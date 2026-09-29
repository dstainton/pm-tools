"""Deterministic blocker links from Jira issue links.

Used by `pm today --all` and the product-management report. No new command.
"""

from core import blocked, conventions, render, sources


def _blocked_by(link, cfg):
    relation = (link.get("relation") or "").strip().lower()
    if relation in conventions.names(cfg, "blocked_by_links"):
        return True
    return (link.get("direction") == "inward"
            and relation in conventions.names(cfg, "blocks_links"))


def _blocks(link, cfg):
    relation = (link.get("relation") or "").strip().lower()
    return (link.get("direction") == "outward"
            and relation in conventions.names(cfg, "blocks_links"))


def collect(cfg, issues, limit=15):
    """Links for blocked issues, capped so a report does not fetch every ticket.

    Each row is `{key, summary, workstream, blocked_by, blocks}`.
    A fetch that fails is skipped.
    """
    jira = (cfg or {}).get("jira") or {}
    if not jira.get("base_url"):
        return []
    blocked_items = [issue for issue in (issues or []) if blocked.is_blocked(issue, cfg)]
    if not blocked_items:
        blocked_items = []
    rows = []
    for issue in blocked_items[:limit]:
        key = issue.get("key")
        if not key:
            continue
        try:
            links = sources.fetch_issue_links(jira, key)
        except Exception:                              # noqa: BLE001
            continue
        blocked_by = []
        blocks = []
        for link in links:
            other = {
                "key": link.get("key") or "",
                "summary": link.get("summary") or "",
                "url": render.browse_url(cfg, link.get("key")),
            }
            if not other["key"]:
                continue
            if _blocked_by(link, cfg):
                blocked_by.append(other)
            elif _blocks(link, cfg):
                blocks.append(other)
        if not blocked_by and not blocks:
            continue
        rows.append({
            "key": key,
            "url": issue.get("url") or render.browse_url(cfg, key),
            "summary": issue.get("summary") or issue.get("title") or "",
            "workstream": issue.get("workstream") or "",
            "blocked_by": blocked_by,
            "blocks": blocks,
        })
    return rows


def lines_for(rows, known_keys=None):
    """Short lines. A link whose other key is outside `known_keys` is external
    when `known_keys` is provided.
    """
    known = set(known_keys or [])
    lines = []
    for row in rows or []:
        this = render.markdown_link(row.get("key"), row.get("url"))
        for other in row.get("blocked_by") or []:
            where = ""
            if known and other.get("key") and other["key"] not in known:
                where = " (outside this report)"
            that = render.issue_link(other.get("key"), other.get("summary"), other.get("url"))
            lines.append(f"- {this} is blocked by {that}{where}")
        for other in row.get("blocks") or []:
            that = render.issue_link(other.get("key"), other.get("summary"), other.get("url"))
            lines.append(f"- {this} blocks {that}")
    return lines
