"""several labelled links per item, and a per-person list of link labels

An item used to have one `url`. It now has any number of links (`item_links`:
address, optional label, position), the first being the primary one, and each
person keeps a private list of labels (`link_labels`) to pick from. Every
existing url becomes the first (unlabelled) link of its item, and the old
column is dropped. Only web addresses are kept: a leading http:// or https://
stays as it is, an address with no scheme at all gets https:// in front of it,
and anything else (javascript:, mailto:, ...) is not a link to a web page and
is left behind - the column accepted anything before, and these links are put
into pages as clickable addresses.

Downgrading puts each item's first link back into `url` (the rest are lost).

Revision ID: d8a2f5b61e37
Revises: c4f1e8a29d63
Create Date: 2026-11-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8a2f5b61e37'
down_revision: Union[str, Sequence[str], None] = 'c4f1e8a29d63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _web_address(url):
    """The address as a web link, or None if it isn't one."""
    url = (url or "").strip()
    if not url:
        return None
    lowered = url.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        return url
    if ":" not in url:
        return "https://" + url
    return None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "link_labels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "name", name="uq_link_labels_owner_id_name"),
    )
    item_links = op.create_table(
        "item_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(), nullable=True),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_item_links_item_id", "item_links", ["item_id"])

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, url FROM items WHERE url IS NOT NULL")).fetchall()
    links = []
    for item_id, url in rows:
        address = _web_address(url)
        if address:
            links.append({"item_id": item_id, "label": None, "url": address, "position": 0})
    if links:
        op.bulk_insert(item_links, links)

    with op.batch_alter_table("items") as batch_op:
        batch_op.drop_column("url")


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("items") as batch_op:
        batch_op.add_column(sa.Column("url", sa.String(), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT item_id, url FROM item_links ORDER BY item_id, position, id")).fetchall()
    first = {}
    for item_id, url in rows:
        first.setdefault(item_id, url)
    for item_id, url in first.items():
        conn.execute(sa.text("UPDATE items SET url = :url WHERE id = :id"), {"url": url, "id": item_id})

    op.drop_index("ix_item_links_item_id", table_name="item_links")
    op.drop_table("item_links")
    op.drop_table("link_labels")
