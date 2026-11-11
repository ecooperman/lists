"""add app-level invites

An invite can now be to the app itself (for_app) rather than to one list: the person
is let in and gets an account, with nothing shared yet. One such invite per email.

Revision ID: b8d3a6f2c501
Revises: a1c5e9b3d704
Create Date: 2026-11-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8d3a6f2c501'
down_revision: Union[str, Sequence[str], None] = 'a1c5e9b3d704'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("invites") as batch_op:
        batch_op.add_column(sa.Column("for_app", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.create_index(
        "uq_invites_app_email",
        "invites",
        ["email"],
        unique=True,
        sqlite_where=sa.text("for_app = 1"),
        postgresql_where=sa.text("for_app"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_invites_app_email", table_name="invites")
    with op.batch_alter_table("invites") as batch_op:
        batch_op.drop_column("for_app")
