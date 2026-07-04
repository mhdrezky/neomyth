"""add QUEUED value to parse_job_status enum

Revision ID: e5a92c7b4f18
Revises: c81f3d5e2a47
Create Date: 2026-07-04

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5a92c7b4f18'
down_revision: Union[str, None] = 'c81f3d5e2a47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside the transaction alembic
    # wraps migrations in, so it needs an autocommit block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE parse_job_status ADD VALUE IF NOT EXISTS 'QUEUED'")


def downgrade() -> None:
    # Postgres cannot remove enum values; intentional no-op.
    pass
