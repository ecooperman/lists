import re
from typing import List, NamedTuple, Optional

# A bullet is a leading "-" - but not "--"/"---", which are separators in
# pasted notes rather than items.
_BULLET = re.compile(r"^-(?!-)\s*(.*)$")


class ParsedItem(NamedTuple):
    name: str
    description: Optional[str]


def parse_dash_list(text: str) -> List[ParsedItem]:
    """Turn pasted notes into items: every line starting with "-" is one
    item's name. Any non-dash lines that follow it are wrapped continuation
    text (e.g. a second line of the same note), so they go in that item's
    description rather than being lost or becoming items of their own.

    Text before the first dash, blank lines, separator lines like "---", and a
    bare "-" (and whatever trails it) are ignored. Runs of whitespace are collapsed to one space.
    """
    items: List[List] = []  # [name, [description lines]]
    current: Optional[List] = None

    for raw in text.splitlines():
        line = " ".join(raw.split())
        # Blank lines and dash-only separators ("--", "---") carry no content.
        if not line or set(line) == {"-"} and len(line) > 1:
            continue
        match = _BULLET.match(line)
        if match:
            name = match.group(1)
            current = [name, []] if name else None
            if current is not None:
                items.append(current)
        elif current is not None:
            current[1].append(line)

    return [ParsedItem(name, "\n".join(desc) or None) for name, desc in items]
