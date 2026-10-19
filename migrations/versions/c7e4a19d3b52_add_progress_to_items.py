"""add progress to items

How far along a not-yet-done item is, 0-100. Existing items start at 0.

Revision ID: c7e4a19d3b52
Revises: b5d2f81c6a39
Create Date: 2026-10-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7e4a19d3b52'
down_revision: Union[str, Sequence[str], None] = 'b5d2f81c6a39'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default so the NOT NULL column can be added to existing rows.
    with op.batch_alter_table("items") as batch_op:
        batch_op.add_column(sa.Column("progress", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("items") as batch_op:
        batch_op.drop_column("progress")
