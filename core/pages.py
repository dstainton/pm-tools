"""Windowed Confluence and SharePoint pages.

Same shape as the comment reader: a cutoff, caps, and an enabled switch.
A page body is not cut to the 180-character issue detail budget.
"""

import datetime as dt
import re

from core import cache as cache_core
from core import model as model_core
from core import sources


_KEY = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
_PAGE_ID = re.compile(r"(?:pageId=|/pages/)(\d+)")


DEFAULTS = {
    "enabled": True,
    "scope": "space",
    "follow_jira_links": True,
    "max_pages": 20,
    "excerpt_chars": 2000,
    "section_chars": 8000,
    "summaries": True,
    "summary_chars": 6000,
    "max_summaries": 20,
    "match_epics_with_model": True,
}

_BOOLS = {"enabled", "follow_jira_links", "summaries", "match_epics_with_model"}
_INTS = {"max_pages", "excerpt_chars", "section_chars", "summary_chars", "max_summaries"}


def settings(cfg):
    block = cfg.get("pages") if isinstance(cfg.get("pages"), dict) else {}
    out = dict(DEFAULTS)
    for key, default in DEFAULTS.items():
        if key not in block or block[key] is None:
            continue
        value = block[key]
        if key in _BOOLS:
            out[key] = bool(value)
        elif key in _INTS:
            try:
                out[key] = max(0, int(value))
            except (TypeError, ValueError):
                out[key] = default
        else:
            out[key] = value
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
        detail = item.get("detail") or item.get("body_text") or ""
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
    confluence = cfg.get("confluence") if isinstance(cfg.get("confluence"), dict) else {}
    opts["content_types"] = list(confluence.get("content_types") or ["page", "blogpost"])
    opts["title_only_types"] = list(confluence.get("title_only_types") or ["database", "embed"])
    return opts


def _labels(raw):
    labels = []
    for label in ((raw.get("metadata") or {}).get("labels") or {}).get("results") or []:
        name = label.get("name") if isinstance(label, dict) else str(label)
        if name:
            labels.append(name)
    if not labels:
        labels = [str(label) for label in (raw.get("labels") or []) if label]
    return labels


def project_keys(cfg):
    keys = []
    jira = cfg.get("jira") or {}
    if jira.get("project"):
        keys.append(str(jira["project"]))
    for ws in cfg.get("workstreams") or []:
        if ws.get("project") and ws["project"] not in keys:
            keys.append(str(ws["project"]))
    return keys


def normalise(raw, base_url, ws=None, product=None, projects=None,
              window_start=None, opts=None):
    """One Confluence search result as a page record."""
    ws = ws or {}
    opts = opts or {}
    page_id = str(raw.get("id") or "")
    kind_labels = [str(label).lower() for label in (ws.get("confluence_labels") or [])]
    labels = _labels(raw)
    content_type = raw.get("type") or "page"
    title_only_types = set(opts.get("title_only_types") or ("database", "embed"))
    title_only = content_type in title_only_types
    body = raw.get("body") or {}
    view_html = (body.get("view") or {}).get("value") or ""
    storage_html = (body.get("storage") or {}).get("value") or raw.get("storage") or ""
    raw_html = view_html or storage_html
    if not raw_html and raw.get("body_text"):
        raw_html = raw["body_text"]
    version = raw.get("version") if isinstance(raw.get("version"), dict) else {}
    updated = str(version.get("when") or raw.get("when") or "")[:10]
    created = str(((raw.get("history") or {}).get("createdDate") or raw.get("created") or ""))[:10]
    title = raw.get("title") or ""
    webui = (raw.get("_links") or {}).get("webui") or f"/pages/{page_id}"
    base = (base_url or "").rstrip("/")
    limit = int(opts.get("summary_chars") or 6000)
    start = str(window_start)[:10] if window_start else ""
    projects = [str(p) for p in (projects or [])]
    blob = f"{title}\n{raw_html}"
    keys = []
    for key in _KEY.findall(blob):
        prefix = key.split("-", 1)[0]
        if projects and prefix not in projects:
            continue
        if key not in keys:
            keys.append(key)
    ancestors = [a for a in (raw.get("ancestors") or []) if isinstance(a, dict)]
    return {
        "source": "Confluence",
        "uid": f"confluence:{page_id or title}",
        "page_id": page_id,
        "ref": "",
        "type": content_type,
        "title_only": title_only,
        "title": title,
        "url": (base + webui) if webui.startswith("/") else (webui or ""),
        "space": ((raw.get("space") or {}).get("key") or raw.get("space") or ws.get("confluence_space") or ""),
        "labels": labels,
        "version": version.get("number") or raw.get("version") or 1,
        "updated": updated,
        "updated_by": ((version.get("by") or {}).get("displayName") or raw.get("by") or ""),
        "version_message": version.get("message") or raw.get("message") or "",
        "created": created,
        "is_new": bool(start and created and created >= start),
        "ancestor_ids": [str(a.get("id")) for a in ancestors if a.get("id")],
        "ancestor_titles": [a.get("title") or "" for a in ancestors],
        "body_text": "" if title_only else sources.strip_html(raw_html, limit=limit),
        "storage": storage_html,
        "keys": keys,
        "kind": next((label.lower() for label in labels if label.lower() in kind_labels), ""),
        "epic": "",
        "epic_match": "",
        "summary": "",
        "workstream": ws.get("abbrev") or "",
        "product": (product or {}).get("abbrev") or ws.get("product") or "",
        "watch": updated,
        "detail": "",
    }


def excluded(page, cfg, skip_ids=None):
    """True for the tool's own published reports and register pages."""
    if str(page.get("page_id") or "") in set(skip_ids or []):
        return True
    from core import confluence_tree
    if confluence_tree.skipped(cfg, page.get("title"), page.get("page_id"),
                               page.get("ancestor_titles"), page.get("ancestor_ids")):
        return True
    if "pm-report" in [str(label).lower() for label in (page.get("labels") or [])]:
        return True
    publish = ((cfg.get("publish") or {}).get("confluence") or {})
    parent = str(publish.get("parent_page") or "")
    space = str(publish.get("space") or "")
    titles = page.get("ancestor_titles") or []
    ids = page.get("ancestor_ids") or []
    if parent and (parent in ids or parent in titles):
        if not space or page.get("space") == space or True:
            if parent in ids or parent in titles:
                return True
    return False


def _window_start(window):
    start = (window or {}).get("start")
    if hasattr(start, "isoformat"):
        return start.isoformat()
    return str(start)[:10] if start else None


def _fetch_dropping_rejected_types(cfg, ws, scope, types, since, limit):
    """A 400 names the type. Drop it for this run and keep the rest."""
    from core import filters
    kept = []
    dropped = cfg.setdefault("_dropped_content_types", set())
    for content_type in types:
        if content_type in dropped:
            continue
        one = filters.build_cql(ws, cfg, scope=scope, types=[content_type])
        try:
            kept.extend(sources.fetch_confluence_results(
                cfg, one, since=since, limit=limit))
        except Exception as err:  # noqa: BLE001
            if "400" not in str(err):
                raise
            dropped.add(content_type)
            print(f"  confluence type {content_type} was rejected — "
                  f"edit confluence.content_types. Dropped for this run.")
    return kept


def _within(page, since):
    if not since:
        return True
    updated = str(page.get("updated") or "")[:10]
    return not updated or updated >= since


def gather(cfg, ws, product=None, epics=None, window=None, skip_ids=None):
    """Changed pages for one workstream, plus pages an in-scope Epic links to."""
    opts = page_settings(cfg)
    if not opts["enabled"]:
        return []
    from core import filters
    dropped = set(cfg.get("_dropped_content_types") or [])
    types = [name for name in list(opts["content_types"]) + list(opts["title_only_types"])
             if name not in dropped]
    scope = "labelled" if opts["scope"] == "labelled" else "space"
    cql = filters.build_cql(ws, cfg, scope=scope, types=types)
    if not cql and not opts.get("follow_jira_links"):
        return []
    since = _window_start(window)
    base = (cfg.get("confluence") or {}).get("base_url") or ""
    projects = project_keys(cfg)
    pages = []
    seen = set()
    if cql:
        try:
            raws = sources.fetch_confluence_results(cfg, cql, since=since, limit=opts["max_pages"])
        except Exception as err:  # noqa: BLE001
            if "400" not in str(err):
                raise
            raws = _fetch_dropping_rejected_types(
                cfg, ws, scope, types, since, opts["max_pages"])
        for raw in raws:
            page = normalise(raw, base, ws, product, projects, since, opts)
            if not _within(page, since) or excluded(page, cfg, skip_ids):
                continue
            if page["page_id"] in seen:
                continue
            seen.add(page["page_id"])
            pages.append(page)
    if opts.get("follow_jira_links"):
        for epic in epics or []:
            key = epic.get("key")
            if not key or epic.get("in_scope") is False:
                continue
            for link in sources.fetch_remote_links(cfg, key):
                page_id = _remote_page_id(link, base)
                if not page_id or page_id in seen:
                    continue
                raw = sources.fetch_confluence_page(cfg, page_id)
                if not raw:
                    continue
                page = normalise(raw, base, ws, product, projects, since, opts)
                if not _within(page, since) or excluded(page, cfg, skip_ids):
                    continue
                page["epic"] = key
                page["epic_match"] = "link"
                seen.add(page_id)
                pages.append(page)
    pages.sort(key=lambda page: page.get("updated") or "", reverse=True)
    kept = pages[: opts["max_pages"]]
    return apply_excerpt(kept, opts, cutoff=None)


def _remote_page_id(link, base_url):
    obj = link.get("object") or {}
    url = obj.get("url") or ""
    app = ((link.get("application") or {}).get("type") or "")
    base = (base_url or "").rstrip("/")
    if app != "com.atlassian.confluence" and base and not url.startswith(base):
        return None
    match = _PAGE_ID.search(url)
    return match.group(1) if match else None


def map_to_epics(pages, epics, parent_of=None, cfg=None):
    """Rules 1–3. Rule 4 (the model) is filled in by page summaries."""
    by_key = {row.get("key"): row for row in epics if row.get("key")}
    parent_of = parent_of or {}
    for page in pages:
        if page.get("epic_match") == "link" and page.get("epic") in by_key:
            by_key[page["epic"]].setdefault("pages", []).append(page)
            continue
        mentioned = []
        for key in page.get("keys") or []:
            epic_key = key if key in by_key else parent_of.get(key)
            if epic_key in by_key and epic_key not in mentioned:
                mentioned.append(epic_key)
        if len(mentioned) == 1:
            page["epic"] = mentioned[0]
            page["epic_match"] = "mention"
            by_key[mentioned[0]].setdefault("pages", []).append(page)
            continue
        page.setdefault("epic", "")
        page.setdefault("epic_match", "")
    matched = {page.get("page_id"): page for page in pages
               if page.get("epic") and page.get("epic_match") in ("link", "mention")}
    for page in pages:
        if page.get("epic"):
            continue
        for ancestor in page.get("ancestor_ids") or []:
            parent = matched.get(ancestor)
            if parent and parent.get("epic") in by_key:
                page["epic"] = parent["epic"]
                page["epic_match"] = "ancestor"
                by_key[parent["epic"]].setdefault("pages", []).append(page)
                break
    opts = page_settings(cfg or {})
    if opts.get("match_epics_with_model"):
        from core import page_summaries
        for page in pages:
            if page.get("epic") or not page.get("summary"):
                continue
            chosen = page_summaries.pick_epic(cfg or {}, page, list(by_key.values()))
            if chosen in by_key:
                page["epic"] = chosen
                page["epic_match"] = "model"
                by_key[chosen].setdefault("pages", []).append(page)
    return pages
