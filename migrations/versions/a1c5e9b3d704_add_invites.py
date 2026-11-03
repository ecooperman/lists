"""add invites

Requests to let someone who has no account yet in: a list's owner asks, an
administrator approves or declines (see app/routers/invites.py).

Revision ID: a1c5e9b3d704
Revises: d9a3b6f1c284
Create Date: 2026-11-04 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c5e9b3d704'
down_revision: Union[str, Sequence[str], None] = 'd9a3b6f1c284'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "invites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("list_id", sa.Integer(), nullable=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("invited_by_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["list_id"], ["lists.id"]),
        sa.ForeignKeyConstraint(["invited_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("list_id", "email", name="uq_invites_list_id_email"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("invites")
