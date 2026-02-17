"""Prompt templates for the Generator."""

from typing import Any


# System prompt for answer generation
GENERATOR_SYSTEM_PROMPT = """You are an AI assistant for an Enterprise Knowledge Copilot system.
Your task is to generate accurate, helpful answers based on the provided context documents.

Guidelines:
1. Only use information from the provided context documents to answer the question
2. If the context doesn't contain enough information to answer the question, say so clearly
3. Be concise but comprehensive in your answers
4. If there are multiple relevant documents, synthesize the information from all of them
5. Cite specific sources when possible
6. Maintain a professional and helpful tone
7. If you're unsure about something, acknowledge the uncertainty

User Role: {user_role}
"""

# Context formatting prompt
CONTEXT_FORMAT_PROMPT = """Based on the following context documents, please answer the user's question.

Context Documents:
{context}

---

User Question: {question}

---

Instructions:
- Provide a clear, accurate answer based solely on the context provided
- If the context doesn't contain enough information, state that clearly
- Use a professional tone
- Keep your answer concise but informative
"""

# Few-shot examples for better answers
GENERATOR_FEW_SHOT_EXAMPLES = """
Example 1:
Context: "The company vacation policy allows employees to take up to 15 days of paid vacation per year. Accrued vacation can be carried over to the next year, up to a maximum of 5 days."
Question: "How many vacation days can I carry over?"
Answer: "According to the company vacation policy, you can carry over up to 5 days of accrued vacation to the next year."

Example 2:
Context: "Project Alpha is scheduled to start on March 1st and end on June 30th. The budget allocation is $500,000. The team consists of 10 members including a project manager, 2 senior developers, 3 developers, and 4 QA engineers."
Question: "When does Project Alpha end?"
Answer: "Project Alpha is scheduled to end on June 30th."

Example 3:
Context: ""
Question: "What is the company's remote work policy?"
Answer: "I couldn't find information about the company's remote work policy in the provided documents. Please check with HR or consult the employee handbook for more details."
"""

# Template-based generation prompt (for non-LLM fallback)
TEMPLATE_PROMPT = """Based on the following relevant information, please answer the question.

Relevant Context:
{context}

Question: {question}

Answer:"""


def format_context_documents(documents: list[dict[str, Any]]) -> str:
    """Format a list of context documents into a readable string.

    Args:
        documents: List of document dictionaries with 'content', 'source', and optional 'score'

    Returns:
        Formatted context string
    """
    if not documents:
        return "No relevant documents found."

    formatted_parts = []
    for i, doc in enumerate(documents, 1):
        source = doc.get("source", "Unknown source")
        content = doc.get("content", "")
        score = doc.get("score", None)

        score_str = f" (relevance: {score:.2f})" if score is not None else ""
        formatted_parts.append(
            f"--- Document {i}{score_str} ---\n"
            f"Source: {source}\n\n"
            f"Content: {content}\n"
        )

    return "\n\n".join(formatted_parts)


def build_generation_prompt(
    question: str,
    documents: list[dict[str, Any]],
    user_role: str,
    include_few_shot: bool = False,
) -> str:
    """Build the full prompt for answer generation.

    Args:
        question: User's question
        documents: List of context documents
        user_role: User's role for context
        include_few_shot: Whether to include few-shot examples

    Returns:
        Complete prompt string
    """
    context = format_context_documents(documents)

    # Build the prompt with system context
    prompt_parts = [
        GENERATOR_SYSTEM_PROMPT.format(user_role=user_role),
        "\n\n",
    ]

    if include_few_shot:
        prompt_parts.append(GENERATOR_FEW_SHOT_EXAMPLES)
        prompt_parts.append("\n\n")

    prompt_parts.append(
        CONTEXT_FORMAT_PROMPT.format(context=context, question=question)
    )

    return "".join(prompt_parts)


def build_template_prompt(question: str, documents: list[dict[str, Any]]) -> str:
    """Build a simple template-based prompt for non-LLM generation.

    Args:
        question: User's question
        documents: List of context documents

    Returns:
        Simple prompt string
    """
    context = format_context_documents(documents)
    return TEMPLATE_PROMPT.format(context=context, question=question)


def extract_answer_from_response(response: str) -> str:
    """Extract the answer from an LLM response.

    This function can be used to post-process the LLM output
    to ensure it meets our format requirements.

    Args:
        response: Raw LLM response

    Returns:
        Cleaned answer string
    """
    # Remove any leading/trailing whitespace
    answer = response.strip()

    # Remove common prefixes that models might add
    prefixes_to_remove = [
        "Answer:",
        "The answer is:",
        "Based on the context:",
        "Here's the answer:",
    ]

    for prefix in prefixes_to_remove:
        if answer.lower().startswith(prefix.lower()):
            answer = answer[len(prefix):].strip()

    return answer
