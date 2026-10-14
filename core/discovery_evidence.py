"""Bounded, read-only evidence for product/workstream discovery.

Evidence is not an accepted definition of responsibility. No model calls.
"""
import datetime as dt
import re

from core import queries, sources, workstreams

MAX_EPICS = 8
MAX_EXCERPT = 320


def _excerpt(text):
    text = re.sub(r"<[^>]+>", " ", str(text or ""))
    return " ".join(text.split())[:MAX_EXCERPT]


def _page_ref(cfg, entity):
    page_id = entity.get("confluence_page_id")
    if not page_id:
        return None
    return str(page_id)


def _page(cfg, entity):
    page_id = _page_ref(cfg, entity)
    if not page_id:
        return {"kind": "Confluence", "state": "not configured"}
    if not (cfg.get("confluence") or {}).get("base_url"):
        return {"kind": "Confluence", "state": "unavailable",
                "detail": "Confluence connection not configured", "reference": page_id}
    try:
        raw = sources.fetch_confluence_page(cfg, page_id)
        if not raw:
            return {"kind": "Confluence", "state": "unavailable",
                    "detail": "Page was not found or could not be read",
                    "reference": page_id}
        body = ((raw.get("body") or {}).get("storage") or {}).get("value") or ""
        return {"kind": "Confluence", "state": "retrieved",
                "title": raw.get("title") or "Untitled",
                "reference": str(raw.get("id") or page_id),
                "updated": ((raw.get("version") or {}).get("when") or "unknown"),
                "excerpt": _excerpt(body)}
    except Exception as exc:
        return {"kind": "Confluence", "state": "unavailable",
                "detail": "{}: {}".format(type(exc).__name__, exc),
                "reference": page_id}


def _epics(cfg, ws):
    selector = workstreams.epic_selector_jql(cfg, ws)
    if not selector:
        return {"kind": "Jira Epics", "state": "not configured",
                "detail": "No usable component, label, or field anchor"}
    try:
        # A bounded example, not a complete Epic inventory.
        raw = sources.search_issues(
            cfg["jira"], selector, fields=["summary", "updated", "issuetype"],
            max_items=MAX_EPICS)
        rows = []
        for item in raw[:MAX_EPICS]:
            fields = item.get("fields") or {}
            rows.append({"key": item.get("key") or "unknown",
                         "title": _excerpt(fields.get("summary")),
                         "updated": fields.get("updated") or "unknown"})
        return {"kind": "Jira Epics", "state": "retrieved", "items": rows,
                "limit": MAX_EPICS,
                "detail": "Up to {} matching Epics sampled; not exhaustive".format(MAX_EPICS)}
    except Exception as exc:
        return {"kind": "Jira Epics", "state": "unavailable",
                "detail": "{}: {}".format(type(exc).__name__, exc)}


def enrich(cfg, report):
    """Add sourced examples to the discovered entities; keep unknowns unknown."""
    products_by_key = {p["abbrev"]: p for p in (cfg.get("products") or [])}
    streams_by_key = {w["abbrev"]: w for w in (cfg.get("workstreams") or [])}
    report["coverage"] = "configured facts, optional configured Confluence pages, and bounded Jira Epic samples"
    report["enriched"] = True
    report["retrieved_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    for product in report["products"]:
        raw = products_by_key.get(product["abbrev"])
        product["evidence"] = [_page(cfg, raw)] if raw else [
            {"kind": "Confluence", "state": "not configured"}]
    for ws in report["workstreams"]:
        raw = streams_by_key.get(ws["abbrev"])
        if raw:
            ws["evidence"] = [_page(cfg, raw), _epics(cfg, raw)]
    return report
