"""Decision logs, risk registers, and ADRs kept as Confluence child pages."""

import re

from core import pages, queries, sources


TYPES = ("decision", "risk", "adr")
_STATUS_LABELS = {
    "proposed", "accepted", "rejected", "superseded", "deprecated",
    "open", "closed", "mitigated",
}
_STATUS_MACRO = re.compile(
    r'ac:name="status"[^>]*>.*?ac:name="title"[^>]*>(?:<!\[CDATA\[)?([^<\]]+)',
    re.I | re.S)
_ROW = re.compile(r"<tr>(.*?)</tr>", re.I | re.S)
_CELL = re.compile(r"<t([hd])[^>]*>(.*?)</t\1>", re.I | re.S)


def settings(cfg):
    """The registers list with defaults filled in. Empty when unset."""
    raw = cfg.get("registers") or []
    out = []
    for reg in raw:
        item = dict(reg)
        item.setdefault("depth", "descendants")
        item.setdefault("status_field", "Status")
        item.setdefault("fields", [])
        item.setdefault("highlight", None)
        item.setdefault("partner_visible", False)
        out.append(item)
    return out


def _selected(cfg, reg):
    product = reg.get("product")
    workstream = reg.get("workstream")
    chosen_products = {p.get("abbrev") for p in (cfg.get("_products") or cfg.get("products") or [])}
    chosen_streams = {w.get("abbrev") for w in (cfg.get("_workstreams") or cfg.get("workstreams") or [])}
    if product and chosen_products and product not in chosen_products:
        return False
    if workstream and chosen_streams and workstream not in chosen_streams:
        return False
    return True


def resolve_root(cfg, reg):
    """The summary page, or None when it cannot be found."""
    base = (cfg.get("confluence") or {}).get("base_url") or ""
    if reg.get("page_id"):
        raw = sources.fetch_confluence_page(cfg, reg["page_id"])
        if not raw:
            return None
        return pages.normalise(raw, base, {}, None, pages.project_keys(cfg), None, pages.page_settings(cfg))
    space, title = reg.get("space"), reg.get("title")
    if not space or not title:
        return None

    def fetch():
        block = sources._confluence_block(cfg)
        url = f"{block['base_url'].rstrip('/')}/rest/api/content"
        resp = sources.send(
            "GET", url,
            params={"spaceKey": space, "title": title, "expand": "version,space,history"},
            auth=(block["email"], block["api_token"]),
            headers={"Accept": "application/json"},
            timeout=60,
        )
        resp.raise_for_status()
        results = resp.json().get("results") or []
        return results[0] if results else None

    raw = pages.cache_fetch(cfg, "confluence-title", (space, title), fetch)
    if not raw:
        return None
    return pages.normalise(raw, base, {}, None, pages.project_keys(cfg), None, pages.page_settings(cfg))


def _entry_cql(reg, root_id):
    query_id = "registers.children" if reg.get("depth") == "children" else "registers.descendants"
    return queries.render(None, query_id, page_id=str(root_id))


def list_entries(cfg, reg, root_id):
    """Every entry id, title and version, without the body."""
    cql = _entry_cql(reg, root_id)
    rows = []
    for raw in sources.fetch_confluence_results(cfg, cql, since="1970-01-01", limit=200):
        version = raw.get("version") or {}
        rows.append({
            "page_id": str(raw.get("id")),
            "title": raw.get("title") or "",
            "version": version.get("number") or 1,
            "updated": str(version.get("when") or "")[:10],
        })
    return rows


def properties(storage_html, wanted):
    """Field values from the first Page Properties table."""
    wanted_map = {str(name).lower(): name for name in (wanted or [])}
    if not wanted_map or not storage_html:
        return {}
    found = {}
    for row in _ROW.findall(storage_html):
        cells = _CELL.findall(row)
        if len(cells) < 2:
            continue
        field = sources.strip_html(cells[0][1], limit=80).strip()
        key = wanted_map.get(field.lower())
        if not key or key in found:
            continue
        value_html = cells[1][1]
        status = _STATUS_MACRO.search(value_html)
        if status:
            found[key] = status.group(1).strip().title()
        else:
            found[key] = sources.strip_html(value_html, limit=200)
    return found


def status_of(entry, reg):
    fields = entry.get("fields") or {}
    status = fields.get(reg.get("status_field") or "Status") or ""
    if status:
        return status
    for label in entry.get("labels") or []:
        if str(label).lower() in _STATUS_LABELS:
            return str(label).title()
    return ""


def _high(entry, reg):
    highlight = reg.get("highlight") or None
    if not highlight:
        return False
    field = highlight.get("field")
    values = {str(v).lower() for v in (highlight.get("values") or [])}
    return str((entry.get("fields") or {}).get(field) or "").lower() in values


def gather_one(cfg, reg, window, previous):
    """One register record. Prints a line and returns None when the root is missing."""
    root = resolve_root(cfg, reg)
    if root is None:
        where = (f"page {reg['page_id']}" if reg.get("page_id")
                 else f"space {reg.get('space')}, title \"{reg.get('title')}\"")
        print(f"_{reg.get('name')}: summary page not found ({where})._")
        return None
    start = window.get("start")
    since = start.isoformat() if hasattr(start, "isoformat") else str(start or "")[:10]
    memory = (previous or {}).get("_registers") or {}
    snap = memory.get(f"{reg['type']}:{root['page_id']}") or {}
    listed = list_entries(cfg, reg, root["page_id"])
    by_id = {row["page_id"]: row for row in listed}
    cql = f"({_entry_cql(reg, root['page_id'])})"
    opts = pages.page_settings(cfg)
    base = (cfg.get("confluence") or {}).get("base_url") or ""
    changed = []
    for raw in sources.fetch_confluence_results(cfg, cql, since=since or "1970-01-01",
                                                 limit=opts["max_pages"]):
        page = pages.normalise(raw, base, {}, None, pages.project_keys(cfg), since, opts)
        if since and page.get("updated") and page["updated"] < since:
            continue
        wanted = [reg.get("status_field") or "Status"] + list(reg.get("fields") or [])
        page["fields"] = properties(page.get("storage") or "", wanted)
        page["status"] = status_of(page, reg)
        page["kind"] = reg["type"]
        page["high"] = _high(page, reg)
        page["register"] = reg["name"]
        stored = snap.get(page["page_id"]) or {}
        page["status_was"] = stored.get("status") or "" if not page.get("is_new") else ""
        if page.get("is_new"):
            page["change"] = "new"
        else:
            page["change"] = "changed"
        changed.append(page)
    removed = []
    if snap:
        for page_id, stored in snap.items():
            if page_id not in by_id:
                removed.append({"page_id": page_id, "title": stored.get("title") or page_id})
    changed.sort(key=lambda page: (not page.get("high"), page.get("change") != "new", page.get("updated") or ""))
    catalog = []
    changed_by_id = {page["page_id"]: page for page in changed}
    for row in listed:
        live = changed_by_id.get(row["page_id"])
        stored = snap.get(row["page_id"]) or {}
        catalog.append({
            "page_id": row["page_id"],
            "title": row["title"],
            "version": row["version"],
            "status": (live or {}).get("status") or stored.get("status") or "",
        })
    root["edited_in_window"] = bool(since and root.get("updated") and root["updated"] >= since)
    scope = {}
    if reg.get("product"):
        scope["product"] = reg["product"]
    elif reg.get("workstream"):
        scope["workstream"] = reg["workstream"]
    return {
        "type": reg["type"],
        "name": reg["name"],
        "partner_visible": bool(reg.get("partner_visible")),
        "root": root,
        "total": len(listed),
        "entries": changed,
        "removed": removed,
        "first_run": not bool(snap),
        "scope": scope,
        "reg": reg,
        "catalog": catalog,
    }


def gather(cfg, window, previous):
    """Registers in scope for this run, and the page ids the general reader must skip."""
    found = []
    skip = set()
    for reg in settings(cfg):
        if not _selected(cfg, reg):
            continue
        record = gather_one(cfg, reg, window or {}, previous or {})
        if record is None:
            continue
        found.append(record)
        skip.add(str(record["root"]["page_id"]))
        for row in record["entries"]:
            skip.add(str(row["page_id"]))
    return found, skip


def snapshot(registers):
    """The `_registers` memory written after a run that saves state."""
    out = {}
    for record in registers or []:
        root_id = record["root"]["page_id"]
        bucket = {}
        # Unchanged entries keep the status stored last time; only a body
        # fetch (new or changed) refreshes it. A leading underscore on the
        # state key keeps core.state from treating this as a workstream.
        for row in record.get("catalog") or []:
            bucket[row["page_id"]] = {
                "title": row.get("title") or "",
                "version": row.get("version") or 1,
                "status": row.get("status") or "",
            }
        out[f"{record['type']}:{root_id}"] = bucket
    return out


def not_found_line(name, reg):
    return ""
