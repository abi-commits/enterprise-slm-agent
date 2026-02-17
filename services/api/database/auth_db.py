"""Auth database module using SQLAlchemy async.

Provides user authentication queries (get user, create user) using
the unified SQLAlchemy async session pattern.

"""

from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.user import UserInDB, UserRole
from services.api.database.models import User
from services.api.database.session import db_manager, get_db_session


class Database:
    """Async database manager for user authentication queries.
    
    Uses SQLAlchemy async sessions from the shared DatabaseManager.
    """

    async def connect(self) -> None:
        """Initialize the database connection."""
        await db_manager.connect()

    async def disconnect(self) -> None:
        """Close the database connection pool."""
        await db_manager.disconnect()

    async def get_user_by_username(
        self, 
        username: str, 
        session: Optional[AsyncSession] = None
    ) -> Optional[UserInDB]:
        """
        Get a user by username or email.

        Args:
            username: The username or email to search for
            session: Optional session (uses new session if not provided)

        Returns:
            UserInDB if found, None otherwise
        """
        async def _query(s: AsyncSession) -> Optional[UserInDB]:
            result = await s.execute(
                select(User).where(
                    or_(User.username == username, User.email == username)
                )
            )
            row = result.scalar_one_or_none()
            
            if row is None:
                return None
            
            return UserInDB(
                id=row.id,
                email=row.email,
                username=row.username,
                hashed_password=row.hashed_password,
                full_name=row.full_name,
                role=UserRole(row.role),
                is_active=row.is_active,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        
        if session:
            return await _query(session)
        
        async with db_manager.session() as s:
            return await _query(s)

    async def get_user_by_id(
        self, 
        user_id: str,
        session: Optional[AsyncSession] = None
    ) -> Optional[UserInDB]:
        """
        Get a user by ID.

        Args:
            user_id: The user UUID to search for
            session: Optional session (uses new session if not provided)

        Returns:
            UserInDB if found, None otherwise
        """
        async def _query(s: AsyncSession) -> Optional[UserInDB]:
            result = await s.execute(
                select(User).where(User.id == user_id)
            )
            row = result.scalar_one_or_none()
            
            if row is None:
                return None
            
            return UserInDB(
                id=row.id,
                email=row.email,
                username=row.username,
                hashed_password=row.hashed_password,
                full_name=row.full_name,
                role=UserRole(row.role),
                is_active=row.is_active,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        
        if session:
            return await _query(session)
        
        async with db_manager.session() as s:
            return await _query(s)

    async def create_user(
        self,
        user_id: str,
        email: str,
        username: str,
        hashed_password: str,
        full_name: Optional[str],
        role: UserRole,
        session: Optional[AsyncSession] = None,
    ) -> UserInDB:
        """
        Create a new user.

        Args:
            user_id: The user UUID
            email: User email
            username: Username
            hashed_password: Hashed password
            full_name: Optional full name
            role: User role
            session: Optional session (uses new session if not provided)

        Returns:
            Created UserInDB
        """
        async def _create(s: AsyncSession) -> UserInDB:
            user = User(
                id=user_id,
                email=email,
                username=username,
                hashed_password=hashed_password,
                full_name=full_name,
                role=role.value,
                is_active=True,
            )
            s.add(user)
            await s.flush()
            await s.refresh(user)
            
            return UserInDB(
                id=user.id,
                email=user.email,
                username=user.username,
                hashed_password=user.hashed_password,
                full_name=user.full_name,
                role=UserRole(user.role),
                is_active=user.is_active,
                created_at=user.created_at,
                updated_at=user.updated_at,
            )
        
        if session:
            return await _create(session)
        
        async with db_manager.session() as s:
            return await _create(s)


# Global auth database instance
db = Database()


async def get_db() -> Database:
    """Get the database instance."""
    return db
