"""Database operations for Knowledge Service."""

from .document_db import (
    calculate_file_hash,
    create_document,
    create_document_chunks,
    delete_document,
    delete_document_chunks,
    get_document,
    get_document_by_hash,
    get_document_point_ids,
    get_session,
    list_documents,
    update_document,
    update_document_metadata,
)

__all__ = [
    "calculate_file_hash",
    "create_document",
    "create_document_chunks",
    "delete_document",
    "delete_document_chunks",
    "get_document",
    "get_document_by_hash",
    "get_document_point_ids",
    "get_session",
    "list_documents",
    "update_document",
    "update_document_metadata",
]
