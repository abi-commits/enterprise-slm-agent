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
        
    Returns:
        Dict with chunks_created and processing_time_ms
    """
    start_time = time.time()
    
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
    
    # Store in Qdrant
    logger.info(f"Storing document {document_id} in Qdrant")
    success = vector_store.store_document_chunks(
        document_id=document_id,
        chunks=chunks,
        title=title,
        department=department,
        access_role=access_role,
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

    The document will be parsed, chunked, embedded, and stored in Qdrant.
    This endpoint blocks until processing is complete. For large files,
    use the async endpoint: POST /documents/async

    Args:
        file: The file to upload (PDF, DOCX, TXT, or Markdown).
        title: Document title.
        department: Department for RBAC.
        access_role: Access role for RBAC (default: "all").
        metadata: Optional JSON string of additional metadata.

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
    doc_info = vector_store.get_document_info(document_id)

    if not doc_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    return knowledge_schemas.DocumentStatusResponse(
        document_id=doc_info["document_id"],
        status=doc_info.get("status", "unknown"),
        chunks=doc_info.get("chunks", 0),
        created_at=doc_info.get("created_at", datetime.utcnow()),
        title=doc_info.get("title"),
        department=doc_info.get("department"),
        access_role=doc_info.get("access_role"),
        error_message=doc_info.get("error"),
    )


@router.delete("/{document_id}", response_model=knowledge_schemas.DeleteResponse)
async def delete_document(document_id: str) -> knowledge_schemas.DeleteResponse:
    """Delete a document and all its chunks.

    Args:
        document_id: The document ID to delete.

    Returns:
        DeleteResponse with deletion status.
    """
    # Check if document exists
    doc_info = vector_store.get_document_info(document_id)
    if not doc_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    # Delete from Qdrant
    chunks_deleted = vector_store.delete_document(document_id)

    return knowledge_schemas.DeleteResponse(
        document_id=document_id,
        status="deleted",
        chunks_deleted=chunks_deleted,
    )


@router.get("", response_model=knowledge_schemas.DocumentListResponse)
async def list_documents(
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
    documents = vector_store.list_documents(
        department=department,
        access_role=access_role,
        limit=limit,
        offset=offset,
    )

    doc_items = [
        knowledge_schemas.DocumentListItem(
            document_id=doc["document_id"],
            title=doc.get("title", ""),
            department=doc.get("department", ""),
            access_role=doc.get("access_role", "all"),
            chunks=doc.get("chunks", 0),
            created_at=doc.get("created_at", datetime.utcnow()),
            status=doc.get("status", "unknown"),
        )
        for doc in documents
    ]

    return knowledge_schemas.DocumentListResponse(
        documents=doc_items,
        total=len(doc_items),
    )
