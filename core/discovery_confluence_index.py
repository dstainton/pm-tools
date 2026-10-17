"""Index authorized Confluence page bodies into the existing offline FTS store.

A page may only be fetched after bounded scoped inventory has established its
membership. Completeness is inherited from that inventory, never inferred from
the number of pages successfully indexed.
"""
import html
import re
import sqlite3
from html.parser import HTMLParser

from core import discovery_fts, discovery_inventory, discovery_confluence_checkpoint, sources


def _single_scoped_project(cfg, inventory):
    """Map a dedicated page-tree scope to its sole configured Jira project.

    Never apply this to whole-space searches or multi-project configurations,
    where membership cannot be safely inferred.
    """
    scopes = [row.get("scope", row) for row in inventory.get("scopes") or []]
    if not scopes or any(scope.get("type") != "page_tree" for scope in scopes):
        return None
    projects = set()
    jira = (cfg.get("jira") or {}).get("project")
    if jira:
        projects.add(str(jira))
    for entry in (cfg.get("products") or []) + (cfg.get("workstreams") or []):
        project = entry.get("project") or entry.get("jira_project")
        if project:
            projects.add(str(project))
    return next(iter(projects)) if len(projects) == 1 else None


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


def _comments(cfg, db, parent_id, space, parent_title, cap, project=None):
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
                    db, "confluence:comment:" + cid, cid, project or space,
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



def _published_v2_fallback(cfg, page_id):
    """Classify a v1 404 without ever indexing unpublished draft content.

    Returns (published_v1_shaped_page_or_None, status). A draft lookup is
    metadata-only and happens only if no current page was returned.
    """
    page = sources.fetch_confluence_page_v2(cfg, page_id, body_format="storage")
    if page is not None:
        status = str(page.get("status") or "").lower()
        if status == "draft":
            return None, "draft"
        if status != "current":
            raise ValueError("Confluence v2 page status is {!r}, not current".format(
                status or "missing"))
        storage = ((page.get("body") or {}).get("storage") or {})
        if not isinstance(storage, dict) or not isinstance(storage.get("value"), str):
            raise ValueError("Confluence v2 current page has no readable storage body")
        v2_version = page.get("version") or {}
        labels = page.get("labels") or {}
        # Normalize only fields used by the indexer; the Confluence tree
        # inventory has already established page membership in its space.
        normalized = {
            "id": str(page_id), "status": "current",
            "title": page.get("title") or "",
            "body": {"storage": storage},
            "history": {"createdDate": page.get("createdAt")},
            "version": {"when": v2_version.get("createdAt")},
            "metadata": {"labels": {
                "results": labels.get("results") or []}},
        }
        return normalized, "current"

    draft = sources.fetch_confluence_page_v2(cfg, page_id, get_draft=True)
    if draft is not None and str(draft.get("status") or "").lower() == "draft":
        return None, "draft"
    raise ValueError(
        "Page unavailable in Confluence v1 and v2; draft status not confirmed")


def index(cfg, db_path, cap=100, use_checkpoint="auto"):
    """Index pages in authorized scopes, preferring persisted crawl checkpoints.

    A complete checkpoint allows indexing all collected pages, not just the
    first cap search rows. Incomplete checkpoints remain partial, never
    falsely declared complete. Without a checkpoint the original bounded
    metadata inventory remains available for compatibility.
    """
    report = {}
    checkpoint = None
    if use_checkpoint is not False:
        checkpoint = discovery_confluence_checkpoint.indexed_inventory(cfg, db_path)
    checkpoint_found = bool(checkpoint and any(
        scope.get("status") in ("complete", "incomplete")
        for scope in checkpoint["scopes"]))
    if use_checkpoint is True or (use_checkpoint == "auto" and checkpoint_found):
        inventory = checkpoint
        inventory_mode = "checkpoint"
    else:
        discovery_inventory.build(cfg, report, cap=cap)
        inventory = report["inventory"]
        inventory_mode = "bounded"
    project_assignment = _single_scoped_project(cfg, inventory)
    blogs, blog_scopes = _blogs(cfg, inventory, cap)
    db = sqlite3.connect(str(db_path))
    indexed = changed = comments_indexed = comments_changed = 0
    errors = []
    drafts_skipped = []
    v2_fallbacks = []
    try:
        discovery_fts._init(db)
        pages = inventory["pages"] + blogs
        for page in pages:
            pid = page["id"]
            try:
                fetched = sources.fetch_confluence_page(cfg, pid)
                if not fetched:
                    fetched, status = _published_v2_fallback(cfg, pid)
                    if inventory_mode == "checkpoint":
                        with db:
                            db.execute("""UPDATE confluence_inventory_items SET status=?
                                WHERE content_id=?""", (status, str(pid)))
                    if status == "draft":
                        drafts_skipped.append({"id": pid, "title": page.get("title") or pid})
                        continue
                    v2_fallbacks.append({"id": pid, "title": page.get("title") or pid})
                if str(fetched.get("status") or "").lower() == "draft":
                    drafts_skipped.append({"id": pid, "title": page.get("title") or pid})
                    continue
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
                        pid, project_assignment or space, "confluence_" + page.get("type", "page"),
                        (fetched.get("history") or {}).get("createdDate"), version,
                        title, body, "confluence:" + pid, source="confluence"))
                indexed += 1
                try:
                    found, modified, limitation = _comments(
                        cfg, db, pid, space, title, cap, project=project_assignment)
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
                "inventory_mode": inventory_mode,
                "project_assignment": project_assignment or "Confluence space",
                "comments_indexed": comments_indexed, "comments_changed": comments_changed,
                "inventory_coverage": inventory["coverage"],
                "scopes": inventory["scopes"] + blog_scopes, "errors": errors,
                "drafts_skipped": drafts_skipped, "v2_fallbacks": v2_fallbacks,
                "complete": inventory["coverage"] == "complete" and not errors
                and all(s["status"] == "complete" for s in blog_scopes)}
    finally:
        db.close()
