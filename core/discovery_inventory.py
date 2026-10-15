"""Scoped, read-only Confluence metadata inventory.

Page boundaries are authoritative. A space provides context, not permission to
broaden a configured page-tree scope.
"""
from core import sources

PAGE_SIZE = 25
MAX_PAGES = 100


def _scopes(cfg, report=None):
    block = cfg.get("confluence") or {}
    default_space = block.get("space")
    configured = block.get("scopes")
    result = []

    def add(kind, space=None, root=None, title=None):
        if kind not in ("space", "page_tree"):
            raise ValueError("Unknown Confluence inventory scope type: " + str(kind))
        if kind == "space":
            if not space:
                raise ValueError("Space discovery needs a space_key")
            scope = {"type": kind, "space": str(space)}
        else:
            if not root and not title:
                raise ValueError("Page-tree discovery needs page_id or page title")
            scope = {"type": kind, "space": str(space) if space else None,
                     "root_id": str(root) if root else None,
                     "root_title": str(title) if title else None}
        if scope not in result:
            result.append(scope)

    if configured is not None:
        if not isinstance(configured, list):
            raise ValueError("confluence.scopes must be a list")
        for item in configured:
            if not isinstance(item, dict):
                raise ValueError("Each Confluence scope must be a mapping")
            kind = item.get("type")
            add(kind, item.get("space_key") or item.get("space") or default_space,
                item.get("page_id") or item.get("root_page_id"),
                item.get("title") or item.get("root_title"))
        return result

    # A team/root page takes precedence over default space. Existing named
    # product/workstream references may add narrower scopes, but never widen it.
    root = block.get("root_page_id") or block.get("team_page_id")
    title = block.get("root_title") or block.get("team_page")
    if root or title:
        add("page_tree", default_space, root, None if root else title)
    for item in list(cfg.get("products") or []) + list(cfg.get("workstreams") or []):
        if not isinstance(item, dict):
            continue
        space = item.get("confluence_space") or default_space
        page_id = item.get("confluence_page_id")
        page_title = item.get("confluence_page")
        if page_id or page_title:
            add("page_tree", space, page_id, None if page_id else page_title)
        elif item.get("confluence_space") and not (root or title):
            add("space", space)
    if not result and default_space:
        add("space", default_space)
    return result


def _resolve(cfg, scope):
    if scope["type"] == "space":
        return scope
    scope = dict(scope)
    if not scope.get("root_id"):
        if not scope.get("space"):
            raise ValueError("Title-based page scopes require a Confluence space")
        found = sources.search_confluence_by_title(
            cfg, scope["space"], scope["root_title"])
        if len(found) != 1:
            raise ValueError("Page-tree root title must resolve to exactly one page: "
                             + str(scope["root_title"]))
        scope["root_id"] = str(found[0]["id"])
    root = sources.fetch_confluence_page(cfg, scope["root_id"])
    if not root:
        raise ValueError("Configured Confluence root is inaccessible or missing: "
                         + scope["root_id"])
    actual_space = (root.get("space") or {}).get("key")
    if scope.get("space") and actual_space and scope["space"] != actual_space:
        raise ValueError("Configured root is not in space " + scope["space"])
    scope["space"] = actual_space or scope.get("space")
    return scope, root


def build(cfg, report, cap=MAX_PAGES):
    """List metadata within each authorized scope, retaining failure status."""
    inventory = {"scopes": [], "pages": [], "coverage": "not started",
                 "limit_per_scope": cap}
    report["inventory"] = inventory
    try:
        scopes = _scopes(cfg, report)
    except Exception as exc:
        inventory["coverage"] = "unavailable"
        inventory["scopes"].append({"status": "unavailable", "detail": str(exc)})
        return report
    if not scopes:
        inventory["coverage"] = "unconfigured"
        return report
    if not (cfg.get("confluence") or {}).get("base_url"):
        inventory["coverage"] = "unavailable"
        inventory["scopes"] = [dict(scope, status="unavailable",
                                    detail="Confluence connection missing")
                               for scope in scopes]
        return report
    global_pages = {}
    for configured in scopes:
        entry = dict(configured, status="complete", retrieved=0, scanned=0)
        inventory["scopes"].append(entry)
        seen = set()
        try:
            resolved = _resolve(cfg, configured)
            root = None
            if isinstance(resolved, tuple):
                scope, root = resolved
                entry["root_id"] = scope["root_id"]
                entry["space"] = scope.get("space")
            else:
                scope = resolved

            def append(item):
                page_id = str(item.get("id") or "")
                if not page_id or page_id in seen:
                    return False
                ancestors = [str(a.get("id")) for a in (item.get("ancestors") or [])
                             if isinstance(a, dict) and a.get("id")]
                if scope["type"] == "page_tree" and page_id != scope["root_id"] and scope["root_id"] not in ancestors:
                    return False
                seen.add(page_id)
                page = global_pages.get(page_id)
                if page is None:
                    page = {"space": scope.get("space"), "id": page_id,
                            "title": item.get("title") or "",
                            "type": item.get("type") or "page",
                            "updated": (item.get("version") or {}).get("when") or "unknown",
                            "ancestors": ancestors,
                            "scope_indices": [],
                            "state": "metadata only; content not evaluated"}
                    global_pages[page_id] = page
                    inventory["pages"].append(page)
                page["scope_indices"].append(len(inventory["scopes"]) - 1)
                return True

            if root is not None:
                append(root)
            start = 0
            # Cap is based on scanned search rows. Root metadata is separate.
            # A server-side ancestor filter prevents sibling pages entering scope.
            while start < cap:
                size = min(PAGE_SIZE, cap - start)
                if scope["type"] == "page_tree":
                    rows, has_more = sources.list_confluence_inventory(
                        cfg, scope.get("space"), start=start, limit=size,
                        ancestor_id=scope["root_id"])
                else:
                    rows, has_more = sources.list_confluence_inventory(
                        cfg, scope["space"], start=start, limit=size)
                if not rows:
                    if has_more:
                        entry["status"] = "incomplete"
                        entry["detail"] = "Empty search page despite continuation"
                    break
                entry["scanned"] += len(rows)
                new_ids = 0
                for item in rows:
                    new_ids += int(append(item))
                start += len(rows)
                if has_more and new_ids == 0:
                    entry["status"] = "incomplete"
                    entry["detail"] = "Pagination made no unique-page progress"
                    break
                if not has_more:
                    break
                if start >= cap:
                    entry["status"] = "truncated"
                    entry["detail"] = "Additional search pages beyond per-scope cap"
                    break
            entry["retrieved"] = len(seen)
        except Exception as exc:
            entry["status"] = "incomplete" if seen else "unavailable"
            entry["retrieved"] = len(seen)
            entry["detail"] = "{}: {}".format(type(exc).__name__, str(exc)[:160])
    inventory["coverage"] = ("complete" if all(
        s["status"] == "complete" for s in inventory["scopes"]) else "partial")
    return report


def summary(report):
    inv = report["inventory"]
    lines = ["Confluence inventory: {} (metadata only)".format(inv["coverage"])]
    for item in inv["scopes"]:
        name = ("Page tree " + str(item.get("root_id") or item.get("root_title"))
                if item.get("type") == "page_tree" else "Space " + str(item.get("space")))
        lines.append("  {}: {} ({} unique pages, {} search rows){}".format(
            name, item["status"], item.get("retrieved", 0),
            item.get("scanned", 0),
            "; " + item["detail"] if item.get("detail") else ""))
    return "\n".join(lines)


def markdown(report):
    inv = report["inventory"]
    lines = ["## Confluence discovery inventory", "",
             "- Overall coverage: " + inv["coverage"],
             "- Page content and suitability: not yet assessed",
             "- Search-row cap per scope: {}".format(inv["limit_per_scope"]), ""]
    for index, scope in enumerate(inv["scopes"]):
        name = ("Page tree " + str(scope.get("root_id") or scope.get("root_title"))
                if scope.get("type") == "page_tree" else "Space " + str(scope.get("space")))
        lines += ["### " + name,
                  "- Space: " + str(scope.get("space") or "unknown"),
                  "- Coverage: {} ({} unique pages; {} search rows)".format(
                      scope["status"], scope.get("retrieved", 0), scope.get("scanned", 0))]
        if scope.get("detail"):
            lines.append("- Limitation: " + scope["detail"])
        lines.append("")
        for page in inv["pages"]:
            if index not in page["scope_indices"]:
                continue
            lines.append("- {} | {} | {} | updated {} | ancestors: {}".format(
                page["id"], page["title"], page["type"], page["updated"],
                ", ".join(page["ancestors"]) or "none"))
        lines.append("")
    return "\n".join(lines) + "\n"
