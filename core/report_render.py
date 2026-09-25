"""Deterministic Markdown for the weekly report."""

import datetime as dt

from core import checklist
from core import products as product_core


def demote(text, levels):
    """Push every Markdown heading down by `levels`."""
    if not levels:
        return text or ""
    prefix = "#" * int(levels)
    lines = []
    for line in (text or "").splitlines():
        if line.startswith("#"):
            lines.append(prefix + line)
        else:
            lines.append(line)
    return "\n".join(lines)


def _link(item, links=True):
    title = (item.get("title") or item.get("summary") or item.get("key") or "item")
    title = title.replace("|", "\\|")
    url = item.get("url") or ""
    if links and url:
        label = item.get("key") or title
        if item.get("key") and item.get("summary"):
            return f"[{item['key']}]({url}) {item['summary']}"
        return f"[{label}]({url})"
    return title


def _md_link(label, url, links=True):
    label = (label or "link").replace("|", "\\|")
    if links and url:
        return f"[{label}]({url})"
    return label


def at_a_glance(groups, rows):
    by_ws = {ws["abbrev"]: row for ws, row in rows}
    lines = [
        "| Product | Workstream | Epics active | Items in window | Moved | Blocked | Docs changed |",
        "|---------|------------|-------------:|----------------:|------:|--------:|-------------:|",
    ]
    for product, streams in groups:
        for ws in streams:
            row = by_ws.get(ws["abbrev"]) or {}
            epics = [e for e in row.get("epics") or [] if e.get("key")]
            items = [it for it in row.get("items") or [] if it.get("source") == "Jira"]
            docs = [it for it in row.get("items") or [] if it.get("source") != "Jira"]
            blocked = sum(int(e.get("blocked") or 0) for e in epics)
            lines.append(
                f"| {product.get('abbrev') or '—'} | {ws['abbrev']} | {len(epics)} | "
                f"{len(items)} | {len(row.get('changed') or [])} | {blocked} | {len(docs)} |"
            )
    return "\n".join(lines)


def epic_block(epic, links=True):
    if not epic.get("key"):
        lines = ["**Not under an Epic**", ""]
        for item in epic.get("items") or []:
            lines.append(f"- In this Sprint: {_link(item, links)}")
        return "\n".join(lines)
    done = epic.get("children_done") or 0
    total = epic.get("children_total") or 0
    due = epic.get("due") or ""
    due_bit = f" · due {due}" if due else ""
    scope = ""
    if epic.get("in_scope") is False:
        scope = " · Epic in no workstream"
    signal = epic.get("signal") or ""
    head = (
        f"**{_md_link(epic['key'], epic.get('url') or '', links)} {epic.get('summary') or ''}**"
        f" — {epic.get('status') or '—'} · {done} of {total} done{due_bit}"
        f"{(' · ' + signal) if signal else ''}{scope}"
    )
    lines = [head, ""]
    for item in epic.get("moved") or []:
        lines.append(f"- Moved: {_link(item, links)}")
    rest = [it for it in epic.get("items") or [] if it not in (epic.get("moved") or [])]
    if rest:
        bits = ", ".join(_link(it, links) for it in rest[:8])
        lines.append(f"- In this Sprint: {bits}")
    for page in epic.get("pages") or []:
        kind = page.get("kind") or page.get("type") or "page"
        lines.append(f"- Doc: {_md_link(page.get('title') or 'page', page.get('url'), links)} — {kind}")
    return "\n".join(lines)


def docs_block(pages):
    if not pages:
        return ""
    lines = ["#### Documentation changed", ""]
    for page in pages:
        when = page.get("updated") or ""
        who = f" by {page['updated_by']}" if page.get("updated_by") else ""
        extra = " (Listed by title.)" if page.get("title_only") or page.get("unsummarised") else ""
        summary = f" {page['summary']}" if page.get("summary") else ""
        lines.append(
            f"- {_md_link(page.get('title') or 'page', page.get('url'))} — "
            f"{page.get('type') or 'page'}, updated {when}{who}.{summary}{extra}"
        )
    return "\n".join(lines)


def register_block(record, level="pm", opts=None):
    opts = opts or {}
    root = record.get("root") or {}
    since = opts.get("since") or ""
    new_n = sum(1 for e in record.get("entries") or [] if e.get("change") == "new")
    changed_n = sum(1 for e in record.get("entries") or [] if e.get("change") == "changed")
    count = f"{record.get('total') or 0} entries"
    if new_n or changed_n:
        bits = []
        if new_n:
            bits.append(f"{new_n} new")
        if changed_n:
            bits.append(f"{changed_n} changed")
        count += " · " + " · ".join(bits)
        if since:
            count += f" since {since}"
    else:
        count += f" · no new or changed entries" + (f" since {since}" if since else "")
    if root.get("edited_in_window"):
        who = f" by {root['updated_by']}" if root.get("updated_by") else ""
        count += f" · summary page updated {root.get('updated') or ''}{who}"
    lines = [f"**{_md_link(record.get('name') or 'Register', root.get('url'))}** — {count}", ""]
    show_status = level != "partner"
    show_owner = level == "pm" or (level == "leadership" and record.get("type") == "decision")
    for entry in record.get("entries") or []:
        if level == "leadership" and record.get("type") == "risk":
            if not (entry.get("high") or entry.get("change") == "new"):
                continue
        if level == "partner" and not record.get("partner_visible"):
            continue
        change = (entry.get("change") or "changed").title()
        high = ", High" if entry.get("high") else ""
        status = ""
        if show_status:
            if entry.get("status_was") and entry.get("status") and entry["status_was"] != entry["status"]:
                status = f" — {entry['status_was']} → {entry['status']}"
            elif entry.get("status"):
                status = f" — {entry['status']}"
        owner = ""
        if show_owner and (entry.get("fields") or {}).get("Owner"):
            owner = f" · {entry['fields']['Owner']}"
        summary = f" {entry['summary']}" if entry.get("summary") else ""
        lines.append(
            f"- {change}{high}: {_md_link(entry.get('title') or 'entry', entry.get('url'))}"
            f"{status}{owner}.{summary}"
        )
    for removed in record.get("removed") or []:
        if level == "partner":
            continue
        lines.append(f"- Removed: {removed.get('title') or removed.get('page_id')}.")
    return "\n".join(lines)


def sources_appendix(groups, rows):
    by_ws = {ws["abbrev"]: row for ws, row in rows}
    lines = ["## Sources", ""]
    for product, streams in groups:
        for ws in streams:
            row = by_ws.get(ws["abbrev"]) or {}
            lines.append(f"### {ws['name']} ({ws['abbrev']})")
            lines.append("")
            lines.append("| Epic | Item | Type | Status | Assignee | Updated |")
            lines.append("|------|------|------|--------|----------|---------|")
            for epic in row.get("epics") or []:
                label = epic.get("summary") or "Not under an Epic"
                if epic.get("key"):
                    label = f"{epic['key']} {label}"
                for item in epic.get("items") or []:
                    title = (item.get("summary") or item.get("title") or "").replace("|", "\\|")
                    link = _md_link(item.get("key") or title, item.get("url"))
                    lines.append(
                        f"| {label} | {link} {title} | {item.get('issuetype') or ''} | "
                        f"{item.get('status') or ''} | {item.get('assignee') or ''} | "
                        f"{str(item.get('updated') or '')[:10]} |"
                    )
            lines.append("")
    return "\n".join(lines)


def _increment_lines(cfg, product):
    items = checklist.definition_items(cfg, product)
    if not items:
        return []
    lines = ["### Increment", "", "Definition of Done for this Increment:", ""]
    for item in items:
        if item.get("label"):
            lines.append(f"- {item['text']} _(label: {item['label']})_")
        else:
            lines.append(f"- {item['text']}")
    lines.append("")
    return lines


def render_pm(cfg, groups, rows, sections, window, scope_note):
    today = dt.date.today().isoformat()
    name = ((cfg.get("audiences") or {}).get("pm") or {}).get("name") or "Product management"
    label = (window or {}).get("label") or "since last report"
    lines = [
        "# Weekly State-of-Product Report",
        f"_Audience: {name} · Window: {label} · Generated {today}_",
        "",
    ]
    if scope_note:
        lines.append(scope_note.strip())
        lines.append("")
    show_products = bool(product_core.listed_products(cfg)) or len(groups) > 1
    if show_products and groups:
        lines.append("## At a glance")
        lines.append("")
        lines.append(at_a_glance(groups, rows))
        lines.append("")
    body_by = {ws["abbrev"]: body for ws, body in sections}
    row_by = {ws["abbrev"]: row for ws, row in rows}
    for product, streams in groups or [({}, [ws for ws, _row in rows])]:
        if show_products and product:
            lines.append(f"## {product.get('name')} ({product.get('abbrev')})")
            lines.append("")
            goal = checklist.product_goal(product)
            if goal:
                lines.append(f"Product Goal: {goal}")
                lines.append("")
            lines.extend(_increment_lines(cfg, product))
        for ws in streams:
            heading = "###" if show_products and product else "##"
            lines.append(f"{heading} {ws['name']} ({ws['abbrev']})")
            lines.append("")
            body = body_by.get(ws["abbrev"]) or ""
            lines.append(demote(body, 1 if heading == "###" else 0))
            lines.append("")
            row = row_by.get(ws["abbrev"]) or {}
            epics = row.get("epics") or []
            if epics:
                lines.append("#### Epics" if heading == "###" else "### Epics")
                lines.append("")
                for epic in epics:
                    if not epic.get("key") and not epic.get("items"):
                        continue
                    lines.append(epic_block(epic))
                    lines.append("")
            loose = [it for it in row.get("items") or []
                     if it.get("source") == "Confluence" and not it.get("epic")]
            block = docs_block(loose)
            if block and heading != "###":
                block = block.replace("#### ", "### ", 1)
            if block:
                lines.append(block)
                lines.append("")
    lines.append(sources_appendix(groups, rows))
    lines.append("")
    lines.append(
        "_Signal is a rule, not a judgement: At risk means a blocked item, a "
        "passed due date, or under half done within 14 days of the due date._"
    )
    lines.append("")
    return "\n".join(lines)
