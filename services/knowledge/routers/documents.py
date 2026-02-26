"""Document endpoints for the Knowledge Service.

Supports both synchronous and asynchronous document ingestion:
- POST /documents - Synchronous upload (blocks until complete)
- POST /documents/async - Async upload with job ID for polling
- GET /documents/jobs/{job_id} - Poll job status
- POST /documents/bulk - Bulk upload with ZIP support
"""

import io
import json
import logging
import time
import uuid
import zipfile
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from services.knowledge import schemas as knowledge_schemas
from services.knowledge.ingestion import chunker
from services.knowledge.retrieval import embeddings
from services.knowledge.ingestion import parser
from services.knowledge.retrieval import vector_store
from services.knowledge.queue import IngestionQueue, IngestionJobStatus, get_queue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


# Cache manager for invalidation (shared Redis instance)
_cache_manager = None


async def get_cache_manager():
    """Get or create cache manager instance (lazy initialization)."""
    global _cache_manager
    if _cache_manager is None:
        from services.api.cache import CacheManager
        _cache_manager = CacheManager()
        await _cache_manager.connect()
    return _cache_manager


def embed_chunks(chunks: list[dict]) -> list[dict]:
    """Embed document chunks using the shared embedding model.

    Args:
        chunks: List of chunk dictionaries with 'text' key.

    Returns:
        List of chunks with added 'embedding' key.
    """
    if not chunks:
        return []

    # Extract text from chunks
    texts = [chunk["text"] for chunk in chunks]

    # Generate embeddings using the shared embeddings module
    chunk_embeddings = embeddings.generate_documents_embeddings(texts)

    # Add embeddings to chunks
    for i, chunk in enumerate(chunks):
        chunk["embedding"] = chunk_embeddings[i]

    logger.info(f"Embedded {len(chunks)} chunks")
    return chunks


async def process_document_sync(
    document_id: str,
    filename: str,
    file_content: bytes,
    title: str,
    department: str,
    access_role: str,
    metadata: dict[str, Any],
    upload_user_id: str = "system",  # TODO: Get from auth context
) -> dict[str, Any]:
    """Process a document synchronously (shared by sync upload and worker).
    
    Args:
        document_id: UUID for the document
        filename: Original filename
        file_content: Raw file bytes
        title: Document title
        department: Department for RBAC
        access_role: Access role for RBAC
        metadata: Additional metadata
        upload_user_id: User ID who uploaded the document
        
    Returns:
        Dict with chunks_created and processing_time_ms
    """
    from services.knowledge.database import calculate_file_hash
    
    start_time = time.time()
    
    # Calculate file hash for duplicate detection
    file_hash = calculate_file_hash(file_content)
    logger.info(f"Processing document {filename} with hash {file_hash}")
    
    # Validate file type
    if not parser.DocumentParser.is_supported(filename):
        raise ValueError(f"Unsupported file format: {filename}")
    
    # Parse document
    logger.info(f"Parsing document: {filename}")
    text = parser.DocumentParser.parse(file_content, filename)
    
    if not text or not text.strip():
        raise ValueError("Document contains no extractable text")
    
    # Chunk text
    logger.info(f"Chunking document ({len(text)} chars)")
    chunks = chunker.TextChunker().chunk_text(text, metadata={
        "document_id": document_id,
        "title": title,
        "department": department,
    })
    
    if not chunks:
        raise ValueError("Failed to create chunks from document")
    
    # Embed chunks using shared embedding model
    logger.info(f"Embedding {len(chunks)} chunks")
    chunks = embed_chunks(chunks)
    
    # Store in Qdrant and database
    logger.info(f"Storing document {document_id} in Qdrant and database")
    success = await vector_store.store_document_chunks(
        document_id=document_id,
        chunks=chunks,
        title=title,
        filename=filename,
        department=department,
        access_role=access_role,
        file_hash=file_hash,
        upload_user_id=upload_user_id,
        metadata=metadata,
    )
    
    if not success:
        raise ValueError("Failed to store document in vector database")
    
    processing_time_ms = (time.time() - start_time) * 1000
    
    return {
        "chunks_created": len(chunks),
        "processing_time_ms": processing_time_ms,
    }


@router.post("", response_model=knowledge_schemas.UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    department: str = Form(...),
    access_role: str = Form(default="all"),
    metadata: Optional[str] = Form(default=None),
) -> knowledge_schemas.UploadResponse:
    """Upload and process a new document synchronously.

    The document will be parsed, chunked, embedded, and stored in Qdrant.For large files,
    use the async endpoint: POST /documents/async

    Returns:
        UploadResponse with document ID, status, chunks count, and processing time.
    """
    document_id = str(uuid.uuid4())
    
    # Parse metadata
    metadata_dict = {}
    if metadata:
        try:
            metadata_dict = json.loads(metadata)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse metadata JSON: {metadata}")
    
    try:
        file_content = await file.read()
        
        result = await process_document_sync(
            document_id=document_id,
            filename=file.filename,
            file_content=file_content,
            title=title,
            department=department,
            access_role=access_role,
            metadata=metadata_dict,
        )
        
        # Invalidate caches for the affected role
        try:
            cache = await get_cache_manager()
            await cache.invalidate_document_caches(
                document_id=document_id,
                access_role=access_role,
            )
        except Exception as cache_error:
            logger.warning(f"Failed to invalidate caches: {cache_error}")
        
        return knowledge_schemas.UploadResponse(
            document_id=document_id,
            status="completed",
            chunks_created=result["chunks_created"],
            processing_time_ms=result["processing_time_ms"],
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to process document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process document: {str(e)}",
        )


@router.post("/async", response_model=knowledge_schemas.AsyncUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document_async(
    file: UploadFile = File(...),
    title: str = Form(...),
    department: str = Form(...),
    access_role: str = Form(default="all"),
    metadata: Optional[str] = Form(default=None),
) -> knowledge_schemas.AsyncUploadResponse:
    """Upload a document for asynchronous processing.

    The document is queued for processing and returns immediately with a job ID.
    Poll the job status endpoint to check progress: GET /documents/jobs/{job_id}

    Args:
        file: The file to upload (PDF, DOCX, TXT, or Markdown).
        title: Document title.
        department: Department for RBAC.
        access_role: Access role for RBAC (default: "all").
        metadata: Optional JSON string of additional metadata.

    Returns:
        AsyncUploadResponse with job ID for status polling.
    """
    # Validate file type
    if not parser.DocumentParser.is_supported(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format: {file.filename}",
        )
    
    # Parse metadata
    metadata_dict = {}
    if metadata:
        try:
            metadata_dict = json.loads(metadata)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse metadata JSON: {metadata}")
    
    try:
        file_content = await file.read()
        
        queue = get_queue()
        job_id = await queue.enqueue(
            filename=file.filename,
            file_content=file_content,
            title=title,
            department=department,
            access_role=access_role,
            metadata=metadata_dict,
        )
        
        # Get the job to get document_id
        job = await queue.get_job_status(job_id)
        
        return knowledge_schemas.AsyncUploadResponse(
            job_id=job_id,
            document_id=job.document_id if job else "",
            status="pending",
            message="Document queued for processing",
        )
        
    except Exception as e:
        logger.error(f"Failed to queue document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue document: {str(e)}",
        )


@router.get("/jobs/{job_id}", response_model=knowledge_schemas.JobStatusResponse)
async def get_job_status(job_id: str) -> knowledge_schemas.JobStatusResponse:
    """Get the status of an async ingestion job.

    Args:
        job_id: The job ID returned from async upload.

    Returns:
        JobStatusResponse with current processing status.
    """
    queue = get_queue()
    job = await queue.get_job_status(job_id)
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )
    
    return knowledge_schemas.JobStatusResponse(
        job_id=job.job_id,
        document_id=job.document_id,
        status=job.status.value,
        filename=job.filename,
        title=job.title,
        department=job.department,
        chunks_created=job.chunks_created,
        processing_time_ms=job.processing_time_ms,
        error_message=job.error_message,
        retry_count=job.retry_count,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.post("/bulk", response_model=knowledge_schemas.BulkUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def bulk_upload_documents(
    files: list[UploadFile] = File(None),
    zip_file: UploadFile = File(None),
    department: str = Form(...),
    access_role: str = Form(default="all"),
    metadata: Optional[str] = Form(default=None),
) -> knowledge_schemas.BulkUploadResponse:
    """Bulk upload multiple documents for async processing.

    Supports either:
    - Multiple individual files in the 'files' field
    - A single ZIP file containing multiple documents

    All documents are queued for async processing. Use the job status
    endpoint to check individual file processing status.

    Args:
        files: List of files to upload.
        zip_file: Alternatively, a ZIP file containing documents.
        department: Department for all documents in this batch.
        access_role: Access role for all documents (default: "all").
        metadata: Optional JSON string of additional metadata for all documents.

    Returns:
        BulkUploadResponse with status for each file.
    """
    # Parse metadata
    metadata_dict = {}
    if metadata:
        try:
            metadata_dict = json.loads(metadata)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse metadata JSON: {metadata}")
    
    items: list[knowledge_schemas.BulkUploadItem] = []
    queue = get_queue()
    
    # Collect files to process
    files_to_process: list[tuple[str, bytes]] = []
    
    # Handle ZIP file
    if zip_file and zip_file.filename:
        try:
            zip_content = await zip_file.read()
            with zipfile.ZipFile(io.BytesIO(zip_content), 'r') as zf:
                for name in zf.namelist():
                    # Skip directories and hidden files
                    if name.endswith('/') or name.startswith('__') or name.startswith('.'):
                        continue
                    
                    if parser.DocumentParser.is_supported(name):
                        file_content = zf.read(name)
                        files_to_process.append((name, file_content))
                    else:
                        items.append(knowledge_schemas.BulkUploadItem(
                            filename=name,
                            status="failed",
                            error=f"Unsupported file format",
                        ))
        except zipfile.BadZipFile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid ZIP file",
            )
    
    # Handle individual files
    if files:
        for file in files:
            if file.filename:
                if parser.DocumentParser.is_supported(file.filename):
                    file_content = await file.read()
                    files_to_process.append((file.filename, file_content))
                else:
                    items.append(knowledge_schemas.BulkUploadItem(
                        filename=file.filename,
                        status="failed",
                        error=f"Unsupported file format",
                    ))
    
    if not files_to_process and not items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided. Use 'files' for multiple files or 'zip_file' for a ZIP archive.",
        )
    
    # Queue all valid files
    queued_count = 0
    for filename, file_content in files_to_process:
        try:
            # Use filename as title if not provided
            title = filename.rsplit('.', 1)[0]
            
            job_id = await queue.enqueue(
                filename=filename,
                file_content=file_content,
                title=title,
                department=department,
                access_role=access_role,
                metadata=metadata_dict,
            )
            
            job = await queue.get_job_status(job_id)
            
            items.append(knowledge_schemas.BulkUploadItem(
                filename=filename,
                job_id=job_id,
                document_id=job.document_id if job else None,
                status="queued",
            ))
            queued_count += 1
            
        except Exception as e:
            logger.error(f"Failed to queue {filename}: {e}")
            items.append(knowledge_schemas.BulkUploadItem(
                filename=filename,
                status="failed",
                error=str(e),
            ))
    
    failed_count = len(items) - queued_count
    
    return knowledge_schemas.BulkUploadResponse(
        total_files=len(items),
        queued=queued_count,
        failed=failed_count,
        items=items,
    )


@router.get("/{document_id}/status", response_model=knowledge_schemas.DocumentStatusResponse)
async def get_document_status(document_id: str) -> knowledge_schemas.DocumentStatusResponse:
    """Get the status of a document.

    Args:
        document_id: The document ID to check.

    Returns:
        DocumentStatusResponse with current status information.
    """
    doc_info = await vector_store.get_document_info(document_id)

    if not doc_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    return knowledge_schemas.DocumentStatusResponse(
        document_id=doc_info["id"],
        status="completed",  # All persisted documents are completed
        chunks=doc_info["chunk_count"],
        created_at=datetime.fromisoformat(doc_info["created_at"]) if isinstance(doc_info["created_at"], str) else doc_info["created_at"],
        title=doc_info["title"],
        department=doc_info["department"],
        access_role=doc_info["access_role"],
        error_message=None,
    )


@router.delete("/{document_id}", response_model=knowledge_schemas.DeleteResponse)
async def delete_document_endpoint(document_id: str) -> knowledge_schemas.DeleteResponse:
    """Delete a document and all its chunks.

    Args:
        document_id: The document ID to delete.

    Returns:
        DeleteResponse with deletion status.
    """
    # Check if document exists
    doc_info = await vector_store.get_document_info(document_id)
    if not doc_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    # Delete from Qdrant and database
    chunks_deleted = await vector_store.delete_document(document_id)
    
    # Invalidate caches for the affected role
    try:
        cache = await get_cache_manager()
        await cache.invalidate_document_caches(
            document_id=document_id,
            access_role=doc_info.get("access_role"),
        )
    except Exception as cache_error:
        logger.warning(f"Failed to invalidate caches: {cache_error}")

    return knowledge_schemas.DeleteResponse(
        document_id=document_id,
        status="deleted",
        chunks_deleted=chunks_deleted,
    )


@router.put("/{document_id}", response_model=knowledge_schemas.UploadResponse)
async def update_document(
    document_id: str,
    file: UploadFile = File(...),
    title: Optional[str] = Form(default=None),
    department: Optional[str] = Form(default=None),
    access_role: Optional[str] = Form(default=None),
    metadata: Optional[str] = Form(default=None),
) -> knowledge_schemas.UploadResponse:
    """Update an existing document by re-processing it.

    Returns:
        UploadResponse with updated document info.
    """
    from services.knowledge.database import (
        get_document,
        get_document_point_ids,
        delete_document_chunks,
        update_document,
        get_session,
        calculate_file_hash,
    )
    
    # Check if document exists
    doc_info = await vector_store.get_document_info(document_id)
    if not doc_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )
    
    # Read file content and calculate hash
    file_content = await file.read()
    new_file_hash = calculate_file_hash(file_content)
    
    # Check if content has changed
    if new_file_hash == doc_info["file_hash"]:
        # File content unchanged - just update metadata if provided
        if title or department or access_role:
            async for session in get_session():
                from services.knowledge.database import update_document_metadata
                await update_document_metadata(
                    session=session,
                    document_id=document_id,
                    title=title,
                    department=department,
                    access_role=access_role,
                )
        
        return knowledge_schemas.UploadResponse(
            document_id=document_id,
            status="not_modified",
            chunks_created=doc_info["chunk_count"],
            processing_time_ms=0,
        )
    
    # File content has changed - full reprocessing needed
    # Use existing values if not provided
    final_title = title or doc_info["title"]
    final_department = department or doc_info["department"]
    final_access_role = access_role or doc_info["access_role"]
    final_filename = file.filename or doc_info["filename"]
    
    # Parse metadata
    metadata_dict = {}
    if metadata:
        try:
            metadata_dict = json.loads(metadata)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse metadata JSON: {metadata}")
    
    try:
        start_time = time.time()
        
        # Delete old chunks from Qdrant
        async for session in get_session():
            old_point_ids = await get_document_point_ids(session, document_id)
            
            if old_point_ids:
                from qdrant_client.http.models import Filter, HasIdCondition
                from services.knowledge.retrieval.vector_store import get_qdrant_client
                from core.config.settings import get_settings
                
                settings = get_settings()
                client = get_qdrant_client()
                client.delete(
                    collection_name=settings.qdrant_collection,
                    points_selector=Filter(
                        must=[HasIdCondition(has_id=old_point_ids)]
                    ),
                )
                logger.info(f"Deleted {len(old_point_ids)} old chunks for document {document_id}")
            
            # Delete old chunk records
            await delete_document_chunks(session, document_id)
        
        # Parse, chunk, and embed new version
        if not parser.DocumentParser.is_supported(final_filename):
            raise ValueError(f"Unsupported file format: {final_filename}")
        
        text = parser.DocumentParser.parse(file_content, final_filename)
        if not text or not text.strip():
            raise ValueError("Document contains no extractable text")
        
        chunks = chunker.TextChunker().chunk_text(text, metadata={
            "document_id": document_id,
            "title": final_title,
            "department": final_department,
        })
        
        if not chunks:
            raise ValueError("Failed to create chunks from document")
        
        chunks = embed_chunks(chunks)
        
        # Store new chunks (this will update the document record too)
        success = await vector_store.store_document_chunks(
            document_id=document_id,
            chunks=chunks,
            title=final_title,
            filename=final_filename,
            department=final_department,
            access_role=final_access_role,
            file_hash=new_file_hash,
            upload_user_id=doc_info["upload_user_id"],  # Keep original uploader
            metadata=metadata_dict,
        )
        
        if not success:
            raise ValueError("Failed to store updated document")
        
        processing_time_ms = (time.time() - start_time) * 1000
        
        # Update document record with new version
        async for session in get_session():
            await update_document(
                session=session,
                document_id=document_id,
                file_hash=new_file_hash,
                chunk_count=len(chunks),
            )
        
        # Invalidate caches for the affected role(s)
        try:
            cache = await get_cache_manager()
            await cache.invalidate_document_caches(
                document_id=document_id,
                access_role=final_access_role,
            )
            # If role changed, also invalidate old role's caches
            if final_access_role != doc_info["access_role"]:
                await cache.invalidate_role_caches(doc_info["access_role"])
        except Exception as cache_error:
            logger.warning(f"Failed to invalidate caches: {cache_error}")
        
        return knowledge_schemas.UploadResponse(
            document_id=document_id,
            status="updated",
            chunks_created=len(chunks),
            processing_time_ms=processing_time_ms,
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to update document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update document: {str(e)}",
        )


@router.patch("/{document_id}/metadata")
async def update_document_metadata_endpoint(
    document_id: str,
    title: Optional[str] = None,
    department: Optional[str] = None,
    access_role: Optional[str] = None,
) -> dict[str, Any]:
    """Update document metadata without re-processing.

    Updates only the metadata fields (title, department, access_role) in both
    the database and Qdrant payloads, without re-parsing or re-embedding the document.

    Args:
        document_id: The document ID to update.
        title: New document title (optional).
        department: New department for RBAC (optional).
        access_role: New access role for RBAC (optional).

    Returns:
        Updated document info.
    """
    from services.knowledge.database import (
        get_document,
        get_document_point_ids,
        update_document_metadata as db_update_metadata,
        get_session,
    )
    from services.knowledge.retrieval.vector_store import get_qdrant_client
    from core.config.settings import get_settings
    
    # Check if document exists
    doc_info = await vector_store.get_document_info(document_id)
    if not doc_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )
    
    # At least one field must be provided
    if not any([title, department, access_role]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one field (title, department, access_role) must be provided",
        )
    
    try:
        # Update in database
        async for session in get_session():
            updated_doc = await db_update_metadata(
                session=session,
                document_id=document_id,
                title=title,
                department=department,
                access_role=access_role,
            )
            
            if not updated_doc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Document {document_id} not found",
                )
            
            # Update Qdrant payloads for all chunks
            point_ids = await get_document_point_ids(session, document_id)
            
            if point_ids:
                settings = get_settings()
                client = get_qdrant_client()
                
                # Build payload updates
                payload_updates = {}
                if title:
                    payload_updates["title"] = title
                if department:
                    payload_updates["department"] = department
                if access_role:
                    payload_updates["access_roles"] = [access_role, "all"]
                
                # Update each point's payload
                for point_id in point_ids:
                    client.set_payload(
                        collection_name=settings.qdrant_collection,
                        payload=payload_updates,
                        points=[point_id],
                    )
                
                logger.info(f"Updated metadata for {len(point_ids)} chunks of document {document_id}")
            
            # Invalidate caches for affected roles
            try:
                cache = await get_cache_manager()
                # Invalidate for new access role
                if access_role:
                    await cache.invalidate_role_caches(access_role)
                    # If role changed, also invalidate old role's caches
                    if access_role != doc_info["access_role"]:
                        await cache.invalidate_role_caches(doc_info["access_role"])
                else:
                    # If only title/department changed, invalidate current role
                    await cache.invalidate_role_caches(doc_info["access_role"])
            except Exception as cache_error:
                logger.warning(f"Failed to invalidate caches: {cache_error}")
            
            return {
                "document_id": document_id,
                "status": "metadata_updated",
                "title": updated_doc.title,
                "department": updated_doc.department,
                "access_role": updated_doc.access_role,
                "version": updated_doc.version,
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update document metadata: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update metadata: {str(e)}",
        )


@router.get("", response_model=knowledge_schemas.DocumentListResponse)
async def list_documents_endpoint(
    department: Optional[str] = None,
    access_role: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> knowledge_schemas.DocumentListResponse:
    """List all uploaded documents.

    Args:
        department: Filter by department.
        access_role: Filter by access role.
        limit: Maximum number of documents to return.
        offset: Offset for pagination.

    Returns:
        DocumentListResponse with list of documents.
    """
    documents = await vector_store.list_documents(
        department=department,
        access_role=access_role,
        limit=limit,
        offset=offset,
    )

    doc_items = [
        knowledge_schemas.DocumentListItem(
            document_id=doc["id"],
            title=doc["title"],
            department=doc["department"],
            access_role=doc["access_role"],
            chunks=doc["chunk_count"],
            created_at=datetime.fromisoformat(doc["created_at"]) if isinstance(doc["created_at"], str) else doc["created_at"],
            status="completed",  # All persisted documents are completed
        )
        for doc in documents
    ]

    return knowledge_schemas.DocumentListResponse(
        documents=doc_items,
        total=len(doc_items),
    )
