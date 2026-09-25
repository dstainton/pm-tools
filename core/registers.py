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


def _register_space(cfg, reg):
    from core import confluence_tree
    return reg.get("space") or confluence_tree.team_space(cfg)


def _normalise_root(cfg, raw):
    base = (cfg.get("confluence") or {}).get("base_url") or ""
    return pages.normalise(raw, base, {}, None, pages.project_keys(cfg), None, pages.page_settings(cfg))


def _resolve_under(cfg, reg, space):
    """The ancestor page id for `under` / `under_id`, or None when it is missing."""
    if reg.get("under_id"):
        return str(reg["under_id"])
    title = reg.get("under")
    if not title:
        return ""
    from core import confluence_tree
    ancestor = confluence_tree._search_under(cfg, space, title)
    found = confluence_tree.find_titled(
        cfg, space, title, under_id=ancestor or None, label=reg.get("name") or "register")
    if not found:
        return None
    return str(found.get("id") or "")


def resolve_root(cfg, reg):
    """The summary page, or None when it cannot be found.

    `page_id` wins. `under` or `under_id` finds `title` as a direct child of
    that page or folder when one exists, and otherwise as the only page of
    that title anywhere under it. That is how a team-level "Risks" page stays
    distinct from a "Risks" page inside a product folder. With no `under`, a
    title lookup stays on the content API so a page found that way still
    resolves, and a folder title is tried when that lookup misses.
    """
    if reg.get("page_id"):
        raw = sources.fetch_confluence_page(cfg, reg["page_id"])
        if not raw:
            return None
        return _normalise_root(cfg, raw)
    space, title = _register_space(cfg, reg), reg.get("title")
    if not space or not title:
        return None
    if reg.get("under") or reg.get("under_id"):
        under_id = _resolve_under(cfg, reg, space)
        if not under_id:
            return None
        from core import confluence_tree
        raw = confluence_tree.find_titled(
            cfg, space, title, under_id=under_id, label=reg.get("name") or "register")
        if not raw:
            return None
        return _normalise_root(cfg, raw)

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
        hits = sources.search_confluence_by_title(cfg, space, title)
        raw = hits[0] if len(hits) == 1 else None
    if not raw:
        return None
    return _normalise_root(cfg, raw)


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
            "labels": pages._labels(raw),
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
                 else f"space {_register_space(cfg, reg)}, title \"{reg.get('title')}\"")
        if reg.get("under"):
            where += f", under \"{reg['under']}\""
        elif reg.get("under_id"):
            where += f", under page {reg['under_id']}"
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
                removed.append({
                    "page_id": page_id,
                    "title": stored.get("title") or page_id,
                    "labels": list(stored.get("labels") or []),
                })
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
            "labels": (live or {}).get("labels") or row.get("labels") or stored.get("labels") or [],
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


def _scope_from_labels(cfg, reg, labels):
    """Where one labelled entry belongs.

    A single workstream abbreviation wins over a product abbreviation. With
    `product` set, a label for one of that product's workstreams files the
    entry there, and every other entry stays on the product. No match, and
    no product on the register, stays unscoped (the portfolio section).
    """
    wanted = {str(label).lower() for label in (labels or [])}
    streams = [ws for ws in (cfg.get("workstreams") or []) if isinstance(ws, dict)]
    products = [row for row in (cfg.get("products") or []) if isinstance(row, dict)]
    product = reg.get("product")
    if product:
        streams = [ws for ws in streams if (ws.get("product") or "") == product]
    stream_hits = []
    for ws in streams:
        abbrev = ws.get("abbrev") or ""
        if abbrev and abbrev.lower() in wanted and abbrev not in stream_hits:
            stream_hits.append(abbrev)
    if len(stream_hits) == 1:
        return {"workstream": stream_hits[0]}
    if product:
        return {"product": product}
    product_hits = []
    for row in products:
        abbrev = row.get("abbrev") or ""
        if abbrev and abbrev.lower() in wanted and abbrev not in product_hits:
            product_hits.append(abbrev)
    if len(stream_hits) > 1:
        return {}
    if len(product_hits) == 1:
        return {"product": product_hits[0]}
    return {}


def _blank_slice(record, scope):
    return {
        "type": record["type"],
        "name": record["name"],
        "partner_visible": record.get("partner_visible"),
        "root": record.get("root"),
        "total": 0,
        "entries": [],
        "removed": [],
        "first_run": record.get("first_run"),
        "scope": scope,
        "reg": record.get("reg"),
        "catalog": [],
        "snapshot_catalog": record.get("snapshot_catalog") or [],
    }


def split_record(cfg, record):
    """One display record, or one record per label scope.

    Every slice keeps `snapshot_catalog` as the full list. Memory is one
    bucket per summary page, not one bucket per slice.
    """
    reg = record.get("reg") or {}
    full = list(record.get("catalog") or [])
    record["snapshot_catalog"] = full
    if reg.get("split") != "label":
        return [record]
    groups = {}

    def bucket(scope):
        key = (scope.get("product") or "", scope.get("workstream") or "")
        if key not in groups:
            groups[key] = _blank_slice(record, {k: v for k, v in (
                ("product", key[0]), ("workstream", key[1])) if v})
            groups[key]["snapshot_catalog"] = full
        return groups[key]

    by_id = {row["page_id"]: row for row in full}
    for row in full:
        bucket(_scope_from_labels(cfg, reg, row.get("labels")))["catalog"].append(row)
    for row in record.get("entries") or []:
        labels = (by_id.get(row["page_id"]) or {}).get("labels")
        if labels is None:
            labels = row.get("labels")
        bucket(_scope_from_labels(cfg, reg, labels))["entries"].append(row)
    for row in record.get("removed") or []:
        labels = row.get("labels") or []
        if labels:
            scope = _scope_from_labels(cfg, reg, labels)
        elif reg.get("product"):
            scope = {"product": reg["product"]}
        else:
            scope = {}
        bucket(scope)["removed"].append(row)
    if not groups:
        base = {"product": reg["product"]} if reg.get("product") else {}
        return [_blank_slice(record, base)]
    slices = []
    for piece in groups.values():
        piece["total"] = len(piece["catalog"])
        slices.append(piece)
    return slices


def _scope_visible(cfg, scope):
    product = (scope or {}).get("product")
    workstream = (scope or {}).get("workstream")
    chosen_products = {p.get("abbrev") for p in (cfg.get("_products") or [])}
    chosen_streams = {w.get("abbrev") for w in (cfg.get("_workstreams") or [])}
    if product and chosen_products and product not in chosen_products:
        return False
    if workstream and chosen_streams and workstream not in chosen_streams:
        return False
    return True


def _specificity(record):
    """Workstream beats product beats portfolio. A fixed register beats a label split."""
    scope = record.get("scope") or {}
    if scope.get("workstream"):
        base = 2
    elif scope.get("product"):
        base = 1
    else:
        base = 0
    split = (record.get("reg") or {}).get("split") == "label"
    return base * 2 + (0 if split else 1)


def dedupe_entries(records):
    """Drop a page from the wider register when a narrower one already lists it."""
    winner = {}
    for index, record in enumerate(records):
        rank = _specificity(record)
        seen = []
        for row in (record.get("entries") or []) + (record.get("catalog") or []) + (record.get("removed") or []):
            pid = str(row.get("page_id") or "")
            if pid and pid not in seen:
                seen.append(pid)
        for pid in seen:
            current = winner.get(pid)
            if current is None or rank > current[0]:
                winner[pid] = (rank, index)
    kept = []
    for index, record in enumerate(records):
        def mine(row, index=index):
            pid = str(row.get("page_id") or "")
            if not pid:
                return True
            return winner.get(pid, (0, index))[1] == index

        record["entries"] = [row for row in (record.get("entries") or []) if mine(row)]
        record["catalog"] = [row for row in (record.get("catalog") or []) if mine(row)]
        record["removed"] = [row for row in (record.get("removed") or []) if mine(row)]
        record["total"] = len(record.get("catalog") or [])
        if record["catalog"] or record["entries"] or record["removed"]:
            kept.append(record)
        elif not record.get("snapshot_catalog"):
            kept.append(record)
    return kept


def gather(cfg, window, previous):
    """Registers in scope for this run, and the page ids the general reader must skip."""
    found = []
    memory_rows = []
    for reg in settings(cfg):
        if not _selected(cfg, reg):
            continue
        record = gather_one(cfg, reg, window or {}, previous or {})
        if record is None:
            continue
        pieces = split_record(cfg, record)
        memory_rows.extend(pieces)
        for piece in pieces:
            if _scope_visible(cfg, piece.get("scope") or {}):
                found.append(piece)
    if isinstance(cfg, dict):
        cfg["_register_memory"] = snapshot(memory_rows)
    found = dedupe_entries(found)
    skip = set()
    for record in found:
        skip.add(str(record["root"]["page_id"]))
        for row in record["entries"]:
            skip.add(str(row["page_id"]))
    return found, skip


def _snap_row(row):
    return {
        "title": row.get("title") or "",
        "version": row.get("version") or 1,
        "status": row.get("status") or "",
        "labels": list(row.get("labels") or []),
    }


def snapshot(registers):
    """The `_registers` memory written after a run that saves state.

    Slices of one summary page share a bucket. The full catalog is what the
    next run compares, so a filtered report does not forget the other entries.
    """
    out = {}
    full = set()
    for record in registers or []:
        root_id = record["root"]["page_id"]
        key = f"{record['type']}:{root_id}"
        catalog = record.get("snapshot_catalog")
        if catalog is not None:
            if key in full:
                continue
            full.add(key)
            bucket = {}
            for row in catalog:
                bucket[row["page_id"]] = _snap_row(row)
            out[key] = bucket
            continue
        bucket = out.setdefault(key, {})
        for row in record.get("catalog") or []:
            bucket[row["page_id"]] = _snap_row(row)
    return out


def saved_memory(cfg, records):
    """Full register memory when gather stored it, otherwise `snapshot(records)`."""
    stored = cfg.get("_register_memory") if isinstance(cfg, dict) else None
    if isinstance(stored, dict):
        return stored
    return snapshot(records)


def not_found_line(name, reg):
    return ""
