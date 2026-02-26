"""Qdrant vector store integration for the Knowledge Service.

Merges functionality from:
- services/search/vector_store.py (search, retrieval, collection management)
- services/ingestion/storage.py (document chunk storage, document tracking)

Provides a shared Qdrant client singleton for both search and ingestion operations.
"""

import logging
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.http.models import Filter, HasIdCondition, PointStruct, SearchParams

from core.config.settings import get_settings

logger = logging.getLogger(__name__)

# Global client instance (shared singleton)
_qdrant_client: Optional[QdrantClient] = None


def get_qdrant_client() -> QdrantClient:
    """Get or create the Qdrant client instance (singleton)."""
    global _qdrant_client
    if _qdrant_client is None:
        settings = get_settings()
        logger.info(f"Connecting to Qdrant at {settings.qdrant_url}")
        _qdrant_client = QdrantClient(url=settings.qdrant_url)
        logger.info("Qdrant client connected successfully")
    return _qdrant_client


def check_qdrant_health() -> bool:
    """Check if Qdrant is accessible.

    Returns:
        True if Qdrant is healthy, False otherwise.
    """
    try:
        client = get_qdrant_client()
        client.health_check()
        return True
    except Exception as e:
        logger.error(f"Qdrant health check failed: {e}")
        return False


def create_collection_if_not_exists(vector_size: int, collection_name: Optional[str] = None) -> bool:
    """Create the Qdrant collection if it doesn't exist.

    Args:
        vector_size: Dimension of the embedding vectors.
        collection_name: Name of the collection. Defaults to settings.

    Returns:
        True if collection exists or was created, False on error.
    """
    settings = get_settings()
    collection_name = collection_name or settings.qdrant_collection

    try:
        client = get_qdrant_client()
        collections = client.get_collections().collections
        collection_names = [c.name for c in collections]

        if collection_name not in collection_names:
            logger.info(f"Creating collection: {collection_name}")
            client.create_collection(
                collection_name=collection_name,
                vectors_config={
                    "dense": {
                        "size": vector_size,
                        "distance": "Cosine",
                    }
                },
            )
            logger.info(f"Collection '{collection_name}' created successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to create collection: {e}")
        return False


# --- Search operations (from services/search/vector_store.py) ---

def search_documents(
    query_embedding: np.ndarray,
    user_role: str,
    top_k: int = 10,
    collection_name: Optional[str] = None,
    additional_filters: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Search documents in Qdrant with role-based filtering.

    Args:
        query_embedding: The query embedding vector.
        user_role: User role for RBAC filtering.
        top_k: Number of results to return.
        collection_name: Name of the collection. Defaults to settings.
        additional_filters: Additional filters to apply.

    Returns:
        List of search results with id, score, payload, and metadata.
    """
    settings = get_settings()
    collection_name = collection_name or settings.qdrant_collection

    try:
        client = get_qdrant_client()

        # Build RBAC filter - allow documents accessible to user's role
        # Documents can be accessed by specific roles or "all" (public)
        must_conditions = [
            {
                "should": [
                    {"match": {"access_roles": user_role}},
                    {"match": {"access_roles": "all"}},
                ]
            }
        ]

        # Add admin bypass - admins can see everything
        if user_role.lower() == "admin":
            must_conditions = []

        # Add additional filters if provided
        if additional_filters:
            for key, value in additional_filters.items():
                must_conditions.append({"match": {key: value}})

        search_filter = Filter(**{"must": must_conditions}) if must_conditions else None

        # Perform search
        results = client.search(
            collection_name=collection_name,
            query_vector=query_embedding,
            query_filter=search_filter,
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )

        # Format results
        search_results = []
        for hit in results:
            search_results.append({
                "id": hit.id,
                "score": hit.score,
                "payload": hit.payload,
            })

        logger.info(f"Found {len(search_results)} documents for role '{user_role}'")
        return search_results

    except UnexpectedResponse as e:
        logger.error(f"Qdrant unexpected response: {e}")
        return []
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return []


def get_document_by_id(
    doc_id: str,
    collection_name: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Retrieve a single document by ID.

    Args:
        doc_id: Document ID.
        collection_name: Name of the collection. Defaults to settings.

    Returns:
        Document payload if found, None otherwise.
    """
    settings = get_settings()
    collection_name = collection_name or settings.qdrant_collection

    try:
        client = get_qdrant_client()
        results = client.retrieve(
            collection_name=collection_name,
            ids=[doc_id],
            with_payload=True,
            with_vectors=False,
        )

        if results:
            return results[0].payload
        return None

    except Exception as e:
        logger.error(f"Failed to retrieve document {doc_id}: {e}")
        return None


def add_documents(
    points: list[dict[str, Any]],
    collection_name: Optional[str] = None,
) -> bool:
    """Add documents to the vector store.

    Args:
        points: List of point dictionaries with id, vector, and payload.
        collection_name: Name of the collection. Defaults to settings.

    Returns:
        True if successful, False otherwise.
    """
    settings = get_settings()
    collection_name = collection_name or settings.qdrant_collection

    try:
        client = get_qdrant_client()

        # Convert to PointStruct
        point_structs = [
            PointStruct(
                id=p["id"],
                vector=p["vector"],
                payload=p.get("payload", {}),
            )
            for p in points
        ]

        client.upsert(
            collection_name=collection_name,
            points=point_structs,
        )

        logger.info(f"Added {len(points)} documents to collection '{collection_name}'")
        return True

    except Exception as e:
        logger.error(f"Failed to add documents: {e}")
        return False


def delete_documents(
    doc_ids: list[str],
    collection_name: Optional[str] = None,
) -> bool:
    """Delete documents from the vector store by point IDs.

    Args:
        doc_ids: List of document IDs to delete.
        collection_name: Name of the collection. Defaults to settings.

    Returns:
        True if successful, False otherwise.
    """
    settings = get_settings()
    collection_name = collection_name or settings.qdrant_collection

    try:
        client = get_qdrant_client()
        client.delete(
            collection_name=collection_name,
            points_selector=Filter(
                must=[HasIdCondition(has_id=doc_ids)]
            ),
        )

        logger.info(f"Deleted {len(doc_ids)} documents from collection '{collection_name}'")
        return True

    except Exception as e:
        logger.error(f"Failed to delete documents: {e}")
        return False


# --- Ingestion/storage operations (from services/ingestion/storage.py) ---

async def store_document_chunks(
    document_id: str,
    chunks: list[dict[str, Any]],
    title: str,
    filename: str,
    department: str,
    access_role: str,
    file_hash: str,
    upload_user_id: str,
    metadata: Optional[dict[str, Any]] = None,
    collection_name: Optional[str] = None,
) -> bool:
    """Store document chunks in Qdrant with RBAC metadata and track in database.

    Args:
        document_id: Unique document identifier.
        chunks: List of chunk dictionaries with 'text' and 'embedding'.
        title: Document title.
        filename: Original filename.
        department: Department for RBAC.
        access_role: Access role for RBAC.
        file_hash: SHA256 hash of file content.
        upload_user_id: User ID who uploaded the document.
        metadata: Additional metadata.
        collection_name: Name of the collection. Defaults to settings.

    Returns:
        True if successful, False otherwise.
    """
    from services.knowledge.database import (
        create_document,
        create_document_chunks,
        delete_document,
        get_session,
    )
    
    settings = get_settings()
    collection_name = collection_name or settings.qdrant_collection

    try:
        client = get_qdrant_client()

        # Create points for each chunk
        points = []
        point_ids = []
        for i, chunk in enumerate(chunks):
            point_id = str(uuid4())  # Use UUIDs instead of predictable IDs
            point_ids.append(point_id)

            # Build payload with RBAC metadata
            payload = {
                "document_id": document_id,
                "title": title,
                "department": department,
                "access_roles": [access_role, "all"],  # Include "all" for public access
                "chunk_index": i,
                "text": chunk["text"],
                "token_count": chunk.get("metadata", {}).get("token_count", 0),
                "metadata": metadata or {},
                "created_at": datetime.utcnow().isoformat(),
            }

            # Convert numpy array to list for JSON serialization
            vector = chunk["embedding"].tolist() if isinstance(chunk["embedding"], np.ndarray) else chunk["embedding"]

            points.append(PointStruct(
                id=point_id,
                vector={"dense": vector},
                payload=payload,
            ))

        # Upsert points to Qdrant
        client.upsert(
            collection_name=collection_name,
            points=points,
        )

        # Store document metadata in PostgreSQL with chunk tracking
        async for session in get_session():
            try:
                # Create document record
                await create_document(
                    session=session,
                    document_id=document_id,
                    title=title,
                    filename=filename,
                    department=department,
                    access_role=access_role,
                    file_hash=file_hash,
                    upload_user_id=upload_user_id,
                    chunk_count=len(chunks),
                )
                
                # Create chunk tracking records
                await create_document_chunks(
                    session=session,
                    document_id=document_id,
                    point_ids=point_ids,
                )
                
                logger.info(f"Stored {len(chunks)} chunks for document {document_id} in DB and Qdrant")
                return True
                
            except Exception as db_error:
                # Rollback: Delete from Qdrant if DB insert failed
                logger.error(f"Database insert failed, rolling back Qdrant upload: {db_error}")
                try:
                    client.delete(
                        collection_name=collection_name,
                        points_selector=Filter(
                            must=[HasIdCondition(has_id=point_ids)]
                        ),
                    )
                except Exception as rollback_error:
                    logger.error(f"Rollback failed: {rollback_error}")
                raise db_error

    except Exception as e:
        logger.error(f"Failed to store document chunks: {e}")
        return False


async def get_document_info(document_id: str) -> Optional[dict[str, Any]]:
    """Get document information from the database.

    Args:
        document_id: Document ID to look up.

    Returns:
        Document info dict if found, None otherwise.
    """
    from services.knowledge.database import get_document, get_session
    
    async for session in get_session():
        doc = await get_document(session, document_id)
        if doc:
            return {
                "id": doc.id,
                "title": doc.title,
                "filename": doc.filename,
                "department": doc.department,
                "access_role": doc.access_role,
                "chunk_count": doc.chunk_count,
                "file_hash": doc.file_hash,
                "upload_user_id": doc.upload_user_id,
                "version": doc.version,
                "created_at": doc.created_at.isoformat(),
                "updated_at": doc.updated_at.isoformat(),
            }
        return None


async def delete_document(
    document_id: str,
    collection_name: Optional[str] = None,
) -> int:
    """Delete a document and its chunks from both Qdrant and database.

    Args:
        document_id: Document ID to delete.
        collection_name: Name of the collection. Defaults to settings.

    Returns:
        Number of chunks deleted.
    """
    from services.knowledge.database import (
        get_document_point_ids,
        delete_document as db_delete_document,
        get_session,
    )
    
    settings = get_settings()
    collection_name = collection_name or settings.qdrant_collection

    try:
        client = get_qdrant_client()

        # Get point IDs from database
        async for session in get_session():
            point_ids = await get_document_point_ids(session, document_id)
            
            if point_ids:
                # Delete from Qdrant
                client.delete(
                    collection_name=collection_name,
                    points_selector=Filter(
                        must=[HasIdCondition(has_id=point_ids)]
                    ),
                )

            # Delete from database (cascades to document_chunks)
            deleted = await db_delete_document(session, document_id)
            
            if deleted:
                logger.info(f"Deleted {len(point_ids)} chunks for document {document_id}")
                return len(point_ids)
            else:
                logger.warning(f"Document {document_id} not found in database")
                return 0

    except Exception as e:
        logger.error(f"Failed to delete document: {e}")
        return 0


async def list_documents(
    department: Optional[str] = None,
    access_role: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List documents from the database.

    Args:
        department: Filter by department.
        access_role: Filter by access role.
        limit: Maximum number of documents to return.
        offset: Offset for pagination.

    Returns:
        List of document info dictionaries.
    """
    from services.knowledge.database import list_documents as db_list_documents, get_session
    
    async for session in get_session():
        docs = await db_list_documents(
            session=session,
            offset=offset,
            limit=limit,
            department=department,
            access_role=access_role,
        )
        
        return [
            {
                "id": doc.id,
                "title": doc.title,
                "filename": doc.filename,
                "department": doc.department,
                "access_role": doc.access_role,
                "chunk_count": doc.chunk_count,
                "version": doc.version,
                "created_at": doc.created_at.isoformat(),
                "updated_at": doc.updated_at.isoformat(),
            }
            for doc in docs
        ]
    
    return []
