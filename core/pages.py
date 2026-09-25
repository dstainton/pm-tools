"""Windowed Confluence and SharePoint pages.

Same shape as the comment reader: a cutoff, caps, and an enabled switch.
A page body is not cut to the 180-character issue detail budget.
"""

import datetime as dt

from core import cache as cache_core
from core import model as model_core
from core import sources


DEFAULTS = {
    "enabled": True,
    "max_pages": 20,
    "excerpt_chars": 2000,
    "section_chars": 8000,
}


def settings(cfg):
    block = cfg.get("pages") if isinstance(cfg.get("pages"), dict) else {}
    out = dict(DEFAULTS)
    for key, default in DEFAULTS.items():
        if key not in block or block[key] is None:
            continue
        value = block[key]
        if key == "enabled":
            out[key] = bool(value)
            continue
        try:
            out[key] = max(0, int(value))
        except (TypeError, ValueError):
            out[key] = default
    return out


def _parse(value):
    text = str(value or "")[:10]
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        return None


def within_window(item, cutoff):
    if cutoff is None:
        return True
    when = _parse(item.get("watch") or "")
    if when is None:
        return True
    if isinstance(cutoff, dt.datetime):
        cutoff = cutoff.date()
    return when >= cutoff


def excerpt(text, limit):
    """Keep a whole word. The decision is usually not in the first line."""
    if not limit:
        return ""
    text = model_core.short_detail(text or "", 100000)
    if len(text) <= limit:
        return text
    cut = text[:limit].rstrip()
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut + "..."


def apply_excerpt(items, opts, cutoff=None):
    """Trim each page to the excerpt budget and drop pages outside the window."""
    if not opts["enabled"]:
        return []
    kept = []
    for item in items:
        if item.get("source") not in ("Confluence", "SharePoint"):
            kept.append(item)
            continue
        if not within_window(item, cutoff):
            continue
        detail = item.get("detail") or ""
        item["detail"] = excerpt(detail, opts["excerpt_chars"])
        item["excerpt_chars"] = opts["excerpt_chars"]
        kept.append(item)
        if len(kept) >= opts["max_pages"]:
            break
    return kept


def cache_fetch(cfg, kind, key_parts, fetch):
    """Fetch through the same cache `search_issues` uses, when one is attached."""
    store = (cfg.get("jira") or {}).get("_fetch_cache") or cfg.get("_fetch_cache")
    if store is None:
        return fetch()
    key = cache_core.cache_key(kind, *key_parts)
    hit = store.get(key)
    if hit is not None:
        return hit
    payload = fetch()
    try:
        store.put(key, payload)
    except OSError:
        pass
    return payload


def summary_key(page_id, version):
    return f"page:{page_id}:{version}"


def page_settings(cfg):
    """Page options including the keys added for the wider reader."""
    opts = settings(cfg)
    block = cfg.get("pages") if isinstance(cfg.get("pages"), dict) else {}
    opts["scope"] = block.get("scope") or "space"
    opts["follow_jira_links"] = block.get("follow_jira_links", True)
    confluence = cfg.get("confluence") if isinstance(cfg.get("confluence"), dict) else {}
    opts["content_types"] = list(confluence.get("content_types") or ["page", "blogpost"])
    opts["title_only_types"] = list(confluence.get("title_only_types") or ["database", "embed"])
    return opts


def normalise(raw, base_url, ws, window_start=None):
    """One Confluence search result as a report item."""
    page_id = str(raw.get("id") or "")
    kind_labels = [str(label).lower() for label in (ws.get("confluence_labels") or [])]
    labels = []
    for label in ((raw.get("metadata") or {}).get("labels") or {}).get("results") or []:
        name = label.get("name") if isinstance(label, dict) else str(label)
        if name:
            labels.append(name)
    if not labels:
        labels = list(raw.get("labels") or [])
    content_type = raw.get("type") or "page"
    title_only = content_type in ("database", "embed")
    body_html = ((raw.get("body") or {}).get("view") or {}).get("value") or ""
    if not body_html and raw.get("body_text"):
        body_html = raw["body_text"]
    version = raw.get("version") or {}
    updated = str(version.get("when") or raw.get("when") or "")[:10]
    created = str(((raw.get("history") or {}).get("createdDate") or ""))[:10]
    title = raw.get("title") or ""
    webui = (raw.get("_links") or {}).get("webui") or f"/pages/{page_id}"
    base = (base_url or "").rstrip("/")
    return {
        "source": "Confluence",
        "uid": f"confluence:{page_id or title}",
        "page_id": page_id,
        "ref": "",
        "type": content_type,
        "title_only": title_only,
        "title": title,
        "summary": title,
        "url": base + webui if webui.startswith("/") else webui,
        "space": ((raw.get("space") or {}).get("key") or raw.get("space") or ws.get("confluence_space") or ""),
        "labels": labels,
        "kind": next((label.lower() for label in labels if label.lower() in kind_labels), ""),
        "version": version.get("number") or 1,
        "updated": updated,
        "watch": updated,
        "updated_by": ((version.get("by") or {}).get("displayName") or ""),
        "created": created,
        "is_new": bool(window_start and created and created >= str(window_start)),
        "detail": "" if title_only else sources.strip_html(body_html, limit=2000),
        "ancestor_ids": [str(a.get("id")) for a in (raw.get("ancestors") or []) if isinstance(a, dict)],
        "workstream": ws.get("abbrev") or "",
    }


def excluded(page, cfg):
    """True for the tool's own published reports."""
    if "pm-report" in [str(label).lower() for label in (page.get("labels") or [])]:
        return True
    publish = ((cfg.get("publish") or {}).get("confluence") or {})
    parent = str(publish.get("parent_page") or "")
    if parent and parent in (page.get("ancestor_ids") or []):
        return True
    return False


def gather(cfg, ws, window):
    """Changed pages for one workstream."""
    opts = page_settings(cfg)
    if not opts["enabled"]:
        return []
    from core import filters
    types = opts["content_types"] + opts["title_only_types"]
    scope = "labelled" if opts["scope"] == "labelled" else "space"
    cql = filters.build_cql(ws, cfg, scope=scope, types=types)
    if not cql:
        return []
    start = (window or {}).get("start")
    since = start.isoformat() if start else None
    confluence = cfg.get("confluence") or {}
    _items, _idx = sources.fetch_confluence(confluence, cql, ws.get("abbrev") or "P", 1, since=since)
    pages = []
    for item in _items:
        if excluded(item, cfg):
            continue
        pages.append(item)
        if len(pages) >= opts["max_pages"]:
            break
    return pages


def map_to_epics(pages, epics_rows):
    """Rules 1–3: a mentioned key, then a label is not enough; key mention wins."""
    by_key = {row.get("key"): row for row in epics_rows if row.get("key")}
    for page in pages:
        text = f"{page.get('title') or ''} {page.get('detail') or ''}"
        mentioned = []
        for key in by_key:
            if key and key in text:
                mentioned.append(key)
        if len(mentioned) == 1:
            page["epic"] = mentioned[0]
            page["epic_match"] = "mention"
            by_key[mentioned[0]].setdefault("pages", []).append(page)
        else:
            page["epic"] = None
            page["epic_match"] = ""
    return pages
