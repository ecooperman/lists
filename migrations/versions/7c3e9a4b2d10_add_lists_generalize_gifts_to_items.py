"""add lists, generalize gifts into items

Adds a `lists` table, renames `gifts` -> `items` (and purchased/purchased_at
-> done/done_at), and gives every item a `list_id`. All pre-existing rows are
assigned to a single "Gifts" list so nothing is lost; other lists are created
by hand afterwards.

Revision ID: 7c3e9a4b2d10
Revises: 1a2b3c4d5e6f
Create Date: 2026-10-05 12:00:00.000000

"""
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c3e9a4b2d10'
down_revision: Union[str, Sequence[str], None] = '1a2b3c4d5e6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "lists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("purpose", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Seed the list that every existing gift moves into.
    lists = sa.table("lists", sa.column("name", sa.String), sa.column("purpose", sa.String), sa.column("created_at", sa.DateTime))
    op.bulk_insert(
        lists,
        [{"name": "Gifts", "purpose": "Gift ideas to buy, organized by who they're for.", "created_at": datetime.utcnow()}],
    )
    gifts_list_id = op.get_bind().execute(sa.text("SELECT id FROM lists WHERE name = 'Gifts'")).scalar_one()

    op.rename_table("gifts", "items")

    # Add list_id nullable first so existing rows can be backfilled, then
    # tighten it to NOT NULL in a second batch (SQLite rebuilds the table
    # for each batch).
    with op.batch_alter_table("items") as batch_op:
        batch_op.add_column(sa.Column("list_id", sa.Integer(), nullable=True))
        batch_op.alter_column("purchased", new_column_name="done")
        batch_op.alter_column("purchased_at", new_column_name="done_at")

    op.get_bind().execute(sa.text("UPDATE items SET list_id = :list_id"), {"list_id": gifts_list_id})

    with op.batch_alter_table("items") as batch_op:
        batch_op.alter_column("list_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key("fk_items_list_id_lists", "lists", ["list_id"], ["id"])


def downgrade() -> None:
    """Downgrade schema.

    Lossy: the old schema has no lists, so items from every list end up in
    the single `gifts` table, and the lists themselves are dropped.
    """
    with op.batch_alter_table("items") as batch_op:
        batch_op.drop_constraint("fk_items_list_id_lists", type_="foreignkey")
        batch_op.drop_column("list_id")
        batch_op.alter_column("done", new_column_name="purchased")
        batch_op.alter_column("done_at", new_column_name="purchased_at")

    op.rename_table("items", "gifts")
    op.drop_table("lists")
