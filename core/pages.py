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
