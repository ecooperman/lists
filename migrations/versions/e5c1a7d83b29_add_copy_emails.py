"""count the copies of lists a person has emailed

"Send a copy" can email a list to anyone, with no approval, so each person gets
a daily allowance. This table holds one row per email sent (who sent it and
when, nothing about the recipient or the content) so the allowance can be
counted.

Revision ID: e5c1a7d83b29
Revises: d8a2f5b61e37
Create Date: 2026-11-12 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5c1a7d83b29'
down_revision: Union[str, Sequence[str], None] = 'd8a2f5b61e37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "copy_emails",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_copy_emails_user_id_sent_at", "copy_emails", ["user_id", "sent_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_copy_emails_user_id_sent_at", table_name="copy_emails")
    op.drop_table("copy_emails")
