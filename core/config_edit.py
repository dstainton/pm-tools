"""Comment-preserving edits to a top-level YAML list (products, workstreams).

`pm products add` / `remove` and `pm workstreams add` / `remove` rewrite the
config file in place. These helpers find the named list, insert or cut one
entry, and leave every comment and every other setting where the author put
it. The caller still validates the result before it replaces the file.
"""

import re


TOP_LEVEL = re.compile(r"^[A-Za-z_][\w-]*:")
ITEM_RE = re.compile(r"^(\s*)-\s")
ABBREV_RE = re.compile(r"""abbrev:\s*["']?([\w-]+)""")


def read_lines(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read().splitlines()


def find_block(lines, key):
    """Locate a top-level list: (header index, end index exclusive)."""
    header = re.compile(rf"^{re.escape(key)}:\s*(#.*)?$")
    start = None
    for n, line in enumerate(lines):
        if header.match(line):
            start = n
            break
    if start is None:
        return None, None

    end = len(lines)
    for n in range(start + 1, len(lines)):
        if TOP_LEVEL.match(lines[n]):
            end = n
            break
    return start, end


def items(lines, start, end):
    """Split the list body into (abbrev, first line, last line) per entry."""
    found, current, indent = [], None, None
    for n in range(start + 1, end):
        match = ITEM_RE.match(lines[n])
        if match:
            if current is not None:
                found.append((current[0], current[1], n - 1))
            current, indent = [None, n], match.group(1)
        elif current is not None and lines[n].strip() and \
                not lines[n].startswith((indent or "") + " "):
            found.append((current[0], current[1], n - 1))
            current = None
        if current is not None:
            abbrev = ABBREV_RE.search(lines[n])
            if abbrev:
                current[0] = abbrev.group(1)
    if current is not None:
        found.append((current[0], current[1], end - 1))
    return found


def ensure_block(text, key, before_key=None):
    """Return `text` with a top-level `key:` list, creating it if needed."""
    lines = text.splitlines()
    start, _end = find_block(lines, key)
    if start is not None:
        return text if text.endswith("\n") else text + "\n"

    insert_at = len(lines)
    if before_key:
        before, _ = find_block(lines, before_key)
        if before is not None:
            insert_at = before
            while insert_at > 0 and not lines[insert_at - 1].strip():
                insert_at -= 1

    block = ["", f"{key}:", ""]
    return "\n".join(lines[:insert_at] + block + lines[insert_at:]) + "\n"


def add_list_entry(text, key, entry, render, before_key=None, create=False):
    """Append one mapping (with an `abbrev`) to the named top-level list.

    `create=True` inserts an empty `key:` block when the file does not have
    one yet (used for `products:`, which older configs omit). Workstreams
    must already be present — a missing list is a config problem, not
    something to silently invent.
    """
    if create:
        text = ensure_block(text, key, before_key=before_key)
    lines = text.splitlines()
    start, end = find_block(lines, key)
    if start is None:
        raise ValueError(f"no top-level `{key}:` list found in the config")

    existing = items(lines, start, end)
    abbrev = entry.get("abbrev") or ""
    for found, _first, _last in existing:
        if found and found.lower() == abbrev.lower():
            raise ValueError(f"a {key[:-1]} with abbrev {found} already exists")

    indent = "  "
    if existing:
        indent = re.match(r"^(\s*)-", lines[existing[0][1]]).group(1)

    insert_at = end
    while insert_at - 1 > start and (not lines[insert_at - 1].strip()
                                     or lines[insert_at - 1].lstrip()
                                     .startswith("#")):
        insert_at -= 1

    rendered = render(entry, indent)
    block = [""] + rendered if existing else rendered
    return "\n".join(lines[:insert_at] + block + lines[insert_at:]) + "\n"


def remove_list_entry(text, key, abbrev):
    """Return `text` with the named entry removed from the list."""
    lines = text.splitlines()
    start, end = find_block(lines, key)
    if start is None:
        raise ValueError(f"no top-level `{key}:` list found in the config")

    for found, first, last in items(lines, start, end):
        if found and found.lower() == abbrev.lower():
            cut_to = last + 1
            if cut_to < end and not lines[cut_to].strip():
                cut_to += 1
            return "\n".join(lines[:first] + lines[cut_to:]) + "\n"

    raise ValueError(f"no {key[:-1]} with abbrev {abbrev} in the config")
