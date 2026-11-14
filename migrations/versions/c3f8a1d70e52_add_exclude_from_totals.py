"""add items.exclude_from_totals

On a list that tracks costs an item can be left out of the totals without changing its
price or removing it (a "what if I skip this" switch). Every existing item stays counted.

Revision ID: c3f8a1d70e52
Revises: b7e2c5a94d18
Create Date: 2026-11-14 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f8a1d70e52'
down_revision: Union[str, Sequence[str], None] = 'b7e2c5a94d18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("items") as batch_op:
        batch_op.add_column(sa.Column("exclude_from_totals", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("items") as batch_op:
        batch_op.drop_column("exclude_from_totals")
