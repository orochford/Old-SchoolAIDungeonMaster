"""add_markdown_path_to_pdf_documents

Revision ID: 0af0c7da7a28
Revises: c57827718236
Create Date: 2026-01-22 19:23:29.045328

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0af0c7da7a28'
down_revision: Union[str, None] = 'c57827718236'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('pdf_documents', sa.Column('markdown_path', sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column('pdf_documents', 'markdown_path')
