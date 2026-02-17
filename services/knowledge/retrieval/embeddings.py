"""Shared embedding model integration using BAAI/bge-small-en-v1.5.

This module provides the single shared embedding model instance used by both
search (query embedding) and ingestion (document chunk embedding).
"""

import logging
from typing import Optional

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

from core.config.settings import get_settings

logger = logging.getLogger(__name__)

# Global model instance
_embedding_model: Optional[SentenceTransformer] = None


def get_embedding_model() -> SentenceTransformer:
    """Get or create the embedding model instance."""
    global _embedding_model
    if _embedding_model is None:
        settings = get_settings()
        logger.info(f"Loading embedding model: {settings.embedding_model}")
        _embedding_model = SentenceTransformer(settings.embedding_model)
        _embedding_model.to("cuda" if torch.cuda.is_available() else "cpu")
        logger.info("Embedding model loaded successfully")
    return _embedding_model


def generate_query_embedding(query: str) -> np.ndarray:
    """Generate embedding for a search query.

    Args:
        query: The query text to embed.

    Returns:
        Numpy array of embeddings.
    """
    model = get_embedding_model()
    embedding = model.encode(query, normalize_embeddings=True)
    return embedding


def generate_documents_embeddings(documents: list[str]) -> np.ndarray:
    """Generate embeddings for a list of documents.

    Args:
        documents: List of document texts to embed.

    Returns:
        Numpy array of embeddings with shape (num_documents, embedding_dim).
    """
    model = get_embedding_model()
    embeddings = model.encode(documents, normalize_embeddings=True, batch_size=32)
    return embeddings


def get_embedding_dimension() -> int:
    """Get the embedding dimension of the model.

    Returns:
        The embedding dimension.
    """
    model = get_embedding_model()
    return model.get_sentence_embedding_dimension()
