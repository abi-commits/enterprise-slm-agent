"""Database operations for document metadata.

Provides CRUD operations for documents and chunks, replacing the
in-memory _document_store dict from vector_store.py.
"""

import hashlib
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select, delete, update, and_
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from core.config.settings import get_settings
from services.api.database.models import Document, DocumentChunk

logger = logging.getLogger(__name__)
settings = get_settings()

# Create async engine for Knowledge Service
_engine = create_async_engine(
    settings.database_url.replace("postgresql://", "postgresql+asyncpg://"),
    echo=settings.debug,
    pool_pre_ping=True,
)

# Session factory
_async_session_maker = async_sessionmaker(
    _engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncSession:
    """Get async database session."""
    async with _async_session_maker() as session:
        yield session


def calculate_file_hash(content: bytes) -> str:
    """Calculate SHA256 hash of file content.
    
    Args:
        content: Raw file bytes
        
    Returns:
        Hex digest of SHA256 hash
    """
    return hashlib.sha256(content).hexdigest()


async def create_document(
    session: AsyncSession,
    document_id: str,
    title: str,
    filename: str,
    department: str,
    access_role: str,
    file_hash: str,
    upload_user_id: str,
    chunk_count: int = 0,
) -> Document:
    """Create a new document record.
    
    Args:
        session: Database session
        document_id: UUID for document
        title: Document title
        filename: Original filename
        department: Department for RBAC
        access_role: Access role for RBAC
        file_hash: SHA256 hash of file content
        upload_user_id: User ID who uploaded
        chunk_count: Number of chunks created
        
    Returns:
        Created Document model
    """
    document = Document(
        id=document_id,
        title=title,
        filename=filename,
        department=department,
        access_role=access_role,
        file_hash=file_hash,
        upload_user_id=upload_user_id,
        chunk_count=chunk_count,
        version=1,
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)
    
    logger.info(f"Created document record: {document_id} ({title})")
    return document


async def get_document(
    session: AsyncSession,
    document_id: str,
) -> Optional[Document]:
    """Get document by ID.
    
    Args:
        session: Database session
        document_id: Document UUID
        
    Returns:
        Document model or None if not found
    """
    result = await session.execute(
        select(Document).where(Document.id == document_id)
    )
    return result.scalar_one_or_none()


async def get_document_by_hash(
    session: AsyncSession,
    file_hash: str,
) -> Optional[Document]:
    """Get document by file hash (for duplicate detection).
    
    Args:
        session: Database session
        file_hash: SHA256 hash of file content
        
    Returns:
        Document model or None if not found
    """
    result = await session.execute(
        select(Document).where(Document.file_hash == file_hash)
    )
    return result.scalar_one_or_none()


async def list_documents(
    session: AsyncSession,
    offset: int = 0,
    limit: int = 100,
    department: Optional[str] = None,
    access_role: Optional[str] = None,
) -> list[Document]:
    """List documents with optional filtering.
    
    Args:
        session: Database session
        offset: Pagination offset
        limit: Pagination limit
        department: Filter by department
        access_role: Filter by access role
        
    Returns:
        List of Document models
    """
    query = select(Document).order_by(Document.created_at.desc())
    
    if department:
        query = query.where(Document.department == department)
    if access_role:
        query = query.where(Document.access_role == access_role)
    
    query = query.offset(offset).limit(limit)
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def update_document(
    session: AsyncSession,
    document_id: str,
    file_hash: str,
    chunk_count: int,
) -> Optional[Document]:
    """Update document after re-processing.
    
    Args:
        session: Database session
        document_id: Document UUID
        file_hash: New file hash
        chunk_count: New chunk count
        
    Returns:
        Updated Document model or None if not found
    """
    result = await session.execute(
        update(Document)
        .where(Document.id == document_id)
        .values(
            file_hash=file_hash,
            chunk_count=chunk_count,
            version=Document.version + 1,
            updated_at=datetime.utcnow(),
        )
        .returning(Document)
    )
    await session.commit()
    
    document = result.scalar_one_or_none()
    if document:
        logger.info(f"Updated document: {document_id} (version {document.version})")
    
    return document


async def update_document_metadata(
    session: AsyncSession,
    document_id: str,
    title: Optional[str] = None,
    department: Optional[str] = None,
    access_role: Optional[str] = None,
) -> Optional[Document]:
    """Update document metadata without re-processing.
    
    Args:
        session: Database session
        document_id: Document UUID
        title: New title (optional)
        department: New department (optional)
        access_role: New access role (optional)
        
    Returns:
        Updated Document model or None if not found
    """
    values = {"updated_at": datetime.utcnow()}
    if title is not None:
        values["title"] = title
    if department is not None:
        values["department"] = department
    if access_role is not None:
        values["access_role"] = access_role
    
    result = await session.execute(
        update(Document)
        .where(Document.id == document_id)
        .values(**values)
        .returning(Document)
    )
    await session.commit()
    
    return result.scalar_one_or_none()


async def delete_document(
    session: AsyncSession,
    document_id: str,
) -> bool:
    """Delete document and all associated chunks.
    
    Args:
        session: Database session
        document_id: Document UUID
        
    Returns:
        True if deleted, False if not found
    """
    result = await session.execute(
        delete(Document).where(Document.id == document_id)
    )
    await session.commit()
    
    deleted = result.rowcount > 0
    if deleted:
        logger.info(f"Deleted document: {document_id}")
    
    return deleted


async def create_document_chunks(
    session: AsyncSession,
    document_id: str,
    point_ids: list[str],
) -> list[DocumentChunk]:
    """Create chunk records linking Qdrant point IDs to document.
    
    Args:
        session: Database session
        document_id: Document UUID
        point_ids: List of Qdrant point UUIDs
        
    Returns:
        List of created DocumentChunk models
    """
    chunks = [
        DocumentChunk(
            document_id=document_id,
            chunk_index=idx,
            point_id=point_id,
        )
        for idx, point_id in enumerate(point_ids)
    ]
    
    session.add_all(chunks)
    await session.commit()
    
    logger.info(f"Created {len(chunks)} chunk records for document {document_id}")
    return chunks


async def get_document_point_ids(
    session: AsyncSession,
    document_id: str,
) -> list[str]:
    """Get all Qdrant point IDs for a document.
    
    Args:
        session: Database session
        document_id: Document UUID
        
    Returns:
        List of Qdrant point UUIDs
    """
    result = await session.execute(
        select(DocumentChunk.point_id)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    )
    return list(result.scalars().all())


async def delete_document_chunks(
    session: AsyncSession,
    document_id: str,
) -> int:
    """Delete all chunk records for a document.
    
    Args:
        session: Database session
        document_id: Document UUID
        
    Returns:
        Number of chunks deleted
    """
    result = await session.execute(
        delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
    )
    await session.commit()
    
    logger.info(f"Deleted {result.rowcount} chunk records for document {document_id}")
    return result.rowcount
