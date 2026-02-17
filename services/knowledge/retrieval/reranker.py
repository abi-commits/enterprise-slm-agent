"""Cross-encoder reranker using cross-encoder/ms-marco-MiniLM-L-6-v2."""

import logging
from typing import Optional

import numpy as np
import torch
from sentence_transformers import CrossEncoder

from core.config.settings import get_settings

logger = logging.getLogger(__name__)

# Global model instance
_reranker_model: Optional[CrossEncoder] = None


def get_reranker_model() -> CrossEncoder:
    """Get or create the cross-encoder reranker model instance."""
    global _reranker_model
    if _reranker_model is None:
        settings = get_settings()
        logger.info(f"Loading reranker model: {settings.reranker_model}")
        _reranker_model = CrossEncoder(settings.reranker_model, max_length=512)
        _reranker_model.model.to("cuda" if torch.cuda.is_available() else "cpu")
        logger.info("Reranker model loaded successfully")
    return _reranker_model


def rerank_documents(query: str, documents: list[str], top_k: Optional[int] = None) -> list[tuple[int, float]]:
    """Rerank documents based on relevance to the query using cross-encoder.

    Args:
        query: The search query.
        documents: List of document texts to rerank.
        top_k: Optional number of top results to return. If None, returns all.

    Returns:
        List of tuples (document_index, relevance_score) sorted by relevance.
    """
    if not documents:
        return []

    model = get_reranker_model()

    # Create query-document pairs for cross-encoder scoring
    pairs = [[query, doc] for doc in documents]

    # Get relevance scores
    scores = model.predict(pairs)

    # Sort by score descending
    results = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)

    if top_k is not None:
        results = results[:top_k]

    return results


def get_reranker_scores(query: str, documents: list[str]) -> np.ndarray:
    """Get relevance scores for all documents without sorting.

    Args:
        query: The search query.
        documents: List of document texts.

    Returns:
        Numpy array of relevance scores.
    """
    if not documents:
        return np.array([])

    model = get_reranker_model()
    pairs = [[query, doc] for doc in documents]
    scores = model.predict(pairs)
    return scores
