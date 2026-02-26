"""Add reuse detection fields to refresh_tokens

Revision ID: 0003_refresh_token_reuse_detection
Revises: 0002_document_metadata
Create Date: 2026-02-18

This migration adds critical security fields for refresh token reuse detection:
- revoked_at: Timestamp when token was revoked (for forensics)
- last_used_at: Timestamp of last usage attempt (helps identify theft timing)
- used_count: Number of times token was used (should be 0 or 1)

These fields enable detection of token theft by identifying when a revoked
token is presented (indicating an attacker has a stolen token).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003_refresh_token_reuse_detection'
down_revision: Union[str, None] = '0002_document_metadata'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add reuse detection fields to refresh_tokens table."""
    
    # Add revoked_at timestamp (when token was revoked)
    op.add_column(
        'refresh_tokens',
        sa.Column('revoked_at', sa.DateTime(), nullable=True)
    )
    
    # Add last_used_at timestamp (last time token was presented)
    op.add_column(
        'refresh_tokens',
        sa.Column('last_used_at', sa.DateTime(), nullable=True)
    )
    
    # Add used_count (how many times token was used - should be 0 or 1)
    op.add_column(
        'refresh_tokens',
        sa.Column('used_count', sa.Integer(), nullable=False, server_default='0')
    )
    
    # Add index on revoked_at for efficient breach investigation queries
    op.create_index(
        'ix_refresh_tokens_revoked_at',
        'refresh_tokens',
        ['revoked_at']
    )


def downgrade() -> None:
    """Remove reuse detection fields from refresh_tokens table."""
    
    op.drop_index('ix_refresh_tokens_revoked_at', table_name='refresh_tokens')
    op.drop_column('refresh_tokens', 'used_count')
    op.drop_column('refresh_tokens', 'last_used_at')
    op.drop_column('refresh_tokens', 'revoked_at')
