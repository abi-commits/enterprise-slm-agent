"""Text chunking module for document segmentation."""

import logging
from typing import Any

import nltk
from nltk.tokenize import sent_tokenize, word_tokenize

from core.config.settings import get_settings

logger = logging.getLogger(__name__)

# Download required NLTK data
try:
    nltk.data.find("tokenizers/punkt")
except LookupError:
    nltk.download("punkt", quiet=True)

try:
    nltk.data.find("tokenizers/punkt_tab")
except LookupError:
    nltk.download("punkt_tab", quiet=True)


class TextChunker:
    """Text chunker for splitting documents into semantic segments."""

    def __init__(self, chunk_size: int = None, overlap: int = None):
        """Initialize the chunker with configured settings.

        Args:
            chunk_size: Maximum chunk size in tokens. Defaults to settings.
            overlap: Overlap between chunks in tokens. Defaults to settings.
        """
        settings = get_settings()
        self.chunk_size = chunk_size or settings.chunk_size
        self.overlap = overlap or settings.chunk_overlap

        logger.info(f"Initialized chunker with chunk_size={self.chunk_size}, overlap={self.overlap}")

    def chunk_text(self, text: str, metadata: dict[str, Any] = None) -> list[dict[str, Any]]:
        """Split text into overlapping chunks.

        Args:
            text: Text content to chunk.
            metadata: Metadata to attach to each chunk.

        Returns:
            List of chunk dictionaries with 'text' and 'metadata'.
        """
        if not text or not text.strip():
            logger.warning("Empty text provided for chunking")
            return []

        metadata = metadata or {}

        # Tokenize into sentences
        try:
            sentences = sent_tokenize(text)
        except Exception as e:
            logger.warning(f"Failed to tokenize sentences: {e}")
            # Fallback: split by newlines
            sentences = [s.strip() for s in text.split("\n") if s.strip()]

        chunks = []
        current_chunk = []
        current_token_count = 0

        for sentence in sentences:
            # Count tokens (approximate using word count)
            sentence_tokens = len(word_tokenize(sentence))

            # If adding this sentence would exceed chunk size, save current chunk
            if current_token_count + sentence_tokens > self.chunk_size and current_chunk:
                # Join sentences into chunk text
                chunk_text = " ".join(current_chunk)

                chunks.append({
                    "text": chunk_text,
                    "metadata": {
                        **metadata,
                        "chunk_index": len(chunks),
                        "token_count": current_token_count,
                    }
                })

                # Start new chunk with overlap
                # Get the last few sentences for overlap
                if self.overlap > 0 and len(current_chunk) > 1:
                    overlap_sentences = []
                    overlap_tokens = 0
                    for s in reversed(current_chunk):
                        s_tokens = len(word_tokenize(s))
                        if overlap_tokens + s_tokens <= self.overlap:
                            overlap_sentences.insert(0, s)
                            overlap_tokens += s_tokens
                        else:
                            break
                    current_chunk = overlap_sentences
                    current_token_count = overlap_tokens
                else:
                    current_chunk = []
                    current_token_count = 0

            # Add sentence to current chunk
            current_chunk.append(sentence)
            current_token_count += sentence_tokens

        # Add remaining content as final chunk
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            chunks.append({
                "text": chunk_text,
                "metadata": {
                    **metadata,
                    "chunk_index": len(chunks),
                    "token_count": current_token_count,
                }
            })

        logger.info(f"Created {len(chunks)} chunks from {len(text)} characters")
        return chunks

    def chunk_by_paragraphs(self, text: str, metadata: dict[str, Any] = None) -> list[dict[str, Any]]:
        """Split text into chunks by paragraphs.

        Args:
            text: Text content to chunk.
            metadata: Metadata to attach to each chunk.

        Returns:
            List of chunk dictionaries with 'text' and 'metadata'.
        """
        if not text or not text.strip():
            return []

        metadata = metadata or {}

        # Split by paragraphs
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = []
        current_token_count = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            para_tokens = len(word_tokenize(para))

            # If adding this paragraph would exceed chunk size, save current chunk
            if current_token_count + para_tokens > self.chunk_size and current_chunk:
                chunk_text = "\n\n".join(current_chunk)
                chunks.append({
                    "text": chunk_text,
                    "metadata": {
                        **metadata,
                        "chunk_index": len(chunks),
                        "token_count": current_token_count,
                    }
                })

                # Start new chunk
                current_chunk = []
                current_token_count = 0

            # Add paragraph to current chunk
            current_chunk.append(para)
            current_token_count += para_tokens

        # Add remaining content
        if current_chunk:
            chunk_text = "\n\n".join(current_chunk)
            chunks.append({
                "text": chunk_text,
                "metadata": {
                    **metadata,
                    "chunk_index": len(chunks),
                    "token_count": current_token_count,
                }
            })

        return chunks
