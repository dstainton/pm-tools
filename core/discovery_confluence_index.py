"""Index authorized Confluence page bodies into the existing offline FTS store.

A page may only be fetched after bounded scoped inventory has established its
membership. Completeness is inherited from that inventory, never inferred from
the number of pages successfully indexed.
"""
import html
import re
import sqlite3
from html.parser import HTMLParser

from core import discovery_fts, discovery_inventory, sources


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "br", "h1", "h2", "h3", "h4", "li", "tr"):
            self.parts.append("\n")


def _text(storage):
    parser = _Text()
    parser.feed(storage or "")
    return " ".join(" ".join(parser.parts).split())


def index(cfg, db_path, cap=100):
    """Fetch scoped pages, index independently, and report failures explicitly."""
    report = {}
    discovery_inventory.build(cfg, report, cap=cap)
    inventory = report["inventory"]
    db = sqlite3.connect(str(db_path))
    indexed = changed = 0
    errors = []
    try:
        discovery_fts._init(db)
        for page in inventory["pages"]:
            pid = page["id"]
            try:
                fetched = sources.fetch_confluence_page(cfg, pid)
                if not fetched:
                    raise ValueError("Page not accessible")
                actual = (fetched.get("space") or {}).get("key")
                if actual and page["space"] and actual != page["space"]:
                    raise ValueError("Page space changed after inventory")
                space = actual or page["space"]
                body = _text(((fetched.get("body") or {}).get("storage") or {}).get("value"))
                version = (fetched.get("version") or {}).get("when")
                title = fetched.get("title") or page["title"]
                with db:
                    changed += int(discovery_fts._put(
                        db, "confluence:page:" + pid, pid, space, "confluence_page",
                        (fetched.get("history") or {}).get("createdDate"), version,
                        title, body, "confluence:" + pid, source="confluence"))
                indexed += 1
            except Exception as exc:
                errors.append({"id": pid, "detail": "{}: {}".format(
                    type(exc).__name__, str(exc)[:160])})
        return {"indexed": indexed, "changed": changed,
                "inventory_coverage": inventory["coverage"],
                "scopes": inventory["scopes"], "errors": errors,
                "complete": inventory["coverage"] == "complete" and not errors}
    finally:
        db.close()
