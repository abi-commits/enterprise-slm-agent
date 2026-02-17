"""Redis Streams based message queue for async document ingestion.

Implements a robust message queue using Redis Streams to handle:
- Async document ingestion to avoid HTTP timeouts
- Job status tracking with polling endpoints
- Consumer groups for horizontal scaling of workers
- Dead letter queue for failed jobs
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

from redis.asyncio import from_url as redis_from_url
from redis.exceptions import ResponseError as RedisResponseError

from core.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class IngestionJobStatus(str, Enum):
    """Status values for ingestion jobs."""
    
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class IngestionJob:
    """Represents a document ingestion job."""
    
    job_id: str
    document_id: str
    filename: str
    title: str
    department: str
    access_role: str
    metadata: dict[str, Any]
    file_content_key: str  # Redis key where file content is stored temporarily
    status: IngestionJobStatus = IngestionJobStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None
    retry_count: int = 0
    chunks_created: int = 0
    processing_time_ms: float = 0.0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert job to dictionary for Redis storage."""
        return {
            "job_id": self.job_id,
            "document_id": self.document_id,
            "filename": self.filename,
            "title": self.title,
            "department": self.department,
            "access_role": self.access_role,
            "metadata": json.dumps(self.metadata),
            "file_content_key": self.file_content_key,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "error_message": self.error_message or "",
            "retry_count": str(self.retry_count),
            "chunks_created": str(self.chunks_created),
            "processing_time_ms": str(self.processing_time_ms),
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IngestionJob":
        """Create job from Redis hash data."""
        return cls(
            job_id=data["job_id"],
            document_id=data["document_id"],
            filename=data["filename"],
            title=data["title"],
            department=data["department"],
            access_role=data["access_role"],
            metadata=json.loads(data.get("metadata", "{}")),
            file_content_key=data["file_content_key"],
            status=IngestionJobStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            error_message=data.get("error_message") or None,
            retry_count=int(data.get("retry_count", 0)),
            chunks_created=int(data.get("chunks_created", 0)),
            processing_time_ms=float(data.get("processing_time_ms", 0.0)),
        )


class IngestionQueue:
    """Redis Streams based queue for document ingestion.
    
    Uses Redis Streams for reliable message delivery with:
    - Consumer groups for parallel processing
    - Automatic message acknowledgment
    - Dead letter queue for failed jobs
    """
    
    STREAM_KEY = "ingestion:jobs:stream"
    JOBS_HASH_KEY = "ingestion:jobs:details"
    DLQ_KEY = "ingestion:jobs:dlq"
    CONSUMER_GROUP = "ingestion_workers"
    FILE_CONTENT_PREFIX = "ingestion:files:"
    FILE_CONTENT_TTL = 3600  # 1 hour TTL for uploaded files
    MAX_RETRIES = 3
    
    def __init__(self, redis_url: Optional[str] = None):
        """Initialize the queue.
        
        Args:
            redis_url: Redis connection URL (defaults to settings)
        """
        self.redis_url = redis_url or settings.redis_url
        self._redis: Any = None  # redis.asyncio.Redis; type Any for Pylance compat
        self._initialized = False
    
    @property
    def redis(self) -> Any:
        """Get the Redis client, ensuring it's connected."""
        if self._redis is None:
            raise RuntimeError("Queue not connected. Call connect() first.")
        return self._redis
    
    async def connect(self) -> None:
        """Connect to Redis and initialize the consumer group."""
        if self._redis is not None:
            return
            
        self._redis = redis_from_url(
            self.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        
        # Create consumer group if it doesn't exist
        try:
            await self.redis.xgroup_create(
                self.STREAM_KEY,
                self.CONSUMER_GROUP,
                id="0",
                mkstream=True,
            )
            logger.info(f"Created consumer group: {self.CONSUMER_GROUP}")
        except RedisResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise
            logger.debug(f"Consumer group already exists: {self.CONSUMER_GROUP}")
        
        self._initialized = True
        logger.info("Ingestion queue connected to Redis")
    
    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self.redis.close()
            self._redis = None
            self._initialized = False
    
    async def _ensure_connected(self) -> None:
        """Ensure we're connected to Redis."""
        if not self._initialized:
            await self.connect()
    
    async def enqueue(
        self,
        filename: str,
        file_content: bytes,
        title: str,
        department: str,
        access_role: str = "all",
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        """Add a document to the ingestion queue.
        
        Args:
            filename: Original filename
            file_content: Raw file content bytes
            title: Document title
            department: Department for RBAC
            access_role: Access role for RBAC
            metadata: Additional metadata
            
        Returns:
            Job ID for status polling
        """
        await self._ensure_connected()
        
        job_id = str(uuid.uuid4())
        document_id = str(uuid.uuid4())
        file_content_key = f"{self.FILE_CONTENT_PREFIX}{job_id}"
        
        # Store file content in Redis with TTL
        await self.redis.set(
            file_content_key,
            file_content,
            ex=self.FILE_CONTENT_TTL,
        )
        
        # Create job object
        job = IngestionJob(
            job_id=job_id,
            document_id=document_id,
            filename=filename,
            title=title,
            department=department,
            access_role=access_role,
            metadata=metadata or {},
            file_content_key=file_content_key,
        )
        
        # Store job details in hash
        await self.redis.hset(
            f"{self.JOBS_HASH_KEY}:{job_id}",
            mapping=job.to_dict(),
        )
        
        # Add to stream for processing
        await self.redis.xadd(
            self.STREAM_KEY,
            {"job_id": job_id},
        )
        
        logger.info(f"Enqueued ingestion job {job_id} for file: {filename}")
        return job_id
    
    async def get_job_status(self, job_id: str) -> Optional[IngestionJob]:
        """Get the current status of an ingestion job.
        
        Args:
            job_id: The job ID to check
            
        Returns:
            IngestionJob if found, None otherwise
        """
        await self._ensure_connected()
        
        data = await self.redis.hgetall(f"{self.JOBS_HASH_KEY}:{job_id}")
        if not data:
            return None
        
        return IngestionJob.from_dict(data)
    
    async def update_job_status(
        self,
        job_id: str,
        status: IngestionJobStatus,
        error_message: Optional[str] = None,
        chunks_created: int = 0,
        processing_time_ms: float = 0.0,
    ) -> None:
        """Update job status in Redis.
        
        Args:
            job_id: Job to update
            status: New status
            error_message: Optional error message for failed jobs
            chunks_created: Number of chunks created
            processing_time_ms: Processing time in milliseconds
        """
        await self._ensure_connected()
        
        updates = {
            "status": status.value,
            "updated_at": datetime.utcnow().isoformat(),
        }
        
        if error_message:
            updates["error_message"] = error_message
        if chunks_created:
            updates["chunks_created"] = str(chunks_created)
        if processing_time_ms:
            updates["processing_time_ms"] = str(processing_time_ms)
        
        await self.redis.hset(
            f"{self.JOBS_HASH_KEY}:{job_id}",
            mapping=updates,
        )
    
    async def get_file_content(self, file_content_key: str) -> Optional[bytes]:
        """Retrieve file content from Redis.
        
        Args:
            file_content_key: Redis key for the file content
            
        Returns:
            File content bytes or None if expired
        """
        await self._ensure_connected()
        
        # Need a separate connection for binary data
        redis_binary = redis_from_url(self.redis_url, decode_responses=False)
        try:
            content = await redis_binary.get(file_content_key)
            return content
        finally:
            await redis_binary.close()
    
    async def delete_file_content(self, file_content_key: str) -> None:
        """Delete file content after processing.
        
        Args:
            file_content_key: Redis key to delete
        """
        await self._ensure_connected()
        await self.redis.delete(file_content_key)
    
    async def move_to_dlq(self, job_id: str, error_message: str) -> None:
        """Move a failed job to the dead letter queue.
        
        Args:
            job_id: The failed job ID
            error_message: Error details
        """
        await self._ensure_connected()
        
        await self.redis.lpush(
            self.DLQ_KEY,
            json.dumps({
                "job_id": job_id,
                "error": error_message,
                "failed_at": datetime.utcnow().isoformat(),
            }),
        )
        
        await self.update_job_status(job_id, IngestionJobStatus.FAILED, error_message)
        logger.warning(f"Job {job_id} moved to DLQ: {error_message}")
    
    async def increment_retry(self, job_id: str) -> int:
        """Increment retry count for a job.
        
        Args:
            job_id: Job to retry
            
        Returns:
            New retry count
        """
        await self._ensure_connected()
        
        retry_count = await self.redis.hincrby(
            f"{self.JOBS_HASH_KEY}:{job_id}",
            "retry_count",
            1,
        )
        
        await self.redis.hset(
            f"{self.JOBS_HASH_KEY}:{job_id}",
            "status",
            IngestionJobStatus.RETRYING.value,
        )
        
        return retry_count
    
    async def list_pending_jobs(self, limit: int = 100) -> list[IngestionJob]:
        """List pending jobs.
        
        Args:
            limit: Maximum number of jobs to return
            
        Returns:
            List of pending IngestionJob objects
        """
        await self._ensure_connected()
        
        # Get pending messages from stream
        messages = await self.redis.xpending_range(
            self.STREAM_KEY,
            self.CONSUMER_GROUP,
            "-",
            "+",
            limit,
        )
        
        jobs = []
        for msg in messages:
            job_id = msg.get("message_id")
            # The message_id here is the stream ID, we need to read the job_id
            # This is a simplified approach
            pass
        
        return jobs


class IngestionWorker:
    """Worker process for consuming and processing ingestion jobs.
    
    Runs as a background task, consuming jobs from the Redis Stream
    and processing documents asynchronously.
    """
    
    def __init__(
        self,
        queue: IngestionQueue,
        process_func: Callable,
        consumer_name: Optional[str] = None,
        batch_size: int = 5,
        block_ms: int = 5000,
    ):
        """Initialize the worker.
        
        Args:
            queue: IngestionQueue instance
            process_func: Async function to process each job
            consumer_name: Unique consumer name (auto-generated if not provided)
            batch_size: Number of jobs to fetch at once
            block_ms: Block time when waiting for jobs
        """
        self.queue = queue
        self.process_func = process_func
        self.consumer_name = consumer_name or f"worker-{uuid.uuid4().hex[:8]}"
        self.batch_size = batch_size
        self.block_ms = block_ms
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """Start the worker as a background task."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info(f"Ingestion worker {self.consumer_name} started")
    
    async def stop(self) -> None:
        """Stop the worker gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"Ingestion worker {self.consumer_name} stopped")
    
    async def _run(self) -> None:
        """Main worker loop."""
        await self.queue.connect()
        
        while self._running:
            try:
                # Read jobs from stream
                messages = await self.queue.redis.xreadgroup(
                    groupname=self.queue.CONSUMER_GROUP,
                    consumername=self.consumer_name,
                    streams={self.queue.STREAM_KEY: ">"},
                    count=self.batch_size,
                    block=self.block_ms,
                )
                
                if not messages:
                    continue
                
                for stream_name, stream_messages in messages:
                    for message_id, message_data in stream_messages:
                        job_id = message_data.get("job_id")
                        if not job_id:
                            continue
                        
                        await self._process_job(job_id, message_id)
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker error: {e}")
                await asyncio.sleep(1)
    
    async def _process_job(self, job_id: str, message_id: str) -> None:
        """Process a single ingestion job.
        
        Args:
            job_id: The job to process
            message_id: Redis stream message ID for acknowledgment
        """
        start_time = time.time()
        
        try:
            # Get job details
            job = await self.queue.get_job_status(job_id)
            if not job:
                logger.error(f"Job {job_id} not found")
                await self.queue.redis.xack(
                    self.queue.STREAM_KEY,
                    self.queue.CONSUMER_GROUP,
                    message_id,
                )
                return
            
            # Update status to processing
            await self.queue.update_job_status(job_id, IngestionJobStatus.PROCESSING)
            
            # Get file content
            file_content = await self.queue.get_file_content(job.file_content_key)
            if not file_content:
                raise ValueError("File content expired or not found")
            
            # Process the document
            result = await self.process_func(
                document_id=job.document_id,
                filename=job.filename,
                file_content=file_content,
                title=job.title,
                department=job.department,
                access_role=job.access_role,
                metadata=job.metadata,
            )
            
            processing_time_ms = (time.time() - start_time) * 1000
            
            # Update job as completed
            await self.queue.update_job_status(
                job_id=job_id,
                status=IngestionJobStatus.COMPLETED,
                chunks_created=result.get("chunks_created", 0),
                processing_time_ms=processing_time_ms,
            )
            
            # Clean up file content
            await self.queue.delete_file_content(job.file_content_key)
            
            # Acknowledge message
            await self.queue.redis.xack(
                self.queue.STREAM_KEY,
                self.queue.CONSUMER_GROUP,
                message_id,
            )
            
            logger.info(
                f"Job {job_id} completed: {result.get('chunks_created', 0)} chunks "
                f"in {processing_time_ms:.2f}ms"
            )
            
        except Exception as e:
            logger.error(f"Failed to process job {job_id}: {e}")
            
            # Check retry count
            retry_count = await self.queue.increment_retry(job_id)
            
            if retry_count >= self.queue.MAX_RETRIES:
                await self.queue.move_to_dlq(job_id, str(e))
            else:
                # Re-queue for retry with backoff
                await asyncio.sleep(min(2 ** retry_count, 30))
                await self.queue.redis.xadd(
                    self.queue.STREAM_KEY,
                    {"job_id": job_id},
                )
            
            # Acknowledge to remove from pending
            await self.queue.redis.xack(
                self.queue.STREAM_KEY,
                self.queue.CONSUMER_GROUP,
                message_id,
            )


# Global queue instance
_queue: Optional[IngestionQueue] = None


def get_queue() -> IngestionQueue:
    """Get the global IngestionQueue instance."""
    global _queue
    if _queue is None:
        _queue = IngestionQueue()
    return _queue
