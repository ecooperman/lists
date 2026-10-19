import re
from typing import List, Optional

# A bullet is a leading "-" - but not "--"/"---", which are separators in
# pasted notes rather than items.
_BULLET = re.compile(r"^-(?!-)\s*(.*)$")


def parse_dash_list(text: str) -> List[str]:
    """Turn pasted notes into item names: every line starting with "-"
    starts a new item. Any non-dash lines that follow are treated as the same
    item wrapped onto another line (a stray line break from copy/paste or a
    notes app), so they're joined onto its name with a single space.

    Text before the first dash, blank lines, separator lines like "---", and a
    bare "-" (and whatever trails it) are ignored. Runs of whitespace are
    collapsed to one space.
    """
    items: List[List[str]] = []  # each item is its name's pieces, joined at the end
    current: Optional[List[str]] = None

    for raw in text.splitlines():
        line = " ".join(raw.split())
        # Blank lines and dash-only separators ("--", "---") carry no content.
        if not line or set(line) == {"-"} and len(line) > 1:
            continue
        match = _BULLET.match(line)
        if match:
            name = match.group(1)
            current = [name] if name else None
            if current is not None:
                items.append(current)
        elif current is not None:
            current.append(line)

    return [" ".join(parts) for parts in items]
