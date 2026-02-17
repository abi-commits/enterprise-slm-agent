"""Unified async database session management using SQLAlchemy.

Provides a shared connection pool and async session factory for all
database operations (auth, metrics, audit). This consolidates the
previous dual-pattern approach (asyncpg + SQLAlchemy) into a single
SQLAlchemy async pattern.

Benefits:
- Single connection pool with configurable limits
- Consistent ORM-based queries across all operations
- Proper transaction management with context managers
- Easy migration management with Alembic
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from core.config.settings import get_settings
from services.api.database.models import Base

logger = logging.getLogger(__name__)
settings = get_settings()


class DatabaseManager:
    """Unified async database manager using SQLAlchemy.
    
    Provides a shared connection pool and session factory for all
    database operations in the API service.
    """
    
    def __init__(
        self,
        database_url: Optional[str] = None,
        pool_size: int = 10,
        max_overflow: int = 20,
        echo: bool = False,
    ):
        """Initialize the database manager.
        
        Args:
            database_url: PostgreSQL connection URL (async)
            pool_size: Connection pool size
            max_overflow: Max connections above pool_size
            echo: Enable SQL logging
        """
        self._database_url = database_url or settings.database_url
        self._pool_size = pool_size
        self._max_overflow = max_overflow
        self._echo = echo
        
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker[AsyncSession]] = None
    
    @property
    def engine(self) -> AsyncEngine:
        """Get the async engine, creating it if needed."""
        if self._engine is None:
            self._engine = create_async_engine(
                self._database_url,
                echo=self._echo,
                pool_size=self._pool_size,
                max_overflow=self._max_overflow,
                pool_pre_ping=True,
                pool_recycle=300,  # Recycle connections every 5 minutes
            )
        return self._engine
    
    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Get the session factory, creating it if needed."""
        if self._session_factory is None:
            self._session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=True,
            )
        return self._session_factory
    
    async def connect(self) -> None:
        """Initialize the database connection and create tables."""
        logger.info("Connecting to database...")
        
        # Create tables if they don't exist
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("Database connected and tables created")
    
    async def disconnect(self) -> None:
        """Close the database connection pool."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("Database connection closed")
    
    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get an async session with automatic cleanup.
        
        Usage:
            async with db_manager.session() as session:
                result = await session.execute(query)
        """
        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
    
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Dependency injection compatible session generator.
        
        Usage with FastAPI:
            @router.get("/users")
            async def get_users(session: AsyncSession = Depends(db_manager.get_session)):
                ...
        """
        async with self.session() as session:
            yield session


# Global database manager instance
db_manager = DatabaseManager(
    pool_size=10,
    max_overflow=20,
    echo=settings.debug,
)


# Convenience functions for dependency injection
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get an async database session for dependency injection."""
    async with db_manager.session() as session:
        yield session
