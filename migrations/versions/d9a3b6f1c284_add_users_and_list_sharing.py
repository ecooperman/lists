"""add users and list sharing

users, and list_members (who has which list, as owner / edit / view, plus each
person's own position and category for it). Lists, contacts and categories each
get an owner.

Everything that exists now is parked on a placeholder user
(legacy-owner@lists.invalid) and made that placeholder's lists' owner; the
first person to sign in takes the placeholder over (app/crud.py
get_or_create_user), so it all becomes theirs without moving a row. Each
existing list's sort_order and category_id move onto its owner's membership
row, so the index looks exactly as it did.

Category names go from unique across the table to unique per owner.

Revision ID: d9a3b6f1c284
Revises: f4a97c2e1b63
Create Date: 2026-11-03 09:00:00.000000

"""
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9a3b6f1c284'
down_revision: Union[str, Sequence[str], None] = 'f4a97c2e1b63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY_OWNER_EMAIL = "legacy-owner@lists.invalid"

# SQLite reports the old unnamed UNIQUE(name) on categories only if told how
# it would have been named, which lets batch mode drop it.
CATEGORY_NAMING = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    conn = op.get_bind()
    conn.execute(
        sa.text("INSERT INTO users (email, created_at) VALUES (:email, :now)"),
        {"email": LEGACY_OWNER_EMAIL, "now": datetime.utcnow()},
    )
    legacy_id = conn.execute(sa.text("SELECT id FROM users WHERE email = :e"), {"e": LEGACY_OWNER_EMAIL}).scalar()

    op.create_table(
        "list_members",
        sa.Column("list_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["list_id"], ["lists.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.PrimaryKeyConstraint("list_id", "user_id"),
    )

    # owner_id starts nullable so the existing rows can be filled in.
    for table in ("lists", "contacts", "categories"):
        with op.batch_alter_table(table, naming_convention=CATEGORY_NAMING if table == "categories" else None) as batch_op:
            batch_op.add_column(sa.Column("owner_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(f"fk_{table}_owner_id_users", "users", ["owner_id"], ["id"])
        conn.execute(sa.text(f"UPDATE {table} SET owner_id = :owner"), {"owner": legacy_id})

    # Each list's position and category now belong to its owner's membership.
    conn.execute(
        sa.text(
            "INSERT INTO list_members (list_id, user_id, role, sort_order, category_id) "
            "SELECT id, owner_id, 'owner', sort_order, category_id FROM lists"
        )
    )

    with op.batch_alter_table("lists") as batch_op:
        batch_op.alter_column("owner_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_constraint("fk_lists_category_id_categories", type_="foreignkey")
        batch_op.drop_column("category_id")
        batch_op.drop_column("sort_order")
    with op.batch_alter_table("contacts") as batch_op:
        batch_op.alter_column("owner_id", existing_type=sa.Integer(), nullable=False)
    with op.batch_alter_table("categories", naming_convention=CATEGORY_NAMING) as batch_op:
        batch_op.alter_column("owner_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_constraint("uq_categories_name", type_="unique")
        batch_op.create_unique_constraint("uq_categories_owner_id_name", ["owner_id", "name"])


def downgrade() -> None:
    """Downgrade schema.

    Sharing is lost: each list keeps only its owner's position and category.
    Fails if two people have a category with the same name (the old schema
    had one table-wide namespace)."""
    with op.batch_alter_table("lists") as batch_op:
        batch_op.add_column(sa.Column("category_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"))
        batch_op.create_foreign_key("fk_lists_category_id_categories", "categories", ["category_id"], ["id"])
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE lists SET "
            "sort_order = (SELECT sort_order FROM list_members m WHERE m.list_id = lists.id AND m.user_id = lists.owner_id), "
            "category_id = (SELECT category_id FROM list_members m WHERE m.list_id = lists.id AND m.user_id = lists.owner_id)"
        )
    )
    op.drop_table("list_members")

    with op.batch_alter_table("categories", naming_convention=CATEGORY_NAMING) as batch_op:
        batch_op.drop_constraint("uq_categories_owner_id_name", type_="unique")
        batch_op.drop_constraint("fk_categories_owner_id_users", type_="foreignkey")
        batch_op.drop_column("owner_id")
        batch_op.create_unique_constraint("uq_categories_name", ["name"])
    with op.batch_alter_table("contacts") as batch_op:
        batch_op.drop_constraint("fk_contacts_owner_id_users", type_="foreignkey")
        batch_op.drop_column("owner_id")
    with op.batch_alter_table("lists") as batch_op:
        batch_op.drop_constraint("fk_lists_owner_id_users", type_="foreignkey")
        batch_op.drop_column("owner_id")
    op.drop_table("users")
