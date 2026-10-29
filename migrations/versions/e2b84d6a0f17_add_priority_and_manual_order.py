"""add priority and manual ordering

items.priority (1-5 lowest to highest, NULL = none set), items.sort_order (manual
position within the list), lists.sort_mode ("manual" or "priority") and
lists.priority_labels (per-list names for levels 1-5, NULL = defaults).
Existing items are
numbered in the order they were already shown in (not done first, then by
needed-by date, then newest first) so every list looks the same after the
upgrade; every list starts in manual mode.

Revision ID: e2b84d6a0f17
Revises: c7e4a19d3b52
Create Date: 2026-10-29 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2b84d6a0f17'
down_revision: Union[str, Sequence[str], None] = 'c7e4a19d3b52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default on the NOT NULL columns so they can be added to existing rows.
    with op.batch_alter_table("items") as batch_op:
        batch_op.add_column(sa.Column("priority", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"))
    with op.batch_alter_table("lists") as batch_op:
        batch_op.add_column(sa.Column("sort_mode", sa.String(), nullable=False, server_default="manual"))
        batch_op.add_column(sa.Column("priority_labels", sa.JSON(), nullable=True))

    # Backfill sort_order from the order lists were previously displayed in.
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, list_id FROM items "
            "ORDER BY list_id, done, needed_by IS NULL, needed_by, created_at DESC, id"
        )
    ).fetchall()
    position = {}
    for item_id, list_id in rows:
        n = position.get(list_id, 0)
        conn.execute(sa.text("UPDATE items SET sort_order = :n WHERE id = :id"), {"n": n, "id": item_id})
        position[list_id] = n + 1


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("lists") as batch_op:
        batch_op.drop_column("priority_labels")
        batch_op.drop_column("sort_mode")
    with op.batch_alter_table("items") as batch_op:
        batch_op.drop_column("sort_order")
        batch_op.drop_column("priority")
