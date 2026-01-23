"""Add cover_image_path and extracted_images table.

Revision ID: 008
Revises: 007
Create Date: 2025-01-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add cover_image_path to pdf_documents
    op.execute("""
        ALTER TABLE pdf_documents
        ADD COLUMN IF NOT EXISTS cover_image_path VARCHAR(500)
    """)

    # Create extracted_images table for maps, illustrations, etc.
    # Using raw SQL with IF NOT EXISTS for idempotency
    op.execute("""
        CREATE TABLE IF NOT EXISTS extracted_images (
            id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
            document_id UUID NOT NULL REFERENCES pdf_documents(id) ON DELETE CASCADE,
            image_path VARCHAR(500) NOT NULL,
            image_type VARCHAR(50) NOT NULL,
            page_number INTEGER,
            title VARCHAR(255),
            description TEXT,
            width INTEGER,
            height INTEGER,
            file_size INTEGER,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
    """)

    # Create indexes if they don't exist
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_extracted_images_document_id ON extracted_images(document_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_extracted_images_image_type ON extracted_images(image_type)
    """)


def _unused_upgrade() -> None:
    # Original implementation kept for reference
    op.create_table_commented_out(
        'extracted_images',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('document_id', UUID(as_uuid=True), sa.ForeignKey('pdf_documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('image_path', sa.String(500), nullable=False),
        sa.Column('image_type', sa.String(50), nullable=False),  # 'cover', 'map', 'illustration', 'table'
        sa.Column('page_number', sa.Integer),
        sa.Column('title', sa.String(255)),
        sa.Column('description', sa.Text),
        sa.Column('width', sa.Integer),
        sa.Column('height', sa.Integer),
        sa.Column('file_size', sa.Integer),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )

    # Create index for faster lookups
    op.create_index('ix_extracted_images_document_id', 'extracted_images', ['document_id'])
    op.create_index('ix_extracted_images_image_type', 'extracted_images', ['image_type'])


def downgrade() -> None:
    op.drop_index('ix_extracted_images_image_type')
    op.drop_index('ix_extracted_images_document_id')
    op.drop_table('extracted_images')
    op.execute("""
        ALTER TABLE pdf_documents
        DROP COLUMN IF EXISTS cover_image_path
    """)
