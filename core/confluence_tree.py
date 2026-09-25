"""One Confluence space laid out as a page tree.

A team page holds product folders, and those hold workstream folders.
`confluence_space` with no page still means the whole space. The team root
is not copied onto a workstream that did not name a page.
"""


def team_space(cfg):
    block = (cfg or {}).get("confluence") or {}
    return str(block.get("space") or "")


def _note(cfg, message):
    seen = cfg.setdefault("_confluence_notes", [])
    if message in seen:
        return
    seen.append(message)
    print(message)


def find_titled(cfg, space, title, under_id=None, label="Confluence"):
    """The page or folder named `title`.

    When `under_id` is set, a direct child wins. A nested page is used only
    when it is the only match, so a team-level "Risks" page stays distinct
    from a "Risks" page inside a product folder.
    """
    from core import sources
    if under_id:
        direct = sources.search_confluence_by_title(
            cfg, space, title, parent_id=under_id)
        if len(direct) == 1:
            return direct[0]
        if len(direct) > 1:
            _note(cfg, f'_{label}: more than one Confluence page is titled "{title}"._')
            return None
        hits = sources.search_confluence_by_title(
            cfg, space, title, ancestor_id=under_id)
    else:
        hits = sources.search_confluence_by_title(cfg, space, title)
    return _one(cfg, hits, label, title)


def _one(cfg, hits, label, title):
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        _note(cfg, f'_{label}: more than one Confluence page is titled "{title}"._')
    else:
        _note(cfg, f'_{label}: Confluence page "{title}" was not found._')
    return None


def team_root_id(cfg):
    """The team page id, or "" when no root is configured or it cannot be found."""
    if not isinstance(cfg, dict):
        return ""
    if "_confluence_root_id" in cfg:
        return cfg["_confluence_root_id"]
    block = cfg.get("confluence") or {}
    if block.get("root_page_id"):
        cfg["_confluence_root_id"] = str(block["root_page_id"])
        return cfg["_confluence_root_id"]
    title = block.get("root_title") or ""
    space = team_space(cfg)
    if not title or not space:
        cfg["_confluence_root_id"] = ""
        return ""
    from core import sources
    hits = sources.search_confluence_by_title(cfg, space, title)
    found = _one(cfg, hits, "confluence.root_title", title)
    cfg["_confluence_root_id"] = str(found.get("id") or "") if found else ""
    return cfg["_confluence_root_id"]


def _search_under(cfg, space, title):
    """Ancestor to disambiguate a title. Empty when the title is the team root."""
    if not space or space != team_space(cfg):
        return ""
    block = (cfg or {}).get("confluence") or {}
    if title and title == (block.get("root_title") or ""):
        return ""
    return team_root_id(cfg)


def _product(cfg, ws):
    abbrev = (ws or {}).get("product") or ""
    if not abbrev:
        return None
    for product in (cfg or {}).get("products") or []:
        if isinstance(product, dict) and product.get("abbrev") == abbrev:
            return product
    return None


def _space_for_page(cfg, ws):
    if ws.get("confluence_space"):
        return str(ws["confluence_space"])
    product = _product(cfg, ws)
    if product and product.get("confluence_space"):
        return str(product["confluence_space"])
    return team_space(cfg)


def locate_product(cfg, product):
    """`{space, ancestor_id, missing}` for a product folder. No page means no ancestor."""
    cfg = cfg if isinstance(cfg, dict) else {}
    product = product or {}
    cache = cfg.setdefault("_confluence_located", {})
    key = ("product", product.get("abbrev") or "",
           str(product.get("confluence_page_id") or ""),
           product.get("confluence_page") or "",
           product.get("confluence_space") or "")
    if key in cache:
        return cache[key]
    result = _locate_product(cfg, product)
    cache[key] = result
    return result


def _locate_product(cfg, product):
    named = product.get("confluence_page") or product.get("confluence_page_id")
    own_space = str(product.get("confluence_space") or "")
    if not named:
        return {"space": own_space, "ancestor_id": "", "missing": False}
    space = own_space or team_space(cfg)
    label = product.get("abbrev") or product.get("name") or "product"
    if product.get("confluence_page_id"):
        if not space:
            _note(cfg, f"_{label}: set confluence.space or confluence_space for this page._")
            return {"space": "", "ancestor_id": "", "missing": True}
        return {"space": space, "ancestor_id": str(product["confluence_page_id"]),
                "missing": False}
    title = product.get("confluence_page") or ""
    if not space:
        _note(cfg, f"_{label}: set confluence.space or confluence_space for \"{title}\"._")
        return {"space": "", "ancestor_id": "", "missing": True}
    from core import sources
    under = _search_under(cfg, space, title)
    hits = sources.search_confluence_by_title(cfg, space, title, ancestor_id=under or None)
    found = _one(cfg, hits, label, title)
    if not found:
        return {"space": space, "ancestor_id": "", "missing": True}
    return {"space": space, "ancestor_id": str(found.get("id") or ""), "missing": False}


def locate_workstream(cfg, ws):
    """`{space, ancestor_id, missing}`.

    A workstream with only `confluence_space` keeps that space and no ancestor.
    A named page is resolved in the workstream space, or the product space, or
    `confluence.space`, and narrowed to the product folder when that folder is
    in the same space.
    """
    cfg = cfg if isinstance(cfg, dict) else {}
    ws = ws or {}
    cache = cfg.setdefault("_confluence_located", {})
    key = ("ws", ws.get("abbrev") or "", ws.get("product") or "",
           str(ws.get("confluence_page_id") or ""),
           ws.get("confluence_page") or "",
           ws.get("confluence_space") or "")
    if key in cache:
        return cache[key]
    result = _locate_workstream(cfg, ws)
    cache[key] = result
    return result


def _locate_workstream(cfg, ws):
    if not ws.get("confluence_page") and not ws.get("confluence_page_id"):
        return {"space": str(ws.get("confluence_space") or ""), "ancestor_id": "",
                "missing": False}
    space = _space_for_page(cfg, ws)
    label = ws.get("abbrev") or ws.get("name") or "workstream"
    if ws.get("confluence_page_id"):
        if not space:
            _note(cfg, f"_{label}: set confluence.space or confluence_space for this page._")
            return {"space": "", "ancestor_id": "", "missing": True}
        return {"space": space, "ancestor_id": str(ws["confluence_page_id"]),
                "missing": False}
    title = ws.get("confluence_page") or ""
    if not space:
        _note(cfg, f"_{label}: set confluence.space or confluence_space for \"{title}\"._")
        return {"space": "", "ancestor_id": "", "missing": True}
    under = ""
    product = _product(cfg, ws)
    if product and (product.get("confluence_page") or product.get("confluence_page_id")):
        parent = locate_product(cfg, product)
        if parent.get("space") == space and parent.get("ancestor_id"):
            under = parent["ancestor_id"]
    if not under:
        under = _search_under(cfg, space, title)
    from core import sources
    hits = sources.search_confluence_by_title(cfg, space, title, ancestor_id=under or None)
    found = _one(cfg, hits, label, title)
    if not found:
        return {"space": space, "ancestor_id": "", "missing": True}
    return {"space": space, "ancestor_id": str(found.get("id") or ""), "missing": False}
