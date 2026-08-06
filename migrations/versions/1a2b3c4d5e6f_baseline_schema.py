"""baseline schema

Revision ID: 1a2b3c4d5e6f
Revises:
Create Date: 2026-08-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a2b3c4d5e6f'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "contacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("first_name", sa.String(), nullable=False),
        sa.Column("last_name", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("address", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "gifts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recipient_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("needed_by", sa.DateTime(), nullable=True),
        sa.Column("purchased", sa.Boolean(), nullable=False),
        sa.Column("purchased_at", sa.DateTime(), nullable=True),
        sa.Column(
            "scrape_status",
            sa.Enum("not_started", "success", "failed", "unsupported", name="scrapestatus"),
            nullable=False,
        ),
        sa.Column("scraped_title", sa.String(), nullable=True),
        sa.Column("scraped_description", sa.String(), nullable=True),
        sa.Column("scraped_image_url", sa.String(), nullable=True),
        sa.Column("scraped_at", sa.DateTime(), nullable=True),
        sa.Column("scrape_error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["recipient_id"], ["contacts.id"], name="fk_gifts_recipient_id_contacts"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("gifts")
    op.drop_table("contacts")
