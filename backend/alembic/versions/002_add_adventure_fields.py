"""Add adventure tracking fields

Revision ID: 002
Revises: 001
Create Date: 2026-01-19

Adds:
- campaigns.adventure_document_id (FK to pdf_documents)
- sessions.adventure_state (JSONB)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add adventure_document_id to campaigns table
    op.add_column(
        'campaigns',
        sa.Column(
            'adventure_document_id',
            UUID(as_uuid=True),
            sa.ForeignKey('pdf_documents.id'),
            nullable=True
        )
    )

    # Add adventure_state to sessions table
    op.add_column(
        'sessions',
        sa.Column(
            'adventure_state',
            JSONB,
            nullable=True,
            server_default='{}'
        )
    )


def downgrade() -> None:
    # Remove adventure_state from sessions
    op.drop_column('sessions', 'adventure_state')

    # Remove adventure_document_id from campaigns
    op.drop_column('campaigns', 'adventure_document_id')
