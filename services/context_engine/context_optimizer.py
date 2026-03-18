"""Context optimization and formatting for RAG.

This module transforms raw retrieved documents into an optimal context
string for language model consumption, implementing strategic token
budgeting, filtering, and presentation.

Aligned with Athena's craftsmanship: raw ore (documents) → refined tools (context).
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, list

from jinja2 import Environment, FileSystemLoader, select_autoescape

from core.config.settings import get_settings

settings = get_settings()


@dataclass
class ContextConfig:
    """Configuration for context engineering.

    Attributes:
        max_tokens: Maximum tokens allowed in the final context (default from settings)
        strategy: Truncation strategy: "smart_truncate", "selective", "truncate"
        include_metadata: Whether to include document metadata in context
        include_keywords: Whether to include extracted keywords
        template_name: Name of Jinja2 template to use (without .jinja2)
        min_relevance_threshold: Minimum rerank score to include document (0.0-1.0)
        enable_deduplication: Whether to attempt content deduplication
        max_documents: Hard limit on number of documents to include
    """
    max_tokens: int = field(default_factory=lambda: settings.max_context_tokens)
    strategy: str = "smart_truncate"
    include_metadata: bool = True
    include_keywords: bool = True
    template_name: str = "default"
    min_relevance_threshold: float = 0.3
    enable_deduplication: bool = True
    max_documents: int = 20


@dataclass
class OptimizedContext:
    """Result of context optimization.

    Attributes:
        formatted_context: The final context string to send to LLM
        documents_included: Number of documents after filtering/truncation
        documents_original: Number of input documents before optimization
        tokens_used: Estimated token count of formatted_context
        budget_remaining: Tokens left unused in budget
        coverage_score: Heuristic score (0.0-1.0) estimating query coverage
        metadata: Additional metrics (truncation_count, deduplication_count, etc.)
    """
    formatted_context: str
    documents_included: int
    documents_original: int
    tokens_used: int
    budget_remaining: int
    coverage_score: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)


class TokenCounter:
    """Simple token counter using word-based approximation.

    For production use, consider tiktoken or model-specific tokenizers.
    This approximation is accurate within ~10% for typical English text.
    """

    def count(self, text: str) -> int:
        """Estimate token count for text.

        Uses approximation: 1 token ≈ 0.75 words or 4 characters.
        """
        if not text:
            return 0
        # Word count method (more stable than char count)
        word_count = len(text.split())
        return int(word_count * 1.33)  # 1/0.75 ≈ 1.33

    def estimate(self, text: str) -> int:
        return self.count(text)


class TemplateEngine:
    """Renders context using Jinja2 templates.

    Templates are stored in services/context_engine/templates/.
    Each template should accept:
      - documents: list of document dicts with keys: content, score, metadata, etc.
      - query: original user query
      - keywords: list of extracted keywords (optional)
      - user_role: user's role for RBAC-aware formatting
      - conversation_history: list of previous turns (optional)
    """

    def __init__(self, templates_dir: str | None = None):
        if templates_dir is None:
            templates_dir = Path(__file__).parent / "templates"
        self.templates_dir = Path(templates_dir)
        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._ensure_default_template()

    def _ensure_default_template(self) -> None:
        """Ensure default template exists."""
        default_path = self.templates_dir / "default.jinja2"
        if not default_path.exists():
            default_path.parent.mkdir(parents=True, exist_ok=True)
            default_path.write_text(self._get_default_template())

    def _get_default_template(self) -> str:
        """Return the default template content."""
        return """## Context Documents
{% for doc in documents %}
### Document {{ loop.index }} (Relevance: {{ "%.2f"|format(doc.score) }})
{% if doc.metadata %}
**Source:** {{ doc.metadata.get('title', doc.metadata.get('source', 'Unknown')) }}
{% if doc.metadata.get('department') %}**Department:** {{ doc.metadata.department }}{% endif %}
{% endif %}
{% if doc.truncated %}[TRUNCATED] {% endif %}
{{ doc.content }}

{% endfor %}
"""

    def render(
        self,
        template_name: str,
        documents: list[dict[str, Any]],
        query: str,
        keywords: list[str] | None = None,
        user_role: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> str:
        """Render the context using the specified template."""
        try:
            template = self.env.get_template(f"{template_name}.jinja2")
        except Exception as e:
            # Fallback to simple formatting if template not found
            return self._simple_format(documents, query)

        return template.render(
            documents=documents,
            query=query,
            keywords=keywords or [],
            user_role=user_role,
            conversation_history=conversation_history or [],
        )

    def _simple_format(self, documents: list[dict], query: str) -> str:
        """Fallback simple text format."""
        parts = [f"Query: {query}\n", "Documents:\n"]
        for i, doc in enumerate(documents, 1):
            meta = ""
            if doc.get("metadata"):
                src = doc["metadata"].get("source") or doc["metadata"].get("title") or "Unknown"
                meta = f" [Source: {src}]"
            parts.append(f"Document {i}{meta} (score={doc.get('score', 0):.2f}):\n")
            parts.append(doc.get("content", "") + "\n")
        return "\n".join(parts)


class ContextOptimizer:
    """Main context optimization orchestrator.

    Transforms a list of retrieved documents into an optimal context string
    tailored to the LLM's token budget and presentation needs.
    """

    def __init__(self, config: ContextConfig | None = None):
        self.config = config or ContextConfig()
        self.token_counter = TokenCounter()
        self.template_engine = TemplateEngine()

    def optimize(
        self,
        documents: list[dict[str, Any]],
        query: str,
        keywords: list[str] | None = None,
        user_role: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> OptimizedContext:
        """Optimize documents into a single context string.

        Pipeline:
        1. Filter by relevance threshold
        2. Deduplicate if enabled (simple content overlap)
        3. Sort by score descending
        4. Enforce max_documents limit
        5. Allocate token budget: iterate documents, truncate if needed
        6. Render final context with template
        7. Compute metrics
        """
        original_count = len(documents)

        # Step 1: Filter by relevance
        docs = [
            d for d in documents
            if d.get("score", 0) >= self.config.min_relevance_threshold
        ]

        # Step 2: Deduplication (naive: exact content prefix match)
        if self.config.enable_deduplication:
            docs = self._deduplicate_documents(docs)

        # Step 3: Sort by score descending
        docs.sort(key=lambda d: d.get("score", 0), reverse=True)

        # Step 4: Limit to max_documents
        docs = docs[:self.config.max_documents]

        # Step 5: Token budgeting and document truncation/packing
        allocated_docs = self._allocate_documents(docs, query, keywords)
        included_count = len(allocated_docs)

        # Step 6: Render with template
        formatted_context = self.template_engine.render(
            template_name=self.config.template_name,
            documents=allocated_docs,
            query=query,
            keywords=keywords,
            user_role=user_role,
            conversation_history=conversation_history,
        )

        # Step 7: Metrics
        tokens_used = self.token_counter.count(formatted_context)
        budget_remaining = max(0, self.config.max_tokens - tokens_used)
        coverage_score = self._estimate_coverage(query, allocated_docs)

        metadata = {
            "truncated_count": sum(1 for d in allocated_docs if d.get("truncated", False)),
            "deduplication_removed": original_count - len(docs) - sum(1 for d in allocated_docs if d.get("duplicate", False)),
            "strategy": self.config.strategy,
            "template": self.config.template_name,
        }

        return OptimizedContext(
            formatted_context=formatted_context,
            documents_included=included_count,
            documents_original=original_count,
            tokens_used=tokens_used,
            budget_remaining=budget_remaining,
            coverage_score=coverage_score,
            metadata=metadata,
        )

    def _allocate_documents(
        self,
        docs: list[dict[str, Any]],
        query: str,
        keywords: list[str] | None,
    ) -> list[dict[str, Any]]:
        """Select and optimize documents within token budget.

        Adds documents in score order until budget is exhausted.
        If a document exceeds remaining budget, apply truncation strategy.
        """
        allocated: list[dict] = []
        current_tokens = 0

        # Base overhead: template structure, query, keywords, etc.
        # Rough estimate: 200 tokens for overhead
        overhead = 200
        if self.config.include_keywords and keywords:
            overhead += 10 * len(keywords)
        if self.config.include_metadata:
            overhead += 50 * len(docs)  # metadata per doc

        current_tokens += overhead

        for doc in docs:
            # Estimate tokens for this document including metadata
            content_tokens = self.token_counter.estimate(doc["content"])
            meta_tokens = 50 if self.config.include_metadata else 0
            doc_total = content_tokens + meta_tokens

            if current_tokens + doc_total <= self.config.max_tokens:
                # Fits entirely
                allocated.append(doc)
                current_tokens += doc_total
            else:
                # Doesn't fit - apply strategy
                if self.config.strategy == "smart_truncate":
                    # Attempt to truncate to fit remaining budget
                    remaining = self.config.max_tokens - current_tokens
                    # Reserve overhead for metadata if needed
                    if self.config.include_metadata:
                        remaining -= 50
                    if remaining > 100:  # Minimum viable snippet
                        truncated = self._truncate_to_budget(doc["content"], remaining)
                        new_doc = doc.copy()
                        new_doc["content"] = truncated
                        new_doc["truncated"] = True
                        allocated.append(new_doc)
                        current_tokens = self.config.max_tokens
                        # Budget filled - stop
                    else:
                        # Not enough space even for a snippet
                        break
                elif self.config.strategy == "selective":
                    # Skip entirely, try next doc
                    continue
                else:
                    # Simple truncate-to-fit without breaking
                    break

        return allocated

    def _truncate_to_budget(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within token budget, preserving sentence boundaries."""
        max_chars = max_tokens * 4  # rough approximation

        if len(text) <= max_chars:
            return text

        # Find the last sentence boundary before max_chars
        # Simple approach: split by ". " and accumulate
        sentences = text.replace("! ", "!|").replace("? ", "?|").replace(". ", ".|").split("|")
        result = ""
        for sent in sentences:
            if len(result) + len(sent) + 1 <= max_chars:
                result += sent + ". " if sent.endswith(".") else sent + " "
            else:
                break

        if result:
            return result.strip() + "..."
        else:
            # Fallback: hard cut
            return text[:max_chars].rstrip() + "..."

    def _deduplicate_documents(self, docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove documents with highly overlapping content (simple dedup)."""
        unique: list[dict] = []
        seen_contents: set[str] = set()

        for doc in docs:
            content = doc["content"].strip()
            # Create a simple fingerprint: first 100 chars + length bucket
            fingerprint = content[:100] + str(len(content) // 100)
            if fingerprint not in seen_contents:
                seen_contents.add(fingerprint)
                unique.append(doc)
            else:
                doc["duplicate"] = True  # mark for metrics
        return unique

    def _estimate_coverage(self, query: str, documents: list[dict[str, Any]]) -> float:
        """Heuristic estimate of how well documents cover the query intent."""
        if not documents:
            return 0.0

        query_words = set(query.lower().split())
        if not query_words:
            return 0.5  # neutral

        # Check overlap with each document
        scores = []
        for doc in documents:
            doc_text = doc["content"].lower()
            # Count overlapping unique words
            doc_words = set(doc_text.split())
            overlap = len(query_words.intersection(doc_words))
            scores.append(overlap / len(query_words) if query_words else 0)

        avg_overlap = sum(scores) / len(scores)
        # Cap at 1.0, but also consider number of docs
        coverage = min(1.0, avg_overlap)
        # Boost if we have multiple diverse docs
        if len(documents) >= 3:
            coverage = min(1.0, coverage + 0.1)
        return coverage
