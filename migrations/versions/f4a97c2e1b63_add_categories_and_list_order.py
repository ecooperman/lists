"""add categories and manual list order

categories (name, color, text_color, sort_order), lists.category_id (optional,
one per list) and lists.sort_order (manual position on the lists index).
Existing lists are numbered in the order the index already showed them
(alphabetical by name), so nothing visibly moves after the upgrade.

Revision ID: f4a97c2e1b63
Revises: e2b84d6a0f17
Create Date: 2026-11-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4a97c2e1b63'
down_revision: Union[str, Sequence[str], None] = 'e2b84d6a0f17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("color", sa.String(), nullable=False),
        sa.Column("text_color", sa.String(), nullable=False, server_default="dark"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    with op.batch_alter_table("lists") as batch_op:
        batch_op.add_column(sa.Column("category_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"))
        batch_op.create_foreign_key("fk_lists_category_id_categories", "categories", ["category_id"], ["id"])

    # Backfill sort_order from the order the index already showed (by name).
    conn = op.get_bind()
    for position, (list_id,) in enumerate(conn.execute(sa.text("SELECT id FROM lists ORDER BY name")).fetchall()):
        conn.execute(sa.text("UPDATE lists SET sort_order = :n WHERE id = :id"), {"n": position, "id": list_id})


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("lists") as batch_op:
        batch_op.drop_constraint("fk_lists_category_id_categories", type_="foreignkey")
        batch_op.drop_column("sort_order")
        batch_op.drop_column("category_id")
    op.drop_table("categories")
