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


def _page(cfg, entity):
    """Read an explicitly configured page by ID or by space and title."""
    page_id = entity.get("confluence_page_id")
    title = entity.get("confluence_page")
    space = entity.get("confluence_space") or (cfg.get("confluence") or {}).get("space")
    has_reference = bool(page_id or (title and space))
    if not has_reference:
        if title or entity.get("confluence_space"):
            return {"kind": "Confluence", "state": "configured",
                    "detail": "Confluence scope exists but has no resolvable page reference"}
        return {"kind": "Confluence", "state": "not configured"}
    reference = str(page_id) if page_id else "{} / {}".format(space, title)
    if not (cfg.get("confluence") or {}).get("base_url"):
        return {"kind": "Confluence", "state": "unavailable",
                "detail": "Confluence connection not configured", "reference": reference}
    try:
        if page_id:
            raw = sources.fetch_confluence_page(cfg, str(page_id))
        else:
            matches = sources.search_confluence_by_title(cfg, space, title)
            if len(matches) > 1:
                return {"kind": "Confluence", "state": "ambiguous",
                        "detail": "Multiple pages have this title; configure confluence_page_id",
                        "reference": reference}
            raw = matches[0] if matches else None
        if not raw:
            return {"kind": "Confluence", "state": "unavailable",
                    "detail": "Configured page not found or not accessible",
                    "reference": reference}
        body = ((raw.get("body") or {}).get("storage") or {}).get("value") or ""
        return {"kind": "Confluence", "state": "retrieved",
                "title": raw.get("title") or "Untitled",
                "reference": str(raw.get("id") or reference),
                "updated": ((raw.get("version") or {}).get("when") or "unknown"),
                "excerpt": _excerpt(body)}
    except Exception as exc:
        return {"kind": "Confluence", "state": "unavailable",
                "detail": "{}: {}".format(type(exc).__name__, exc),
                "reference": reference}


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
