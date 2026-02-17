"""Database models and operations for Knowledge Service.

Provides document metadata storage in PostgreSQL to replace
the in-memory document store that was lost on service restart.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, DateTime, Integer, String, Text, select, delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from core.config.settings import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""

    pass


class DocumentRecord(Base):
    """Model for storing document metadata."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    department: Mapped[str] = mapped_column(String(100), nullable=False)
    access_role: Mapped[str] = mapped_column(String(50), nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


# Database engine
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)


async def init_db() -> None:
    """Initialize the database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def store_document(
    document_id: str,
    title: str,
    department: str,
    access_role: str,
    chunk_count: int = 0,
    status: str = "completed",
    metadata: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
) -> bool:
    """Store document metadata in the database.

    Args:
        document_id: Unique document identifier
        title: Document title
        department: Department for RBAC
        access_role: Access role for RBAC
        chunk_count: Number of chunks
        status: Document status (pending, completed, failed)
        metadata: Additional metadata
        error_message: Error message if failed

    Returns:
        True if successful, False otherwise
    """
    try:
        async with AsyncSession(engine) as session:
            document = DocumentRecord(
                id=document_id,
                title=title,
                department=department,
                access_role=access_role,
                chunk_count=chunk_count,
                status=status,
                metadata_json=metadata or {},
                error_message=error_message,
            )
            session.add(document)
            await session.commit()
            return True
    except Exception as e:
        from services.knowledge.main import logger
        logger.error(f"Failed to store document: {e}")
        return False


async def get_document_info(document_id: str) -> Optional[Dict[str, Any]]:
    """Get document information from the database.

    Args:
        document_id: Document ID to look up

    Returns:
        Document info if found, None otherwise
    """
    try:
        async with AsyncSession(engine) as session:
            result = await session.execute(
                select(DocumentRecord).where(DocumentRecord.id == document_id)
            )
            doc = result.scalar_one_or_none()

            if doc is None:
                return None

            return {
                "document_id": doc.id,
                "title": doc.title,
                "department": doc.department,
                "access_role": doc.access_role,
                "chunk_count": doc.chunk_count,
                "status": doc.status,
                "metadata": doc.metadata_json or {},
                "error": doc.error_message,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
    except Exception as e:
        from services.knowledge.main import logger
        logger.error(f"Failed to get document info: {e}")
        return None


async def update_document_status(
    document_id: str,
    status: str,
    error_message: Optional[str] = None,
) -> bool:
    """Update document status.

    Args:
        document_id: Document ID
        status: New status
        error_message: Optional error message

    Returns:
        True if successful, False otherwise
    """
    try:
        async with AsyncSession(engine) as session:
            result = await session.execute(
                select(DocumentRecord).where(DocumentRecord.id == document_id)
            )
            doc = result.scalar_one_or_none()

            if doc:
                doc.status = status
                doc.error_message = error_message
                doc.updated_at = datetime.utcnow()
                await session.commit()
                return True
            return False
    except Exception as e:
        from services.knowledge.main import logger
        logger.error(f"Failed to update document status: {e}")
        return False


async def delete_document_record(document_id: str) -> bool:
    """Delete a document record from the database.

    Args:
        document_id: Document ID to delete

    Returns:
        True if successful, False otherwise
    """
    try:
        async with AsyncSession(engine) as session:
            await session.execute(
                delete(DocumentRecord).where(DocumentRecord.id == document_id)
            )
            await session.commit()
            return True
    except Exception as e:
        from services.knowledge.main import logger
        logger.error(f"Failed to delete document record: {e}")
        return False


async def list_documents(
    department: Optional[str] = None,
    access_role: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """List documents from the database.

    Args:
        department: Filter by department
        access_role: Filter by access role
        limit: Maximum number of documents
        offset: Offset for pagination

    Returns:
        List of document info dictionaries
    """
    try:
        async with AsyncSession(engine) as session:
            query = select(DocumentRecord).order_by(DocumentRecord.created_at.desc())

            if department:
                query = query.where(DocumentRecord.department == department)
            if access_role:
                query = query.where(DocumentRecord.access_role == access_role)

            query = query.limit(limit).offset(offset)
            result = await session.execute(query)
            docs = result.scalars().all()

            return [
                {
                    "document_id": doc.id,
                    "title": doc.title,
                    "department": doc.department,
                    "access_role": doc.access_role,
                    "chunk_count": doc.chunk_count,
                    "status": doc.status,
                    "metadata": doc.metadata_json or {},
                    "created_at": doc.created_at.isoformat() if doc.created_at else None,
                }
                for doc in docs
            ]
    except Exception as e:
        from services.knowledge.main import logger
        logger.error(f"Failed to list documents: {e}")
        return []
