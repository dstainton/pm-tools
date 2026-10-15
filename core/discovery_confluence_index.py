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


def _blogs(cfg, inventory, cap):
    """Blog posts are space-scoped, never discovered from a page-tree scope."""
    results = []
    status = []
    spaces = sorted({scope["space"] for scope in inventory["scopes"]
                     if scope.get("type") == "space" and scope.get("space")})
    for space in spaces:
        start = 0
        state = {"space": space, "type": "blogpost", "status": "complete"}
        try:
            while start < cap:
                rows, more = sources.list_confluence_inventory(
                    cfg, space, start=start, limit=min(25, cap - start),
                    content_types=["blogpost"])
                if not rows:
                    if more:
                        state["status"] = "incomplete"
                        state["detail"] = "Empty blog search page with continuation"
                    break
                for page in rows:
                    results.append({"id": str(page["id"]), "space": space,
                                    "title": page.get("title") or "",
                                    "type": "blogpost"})
                start += len(rows)
                if not more:
                    break
                if start >= cap:
                    state["status"] = "truncated"
                    state["detail"] = "Blog posts beyond per-space cap"
                    break
        except Exception as exc:
            state["status"] = "unavailable"
            state["detail"] = "{}: {}".format(type(exc).__name__, str(exc)[:160])
        status.append(state)
    return results, status


def _comments(cfg, db, parent_id, space, parent_title, cap):
    """Index direct comments with per-parent bounded pagination and citations."""
    start = updated = count = 0
    while start < cap:
        rows, more = sources.list_confluence_comments(
            cfg, parent_id, start=start, limit=min(25, cap - start))
        if not rows:
            if more:
                return count, updated, "Empty comment page with continuation"
            return count, updated, None
        for comment in rows:
            cid = str(comment.get("id") or "")
            if not cid:
                return count, updated, "Comment response has no ID"
            body = _text(((comment.get("body") or {}).get("storage") or {}).get("value"))
            if not body:
                # Empty comments still have a valid observation.
                body = ""
            when = (comment.get("version") or {}).get("when")
            with db:
                updated += int(discovery_fts._put(
                    db, "confluence:comment:" + cid, cid, space,
                    "confluence_comment",
                    (comment.get("history") or {}).get("createdDate"), when,
                    parent_title + " comment " + cid, body,
                    "confluence:" + parent_id + "#comment-" + cid,
                    source="confluence"))
            count += 1
        start += len(rows)
        if not more:
            return count, updated, None
        if start >= cap:
            return count, updated, "Comments beyond per-parent cap"
    return count, updated, "Comments beyond per-parent cap"


def index(cfg, db_path, cap=100):
    """Fetch scoped pages, index independently, and report failures explicitly."""
    report = {}
    discovery_inventory.build(cfg, report, cap=cap)
    inventory = report["inventory"]
    blogs, blog_scopes = _blogs(cfg, inventory, cap)
    db = sqlite3.connect(str(db_path))
    indexed = changed = comments_indexed = comments_changed = 0
    errors = []
    try:
        discovery_fts._init(db)
        pages = inventory["pages"] + blogs
        for page in pages:
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
                labels = ((fetched.get("metadata") or {}).get("labels") or {}).get("results") or []
                names = [label.get("name") for label in labels
                         if isinstance(label, dict) and label.get("name")]
                body = " ".join(filter(None, [body, " ".join(names)]))
                version = (fetched.get("version") or {}).get("when")
                title = fetched.get("title") or page["title"]
                with db:
                    changed += int(discovery_fts._put(
                        db, "confluence:" + page.get("type", "page") + ":" + pid,
                        pid, space, "confluence_" + page.get("type", "page"),
                        (fetched.get("history") or {}).get("createdDate"), version,
                        title, body, "confluence:" + pid, source="confluence"))
                indexed += 1
                try:
                    found, modified, limitation = _comments(
                        cfg, db, pid, space, title, cap)
                    comments_indexed += found
                    comments_changed += modified
                    if limitation:
                        errors.append({"id": pid, "detail": limitation})
                except Exception as exc:
                    errors.append({"id": pid, "detail": "Comments unavailable: {}: {}".format(
                        type(exc).__name__, str(exc)[:160])})
            except Exception as exc:
                errors.append({"id": pid, "detail": "{}: {}".format(
                    type(exc).__name__, str(exc)[:160])})
        return {"indexed": indexed, "changed": changed,
                "comments_indexed": comments_indexed, "comments_changed": comments_changed,
                "inventory_coverage": inventory["coverage"],
                "scopes": inventory["scopes"] + blog_scopes, "errors": errors,
                "complete": inventory["coverage"] == "complete" and not errors
                and all(s["status"] == "complete" for s in blog_scopes)}
    finally:
        db.close()
