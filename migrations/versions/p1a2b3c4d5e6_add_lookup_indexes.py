"""indexes on the columns the app looks rows up by (foreign keys and a date), so a lookup no longer reads the whole table

Revision ID: p1a2b3c4d5e6
Revises: i6e0f3a7c1d5
"""
from typing import Sequence, Union

from alembic import op

revision: str = "p1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "i6e0f3a7c1d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_items_list_id", "items", ["list_id"])
    op.create_index("ix_items_recipient_id", "items", ["recipient_id"])
    op.create_index("ix_list_members_user_id", "list_members", ["user_id"])
    op.create_index("ix_lists_owner_id", "lists", ["owner_id"])
    op.create_index("ix_contacts_owner_id", "contacts", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_contacts_owner_id", table_name="contacts")
    op.drop_index("ix_lists_owner_id", table_name="lists")
    op.drop_index("ix_list_members_user_id", table_name="list_members")
    op.drop_index("ix_items_recipient_id", table_name="items")
    op.drop_index("ix_items_list_id", table_name="items")
