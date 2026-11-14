"""A list (or one item) rendered as a copy to paste somewhere else.

This is "Send a copy" in the app's vocabulary: a one-time snapshot, in contrast
to sharing access. The same text and rich version are what a copy to the
clipboard puts there and what an email would carry later, so the layout choices
live here once. Only what the person ticked is included, and never anything
about who the list is shared with or the owner's contacts beyond a name.
"""
from html import escape
from urllib.parse import urlsplit
from typing import List, Optional

from . import models, schemas

DONE_NOTE = "(done)"


def _contact_name(contact) -> str:
    return " ".join(part for part in (contact.first_name, contact.last_name) if part)


def _date(value) -> str:
    return f"{value:%b} {value.day}, {value.year}"


def _money(cents: int) -> str:
    """$1,234.50, or $750 when there are no cents."""
    return f"${cents // 100:,}" if cents % 100 == 0 else f"${cents / 100:,.2f}"


def _totals(items: List[models.Item], options: schemas.CopyOptions, priority_labels: List[str]):
    """The closing lines of a copy that includes prices, as (label, value) pairs - the same figures the
    list's totals strip shows. Each counted item is at its final cost or else its estimate; items the
    list has left out of its totals are not counted (the Total says how many). When any counted item has
    a priority there is a line per priority first (highest level first, "No priority" last), then the
    Total. Empty when prices are off, only one item is copied, or none of the counted ones has a price."""
    if not options.prices or len(items) < 2:  # one item's own Price line already says it
        return []
    counted = [item for item in items if not item.exclude_from_totals]
    left_out = len(items) - len(counted)
    costs = [item.cost_cents for item in counted]
    if all(cost is None for cost in costs):
        return []
    missing = sum(1 for cost in costs if cost is None)
    notes = []
    if missing:
        notes.append(f"{missing} without a price")
    if left_out:
        notes.append(f"{left_out} left out")
    note = f" ({', '.join(notes)})" if notes else ""

    by_priority = {}
    for item in counted:
        if item.cost_cents is not None:
            by_priority[item.priority] = by_priority.get(item.priority, 0) + item.cost_cents
    rows = []
    if any(priority for priority in by_priority):
        for priority in sorted(by_priority, key=lambda level: -(level or 0)):
            if by_priority[priority]:
                label = priority_labels[priority - 1] if priority else "No priority"
                rows.append((label, _money(by_priority[priority])))
    rows.append(("Total", f"{_money(sum(cost for cost in costs if cost is not None))}{note}"))
    return rows


def _details(item: models.Item, options: schemas.CopyOptions, priority_labels: List[str]):
    """What to show under an item's name, in order, as (kind, label, value):
    "note" (free text), "link" (label may be None; value is the address) and
    "field" (a short label: value line)."""
    rows = []
    if options.description and item.description and item.description.strip():
        rows.append(("note", None, item.description.strip()))
    if options.links:
        rows.extend(("link", link.label, link.url) for link in item.links)
    if options.prices and item.cost_cents is not None:
        left_out = " (left out of the total)" if item.exclude_from_totals else ""
        rows.append(("field", "Price", f"{_money(item.cost_cents)}{left_out}"))
    if options.needed_by and item.needed_by:
        rows.append(("field", "Needed by", _date(item.needed_by)))
    if options.priority and item.priority:
        rows.append(("field", "Priority", priority_labels[item.priority - 1]))
    if options.progress and item.progress and not item.done:
        rows.append(("field", "Progress", f"{item.progress}%"))
    if options.recipient and item.recipient is not None:
        rows.append(("field", "For", _contact_name(item.recipient)))
    return rows


def _chosen(items: List[models.Item], options: schemas.CopyOptions) -> List[models.Item]:
    chosen = [item for item in items if not (options.done == "hide" and item.done)]
    if options.order == "priority":
        # Stable: ties (and unprioritised items) keep the list's own order, and done items stay last.
        chosen = sorted(chosen, key=lambda item: (item.done, -(item.priority or 0)))
    return chosen


def _marker(options: schemas.CopyOptions, item: models.Item, number: int) -> str:
    if options.style == "numbered":
        return f"{number}."
    if options.style == "bulleted":
        return "-"
    if options.style == "checkboxes":
        return "☑" if item.done else "☐"
    return ""


def _text(title: Optional[str], items, options, priority_labels) -> str:
    entries = [(item, _details(item, options, priority_labels)) for item in items]
    # Items with details get a blank line between them so each reads as a block.
    spaced = any(rows for _, rows in entries)
    blocks = []
    for number, (item, rows) in enumerate(entries, start=1):
        marker = _marker(options, item, number)
        name = item.name + (f" {DONE_NOTE}" if item.done and options.done == "strike" else "")
        lines = [f"{marker} {name}" if marker else name]
        indent = " " * (len(marker) + 1) if marker else ""
        for kind, label, value in rows:
            if kind == "note":
                lines.extend(f"{indent}{part}" for part in value.splitlines() if part.strip())
            elif kind == "link":
                lines.append(f"{indent}{label}: {value}" if label else f"{indent}{value}")
            else:
                lines.append(f"{indent}{label}: {value}")
        blocks.append("\n".join(lines))
    body = ("\n\n" if spaced else "\n").join(blocks) if blocks else "(no items)"
    totals = _totals(items, options, priority_labels)
    if totals:
        body += "\n\n" + "\n".join(f"{label}: {value}" for label, value in totals)
    return f"{title}\n\n{body}" if title else body


def _site_name(url: str) -> str:
    """What to show for a link with no label in the rich version: the site
    ("opentable.com"), since the address itself can run to several lines. The
    plain text keeps the full address, and the link underneath is always it."""
    host = (urlsplit(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host or url


def _html_item(item: models.Item, rows, options) -> str:
    name = escape(item.name)
    if item.done and options.done == "strike":
        name = f"<s>{name}</s>"
    parts = [f"<strong>{name}</strong>"]
    if options.style == "checkboxes":
        parts.insert(0, "☑ " if item.done else "☐ ")
    for kind, label, value in rows:
        if kind == "note":
            parts.append("<br>" + "<br>".join(escape(part) for part in value.splitlines() if part.strip()))
        elif kind == "link":
            parts.append(f'<br><a href="{escape(value)}">{escape(label or _site_name(value))}</a>')
        else:
            parts.append(f"<br>{escape(label)}: {escape(value)}")
    return "".join(parts)


def _html(title: Optional[str], items, options, priority_labels) -> str:
    out = [f"<h3>{escape(title)}</h3>"] if title else []
    if not items:
        out.append("<p>(no items)</p>")
        return "".join(out)
    rendered = [_html_item(item, _details(item, options, priority_labels), options) for item in items]
    if options.style in ("numbered", "bulleted"):
        tag = "ol" if options.style == "numbered" else "ul"
        out.append(f"<{tag}>" + "".join(f"<li>{block}</li>" for block in rendered) + f"</{tag}>")
    else:
        # Checkboxes carry their own symbol, and plain has none: no list markers.
        out.append("".join(f"<p>{block}</p>" for block in rendered))
    totals = _totals(items, options, priority_labels)
    if totals:
        # The closing Total is bold; the priority lines above it are plain.
        lines = [
            f"<strong>{escape(label)}:</strong> {escape(value)}" if label == "Total" else f"{escape(label)}: {escape(value)}"
            for label, value in totals
        ]
        out.append("<p>" + "<br>".join(lines) + "</p>")
    return "".join(out)


def email_message(sender: str, list_name: str, result: schemas.CopyResult):
    """(subject, text, html) for emailing a rendered copy. The copy itself is
    what the sender previewed; a short note after it says who it is from, that
    replies go to them, and that it is a one-time snapshot - so a stranger
    knows why it arrived. Everything put into the HTML is escaped."""
    note = (
        f"Sent by {sender} using Lists. Reply to this email to reach them. "
        "This is a one-time copy and won't change if the list does."
    )
    subject = f'{sender} sent you a copy of "{list_name}"'
    text = f"{result.text}\n\n--\n{note}\n"
    html = (
        '<div style="font-family: -apple-system, Segoe UI, Helvetica, Arial, sans-serif; font-size: 15px; line-height: 1.5;">'
        f"{result.html}"
        '<hr style="border: none; border-top: 1px solid #ddd; margin-top: 24px;">'
        f'<p style="color: #666; font-size: 12px;">{escape(note)}</p>'
        "</div>"
    )
    return subject, text, html


def render(
    title: Optional[str], items: List[models.Item], options: schemas.CopyOptions, priority_labels: List[str]
) -> schemas.CopyResult:
    """`items` in the order the list shows them; `title` is None for no heading."""
    chosen = _chosen(items, options)
    return schemas.CopyResult(
        text=_text(title, chosen, options, priority_labels),
        html=_html(title, chosen, options, priority_labels),
        count=len(chosen),
    )
