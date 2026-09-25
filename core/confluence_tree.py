"""Teams that share one Confluence space.

A space can hold several teams. Each team has a team page, and under it
are pages or folders for its products and workstreams, plus pages that
belong to the whole team. `confluence.team_page` names the team page.

A product or workstream finds its folder in this order: `confluence_page_id`,
then `confluence_page` (a title), then a page or folder under the team page
whose title matches the product or workstream name or short name, for
example "Secure Data Exchange (SDX)". `confluence_page: false` turns the
match off. `confluence_space` with no page still means that whole space.
"""

import re


_KEY = re.compile(r"^[A-Za-z0-9_~-]+$")


def _block(cfg):
    block = (cfg or {}).get("confluence") if isinstance(cfg, dict) else None
    return block if isinstance(block, dict) else {}


def _note(cfg, message):
    if not isinstance(cfg, dict):
        print(message)
        return
    seen = cfg.setdefault("_confluence_notes", [])
    if message in seen:
        return
    seen.append(message)
    print(message)


def team_space(cfg):
    """The shared space key. A space name, such as "POSM Chapter", is looked up once."""
    raw = str(_block(cfg).get("space") or "").strip()
    if not raw:
        return ""
    if _KEY.match(raw):
        return raw
    if not isinstance(cfg, dict):
        return raw
    cache = cfg.setdefault("_confluence_space_key", {})
    if raw in cache:
        return cache[raw]
    from core import sources
    try:
        found = sources.find_confluence_space(cfg, raw)
    except Exception as err:  # noqa: BLE001
        _note(cfg, f'_confluence.space: could not look up "{raw}" ({err})._')
        found = None
    if found:
        cache[raw] = found["key"]
    else:
        _note(cfg, f'_confluence.space: no space is named "{raw}". Use the space key._')
        cache[raw] = ""
    return cache[raw]


def team_page_title(cfg):
    block = _block(cfg)
    return str(block.get("team_page") or block.get("root_title") or "")


def team_page_setting_id(cfg):
    block = _block(cfg)
    return str(block.get("team_page_id") or block.get("root_page_id") or "")


def has_team_page(cfg):
    return bool(team_page_title(cfg) or team_page_setting_id(cfg))


def find_titled(cfg, space, title, under_id=None, label="Confluence", quiet=False):
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
            if not quiet:
                _note(cfg, f'_{label}: more than one Confluence page is titled "{title}"._')
            return None
        hits = sources.search_confluence_by_title(
            cfg, space, title, ancestor_id=under_id)
    else:
        hits = sources.search_confluence_by_title(cfg, space, title)
    return _one(cfg, hits, label, title, quiet=quiet)


def _one(cfg, hits, label, title, quiet=False):
    if len(hits) == 1:
        return hits[0]
    if quiet:
        return None
    if len(hits) > 1:
        _note(cfg, f'_{label}: more than one Confluence page is titled "{title}"._')
    else:
        _note(cfg, f'_{label}: Confluence page "{title}" was not found._')
    return None


def team_root_id(cfg):
    """The team page id, or "" when none is set or it cannot be found."""
    if not isinstance(cfg, dict):
        return ""
    if "_confluence_root_id" in cfg:
        return cfg["_confluence_root_id"]
    if team_page_setting_id(cfg):
        cfg["_confluence_root_id"] = team_page_setting_id(cfg)
        return cfg["_confluence_root_id"]
    title = team_page_title(cfg)
    space = team_space(cfg)
    if not title or not space:
        cfg["_confluence_root_id"] = ""
        return ""
    found = find_titled(cfg, space, title, label="confluence.team_page")
    cfg["_confluence_root_id"] = str(found.get("id") or "") if found else ""
    return cfg["_confluence_root_id"]


def _search_under(cfg, space, title):
    """Ancestor to narrow a title search. Empty when the title is the team page."""
    if not space or space != team_space(cfg):
        return ""
    if title and title == team_page_title(cfg):
        return ""
    return team_root_id(cfg)


def children(cfg, space, parent_id):
    """`[{id, title, type}]` directly under a page. Cached for the run."""
    if not isinstance(cfg, dict) or not space or not parent_id:
        return []
    cache = cfg.setdefault("_confluence_children", {})
    key = (space, str(parent_id))
    if key in cache:
        return cache[key]
    from core import sources
    try:
        rows = sources.list_confluence_children(cfg, space, parent_id)
    except Exception as err:  # noqa: BLE001
        _note(cfg, f"_Confluence: could not list the pages under {parent_id} ({err})._")
        rows = []
    cache[key] = [{"id": str(row.get("id") or ""), "title": row.get("title") or "",
                   "type": row.get("type") or "page"} for row in rows if row.get("id")]
    return cache[key]


def _words(text):
    return re.sub(r"[^0-9a-z]+", " ", str(text or "").casefold()).split()


def match_rank(title, entry):
    """How well a folder title names this product or workstream. 0 is no match."""
    name = entry.get("name") or ""
    abbrev = entry.get("abbrev") or ""
    title_words = _words(title)
    name_words = _words(name)
    if name_words and title_words == name_words:
        return 5
    if abbrev and f"({abbrev.casefold()})" in str(title or "").casefold():
        return 4
    if abbrev and title_words == _words(abbrev):
        return 3
    if abbrev and re.search(rf"(?<![0-9A-Za-z]){re.escape(abbrev)}(?![0-9A-Za-z])",
                            str(title or "")):
        return 2
    if len(name_words) >= 2:
        joined = " ".join(title_words)
        if f" {' '.join(name_words)} " in f" {joined} ":
            return 1
    return 0


def best_match(rows, entry, exclude=()):
    """The one row whose title names this entry best. None when absent or tied."""
    scored = []
    for row in rows:
        if row["id"] in exclude:
            continue
        rank = match_rank(row["title"], entry)
        if rank:
            scored.append((rank, row))
    if not scored:
        return None
    scored.sort(key=lambda pair: pair[0], reverse=True)
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None
    return scored[0][1]


def product_of(cfg, ws):
    abbrev = (ws or {}).get("product") or ""
    if not abbrev:
        return None
    for product in (cfg or {}).get("products") or []:
        if isinstance(product, dict) and product.get("abbrev") == abbrev:
            return product
    return None


def _result(space="", ancestor_id="", missing=False, title="", how=""):
    return {"space": space, "ancestor_id": ancestor_id, "missing": missing,
            "title": title, "how": how}


def _cached(cfg, key, build):
    cfg = cfg if isinstance(cfg, dict) else {}
    cache = cfg.setdefault("_confluence_located", {})
    if key not in cache:
        cache[key] = build()
    return cache[key]


def _entry_key(kind, entry):
    return (kind, entry.get("abbrev") or "", entry.get("name") or "",
            entry.get("product") or "",
            str(entry.get("confluence_page_id") or ""),
            str(entry.get("confluence_page") if "confluence_page" in entry else ""),
            entry.get("confluence_space") or "")


def _named(cfg, entry, space, under, label):
    """Resolve `confluence_page_id` or a `confluence_page` title."""
    if entry.get("confluence_page_id"):
        if not space:
            _note(cfg, f"_{label}: set confluence.space or confluence_space for this page._")
            return _result(missing=True)
        return _result(space, str(entry["confluence_page_id"]), how="page id")
    title = entry.get("confluence_page") or ""
    if not space:
        _note(cfg, f"_{label}: set confluence.space or confluence_space for \"{title}\"._")
        return _result(missing=True)
    found = find_titled(cfg, space, title, under_id=under or None, label=label)
    if not found:
        return _result(space, missing=True, title=title)
    return _result(space, str(found.get("id") or ""), title=found.get("title") or title,
                   how="title")


def _matched(cfg, entry, space, parents, exclude=()):
    """A folder under one of `parents` whose title names the entry."""
    for parent in parents:
        if not parent:
            continue
        row = best_match(children(cfg, space, parent), entry, exclude=exclude)
        if row:
            return _result(space, row["id"], title=row["title"], how="matched")
    return None


def can_match(entry):
    if entry.get("confluence_page") is False:
        return False
    return not (entry.get("confluence_space") or entry.get("confluence_page")
                or entry.get("confluence_page_id") or entry.get("confluence_cql"))


def locate_product(cfg, product):
    """`{space, ancestor_id, missing, title, how}` for a product's folder."""
    product = product or {}
    return _cached(cfg, _entry_key("product", product),
                   lambda: _locate_product(cfg, product))


def _locate_product(cfg, product):
    label = product.get("abbrev") or product.get("name") or "product"
    if product.get("confluence_page") or product.get("confluence_page_id"):
        space = str(product.get("confluence_space") or "") or team_space(cfg)
        title = product.get("confluence_page") or ""
        return _named(cfg, product, space, _search_under(cfg, space, title), label)
    if can_match(product) and has_team_page(cfg):
        space = team_space(cfg)
        found = _matched(cfg, product, space, [team_root_id(cfg)])
        if found:
            return found
    return _result(str(product.get("confluence_space") or ""))


def locate_workstream(cfg, ws):
    """`{space, ancestor_id, missing, title, how}` for a workstream's folder.

    A workstream with only `confluence_space` keeps that whole space. A named
    page is looked up inside the product folder when there is one, then
    under the team page. With neither, a folder whose title names the
    workstream is looked for in the product folder, then under the team page.
    """
    ws = ws or {}
    return _cached(cfg, _entry_key("ws", ws), lambda: _locate_workstream(cfg, ws))


def _locate_workstream(cfg, ws):
    label = ws.get("abbrev") or ws.get("name") or "workstream"
    product = product_of(cfg, ws)
    parent = locate_product(cfg, product) if product else _result()
    if ws.get("confluence_page") or ws.get("confluence_page_id"):
        if ws.get("confluence_space"):
            space = str(ws["confluence_space"])
        elif product and product.get("confluence_space"):
            space = str(product["confluence_space"])
        else:
            space = team_space(cfg)
        under = ""
        if parent.get("ancestor_id") and parent.get("space") == space:
            under = parent["ancestor_id"]
        if not under:
            under = _search_under(cfg, space, ws.get("confluence_page") or "")
        return _named(cfg, ws, space, under, label)
    if can_match(ws) and has_team_page(cfg):
        space = team_space(cfg)
        parents = []
        exclude = ()
        if parent.get("ancestor_id") and parent.get("space") == space:
            parents.append(parent["ancestor_id"])
            exclude = (parent["ancestor_id"],)
        parents.append(team_root_id(cfg))
        found = _matched(cfg, ws, space, parents, exclude=exclude)
        if found:
            return found
    return _result(str(ws.get("confluence_space") or ""))


def folder_ids(cfg, kind=None):
    """Every located product and workstream folder id in the team space."""
    ids = []
    if kind in (None, "workstream"):
        for ws in (cfg or {}).get("workstreams") or []:
            if isinstance(ws, dict):
                found = locate_workstream(cfg, ws).get("ancestor_id")
                if found and found not in ids:
                    ids.append(found)
    if kind in (None, "product"):
        for product in (cfg or {}).get("products") or []:
            if isinstance(product, dict):
                found = locate_product(cfg, product).get("ancestor_id")
                if found and found not in ids:
                    ids.append(found)
    return ids
