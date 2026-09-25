"""Turn model citation tags into links, and drop tags that were not in the material."""

import re


_KEY = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")
_BRACKET = re.compile(
    r"\[((?:[A-Z][A-Z0-9]+-\d+|D\d+)"
    r"(?:\s*,\s*(?:[A-Z][A-Z0-9]+-\d+|D\d+))*)\]")


def _cut(title, limit=60):
    text = (title or "").strip()
    if len(text) <= limit:
        return text
    clipped = text[:limit].rsplit(" ", 1)[0].strip()
    return clipped or text[:limit].strip()


def assign_doc_tags(docs):
    """Give each doc a D-tag, numbered by page id ascending. Returns the docs."""
    def page_key(doc):
        raw = str(doc.get("page_id") or doc.get("uid") or "")
        digits = "".join(ch for ch in raw if ch.isdigit())
        return (int(digits) if digits else 0, raw)

    ordered = sorted(docs, key=page_key)
    for number, doc in enumerate(ordered, 1):
        doc["ref"] = f"D{number}"
    return docs


def citation_map(items):
    """{tag: (label, url)}. Jira: (key, url). Docs: (title cut to 60, url)."""
    mapped = {}
    for item in items:
        tag = item.get("ref") or ""
        if not tag:
            continue
        url = item.get("url") or ""
        if item.get("source") == "Jira":
            mapped[tag] = (item.get("key") or tag, url)
        else:
            title = item.get("summary") or item.get("title") or tag
            mapped[tag] = (_cut(title), url)
    return mapped


def resolve(text, cmap):
    """Return (new_text, removed_count). Rewrite bracketed tags to links.

    A tag that is not in cmap is removed and counted. A key-looking word
    outside brackets is left alone. Comma lists inside one bracket become
    one link per tag.
    """
    removed = 0

    def repl(match):
        nonlocal removed
        links = []
        for part in match.group(1).split(","):
            tag = part.strip()
            if tag in cmap:
                label, url = cmap[tag]
                links.append(f"[{label}]({url})" if url else label)
            else:
                removed += 1
        return ", ".join(links)

    return _BRACKET.sub(repl, text or ""), removed


def is_issue_key(value):
    return bool(_KEY.match(str(value or "")))
