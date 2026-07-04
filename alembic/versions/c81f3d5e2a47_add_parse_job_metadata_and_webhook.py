"""add parse_jobs metadata and webhook_url

Revision ID: c81f3d5e2a47
Revises: 934fa83f9eb5
Create Date: 2026-07-04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = 'c81f3d5e2a47'
down_revision: Union[str, None] = '934fa83f9eb5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('parse_jobs', sa.Column('metadata', JSONB, nullable=True))
    op.add_column(
        'parse_jobs', sa.Column('webhook_url', sa.String(length=1000), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('parse_jobs', 'webhook_url')
    op.drop_column('parse_jobs', 'metadata')
