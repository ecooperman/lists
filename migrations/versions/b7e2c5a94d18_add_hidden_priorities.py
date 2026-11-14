"""add lists.hidden_priorities

A list can hide some of the five priority levels from its priority pickers (a shopping
list that only wants Need / Want / Required, say). NULL = none hidden, so every existing
list is unchanged.

Revision ID: b7e2c5a94d18
Revises: a6d3f9e12b84
Create Date: 2026-11-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e2c5a94d18'
down_revision: Union[str, Sequence[str], None] = 'a6d3f9e12b84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("lists") as batch_op:
        batch_op.add_column(sa.Column("hidden_priorities", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("lists") as batch_op:
        batch_op.drop_column("hidden_priorities")
