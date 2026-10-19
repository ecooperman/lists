"""add locked to lists

A locked list can't be deleted until it's unlocked. Existing lists start
unlocked.

Revision ID: b5d2f81c6a39
Revises: 7c3e9a4b2d10
Create Date: 2026-10-18 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5d2f81c6a39'
down_revision: Union[str, Sequence[str], None] = '7c3e9a4b2d10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default so the NOT NULL column can be added to existing rows.
    with op.batch_alter_table("lists") as batch_op:
        batch_op.add_column(sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("lists") as batch_op:
        batch_op.drop_column("locked")
