"""Read-only, bounded Confluence inventory with explicit coverage accounting.

This is a discovery *index*, not evidence ranking or confirmed configuration.
"""
from core import sources

PAGE_SIZE = 25
MAX_PAGES = 100


def _spaces(cfg, report):
    spaces = set()
    default = (cfg.get("confluence") or {}).get("space")
    for raw in list(cfg.get("products") or []) + list(cfg.get("workstreams") or []):
        if raw.get("confluence_space"):
            spaces.add(raw["confluence_space"])
        elif raw.get("confluence_page") or raw.get("confluence_page_id"):
            if default:
                spaces.add(default)
    if default:
        spaces.add(default)
    return sorted(spaces)


def build(cfg, report, cap=MAX_PAGES):
    """Enumerate page metadata, preserving failure and truncation status."""
    spaces = _spaces(cfg, report)
    inventory = {"scopes": [], "pages": [], "coverage": "not started",
                 "limit_per_space": cap}
    report["inventory"] = inventory
    if not spaces:
        inventory["coverage"] = "unconfigured"
        return report
    if not (cfg.get("confluence") or {}).get("base_url"):
        inventory["coverage"] = "unavailable"
        inventory["scopes"] = [{"space": s, "status": "unavailable",
                                "detail": "Confluence connection missing"} for s in spaces]
        return report
    for space in spaces:
        entry = {"space": space, "status": "complete", "retrieved": 0}
        inventory["scopes"].append(entry)
        offset = 0
        seen = set()
        try:
            while offset < cap:
                size = min(PAGE_SIZE, cap - offset)
                rows, has_more = sources.list_confluence_inventory(
                    cfg, space, start=offset, limit=size)
                if not rows and has_more:
                    entry["status"] = "incomplete"
                    entry["detail"] = "Empty page returned with a continuation token"
                    break
                for item in rows:
                    page_id = str(item.get("id") or "")
                    if not page_id or page_id in seen:
                        continue
                    seen.add(page_id)
                    ancestors = [str(a.get("id")) for a in (item.get("ancestors") or [])
                                 if isinstance(a, dict) and a.get("id")]
                    inventory["pages"].append({
                        "space": space, "id": page_id,
                        "title": item.get("title") or "",
                        "type": item.get("type") or "page",
                        "updated": (item.get("version") or {}).get("when") or "unknown",
                        "ancestors": ancestors,
                        "state": "metadata only; content not evaluated",
                    })
                offset += len(rows)
                if not has_more:
                    break
                if not rows:
                    entry["status"] = "incomplete"
                    entry["detail"] = "Unable to advance pagination"
                    break
                if offset >= cap:
                    entry["status"] = "truncated"
                    entry["detail"] = "Additional pages exist beyond per-space cap"
                    break
            entry["retrieved"] = len(seen)
        except Exception as exc:
            entry["status"] = "unavailable" if not seen else "incomplete"
            entry["retrieved"] = len(seen)
            entry["detail"] = "{}: {}".format(type(exc).__name__, str(exc)[:160])
    statuses = [x["status"] for x in inventory["scopes"]]
    inventory["coverage"] = ("complete" if all(x == "complete" for x in statuses)
                             else "partial")
    return report


def summary(report):
    inv = report["inventory"]
    lines = ["Confluence inventory: {} (metadata only)".format(inv["coverage"])]
    for item in inv["scopes"]:
        lines.append("  {}: {} ({} pages){}".format(
            item["space"], item["status"], item.get("retrieved", 0),
            "; " + item["detail"] if item.get("detail") else ""))
    return "\n".join(lines)


def markdown(report):
    inv = report["inventory"]
    lines = ["## Confluence discovery inventory", "",
             "- Overall coverage: " + inv["coverage"],
             "- Page content and suitability: not yet assessed",
             "- Page-count cap per space: {}".format(inv["limit_per_space"]), ""]
    for scope in inv["scopes"]:
        lines.append("### Space {}".format(scope["space"]))
        lines.append("- Coverage: {} ({} unique pages)".format(
            scope["status"], scope.get("retrieved", 0)))
        if scope.get("detail"):
            lines.append("- Limitation: " + scope["detail"])
        lines.append("")
        for page in inv["pages"]:
            if page["space"] != scope["space"]:
                continue
            lines.append("- {} | {} | {} | updated {} | ancestors: {}".format(
                page["id"], page["title"], page["type"], page["updated"],
                ", ".join(page["ancestors"]) or "none"))
        lines.append("")
    return "\n".join(lines) + "\n"
