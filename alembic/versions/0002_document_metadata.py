"""Add document metadata and refresh tokens tables

Revision ID: 0002_document_metadata
Revises: 0001_initial
Create Date: 2026-02-18

This migration adds:
- documents: Persistent document metadata (replaces in-memory _document_store)
- document_chunks: Maps Qdrant point IDs to documents
- refresh_tokens: JWT refresh token storage for token rotation
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002_document_metadata'
down_revision: Union[str, None] = '0001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create document metadata and refresh tokens tables."""
    
    # Create documents table
    op.create_table(
        'documents',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('filename', sa.String(500), nullable=False),
        sa.Column('department', sa.String(100), nullable=False),
        sa.Column('access_role', sa.String(50), nullable=False),
        sa.Column('chunk_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('file_hash', sa.String(64), nullable=False),  # SHA256 hash
        sa.Column('upload_user_id', sa.String(36), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_documents_department', 'documents', ['department'])
    op.create_index('ix_documents_access_role', 'documents', ['access_role'])
    op.create_index('ix_documents_upload_user_id', 'documents', ['upload_user_id'])
    op.create_index('ix_documents_file_hash', 'documents', ['file_hash'])
    op.create_index('ix_documents_created_at', 'documents', ['created_at'])
    
    # Create document_chunks table (maps Qdrant point IDs to documents)
    op.create_table(
        'document_chunks',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('document_id', sa.String(36), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('point_id', sa.String(36), nullable=False, unique=True),  # Qdrant point UUID
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ['document_id'],
            ['documents.id'],
            name='fk_document_chunks_document_id',
            ondelete='CASCADE'
        ),
    )
    op.create_index('ix_document_chunks_document_id', 'document_chunks', ['document_id'])
    op.create_index('ix_document_chunks_point_id', 'document_chunks', ['point_id'])
    
    # Create refresh_tokens table
    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('token_hash', sa.String(64), nullable=False, unique=True),  # SHA256 hash
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('revoked', sa.Boolean(), nullable=False, server_default='false'),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['users.id'],
            name='fk_refresh_tokens_user_id',
            ondelete='CASCADE'
        ),
    )
    op.create_index('ix_refresh_tokens_token_hash', 'refresh_tokens', ['token_hash'])
    op.create_index('ix_refresh_tokens_user_id', 'refresh_tokens', ['user_id'])
    op.create_index('ix_refresh_tokens_expires_at', 'refresh_tokens', ['expires_at'])


def downgrade() -> None:
    """Drop document metadata and refresh tokens tables."""
    # Drop refresh_tokens table
    op.drop_index('ix_refresh_tokens_expires_at', table_name='refresh_tokens')
    op.drop_index('ix_refresh_tokens_user_id', table_name='refresh_tokens')
    op.drop_index('ix_refresh_tokens_token_hash', table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    
    # Drop document_chunks table
    op.drop_index('ix_document_chunks_point_id', table_name='document_chunks')
    op.drop_index('ix_document_chunks_document_id', table_name='document_chunks')
    op.drop_table('document_chunks')
    
    # Drop documents table
    op.drop_index('ix_documents_created_at', table_name='documents')
    op.drop_index('ix_documents_file_hash', table_name='documents')
    op.drop_index('ix_documents_upload_user_id', table_name='documents')
    op.drop_index('ix_documents_access_role', table_name='documents')
    op.drop_index('ix_documents_department', table_name='documents')
    op.drop_table('documents')
