"""add cost tracking: lists.track_costs, items.estimate_cents and final_cents

A list can be set to track costs: each of its items then carries an estimate and a
final cost (whole cents) and the list shows totals. Everything starts off / empty.

Revision ID: a6d3f9e12b84
Revises: e5c1a7d83b29
Create Date: 2026-11-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a6d3f9e12b84'
down_revision: Union[str, Sequence[str], None] = 'e5c1a7d83b29'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("lists") as batch_op:
        batch_op.add_column(sa.Column("track_costs", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("items") as batch_op:
        batch_op.add_column(sa.Column("estimate_cents", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("final_cents", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("items") as batch_op:
        batch_op.drop_column("final_cents")
        batch_op.drop_column("estimate_cents")
    with op.batch_alter_table("lists") as batch_op:
        batch_op.drop_column("track_costs")
