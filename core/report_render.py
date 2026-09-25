"""Deterministic Markdown for the weekly report."""

import datetime as dt
import re

from core import checklist
from core import products as product_core


_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_HEADING = re.compile(r"^#{2,5}\s+(.+?)\s*$")

SIGNAL_FOOTER = (
    "_Signal is a rule, not a judgement: At risk means a blocked item, a "
    "passed due date, or under half done within 14 days of the due date._"
)


def strip_links(text):
    """Markdown links become their labels, so a later model cannot cite them."""
    return _LINK.sub(r"\1", text or "")


def extract_sections(markdown, names):
    """Body under each named heading. `names` come from prompts.heading."""
    wanted = list(names or [])
    found = {name: [] for name in wanted}
    current = None
    for line in (markdown or "").splitlines():
        match = _HEADING.match(line)
        if match:
            title = match.group(1).strip()
            current = title if title in found else None
            continue
        if current is not None:
            found[current].append(line)
    return {name: "\n".join(found[name]).strip() for name in wanted}


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


_REGISTER_COLUMNS = (
    ("decision", "New decisions"),
    ("risk", "New risks"),
    ("adr", "New ADRs"),
)


def _configured_register_types(rows):
    found = []
    for record in _register_records(rows):
        kind = record.get("type")
        if kind in {name for name, _label in _REGISTER_COLUMNS} and kind not in found:
            found.append(kind)
    return [pair for pair in _REGISTER_COLUMNS if pair[0] in found]


def _new_register_counts(records, product, ws, epics, claimed):
    """New entries for this row. Each entry is counted on one row only."""
    counts = {kind: 0 for kind, _label in _REGISTER_COLUMNS}
    epic_keys = {epic.get("key") for epic in epics if epic.get("key")}
    for record in records or []:
        kind = record.get("type")
        if kind not in counts:
            continue
        scope = record.get("scope") or {}
        for entry in record.get("entries") or []:
            if entry.get("change") != "new":
                continue
            marker = entry.get("page_id") or id(entry)
            if marker in claimed:
                continue
            matched = ""
            for key in entry.get("keys") or []:
                if key in epic_keys:
                    matched = key
                    break
            owns = False
            if scope.get("workstream"):
                owns = scope.get("workstream") == ws.get("abbrev")
            elif matched:
                owns = True
            elif not claimed_scope_elsewhere(scope, product, ws):
                owns = True
            if owns:
                counts[kind] += 1
                claimed.add(marker)
    return counts


def claimed_scope_elsewhere(scope, product, ws):
    """True when a later row should not absorb an unmatched portfolio entry."""
    return False


def at_a_glance(groups, rows):
    by_ws = {ws["abbrev"]: row for ws, row in rows}
    extra = _configured_register_types(rows)
    head = ["Product", "Workstream", "Epics active", "Items in window",
            "Moved", "Blocked", "Docs changed"]
    head.extend(label for _kind, label in extra)
    align = ["---------", "------------", "-------------:", "----------------:",
             "------:", "--------:", "-------------:"]
    align.extend("-------------:" for _pair in extra)
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join(align) + "|"]
    records = _register_records(rows)
    claimed = set()
    first_of_product = {}
    for product, streams in groups:
        abbrev = product.get("abbrev") or ""
        first_of_product[abbrev] = streams[0]["abbrev"] if streams else ""
        for ws in streams:
            row = by_ws.get(ws["abbrev"]) or {}
            epics = [e for e in row.get("epics") or [] if e.get("key")]
            items = [it for it in row.get("items") or [] if it.get("source") == "Jira"]
            docs = [it for it in row.get("items") or [] if it.get("source") != "Jira"]
            blocked = sum(int(e.get("blocked") or 0) for e in epics)
            cells = [
                product.get("abbrev") or "—", ws["abbrev"], str(len(epics)),
                str(len(items)), str(len(row.get("changed") or [])),
                str(blocked), str(len(docs)),
            ]
            if extra:
                counts = _new_register_counts(records, product, ws, epics, claimed)
                cells.extend(str(counts[kind]) for kind, _label in extra)
            lines.append("| " + " | ".join(cells) + " |")
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
    for entry in epic.get("register_entries") or []:
        kind = (entry.get("register_type") or entry.get("kind") or "entry").capitalize()
        change = entry.get("change") or "changed"
        lines.append(
            f"- {kind} ({change}): "
            f"{_md_link(entry.get('title') or 'entry', entry.get('url'), links)}"
        )
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


def append_registers(lines, records, level, since, match):
    """Print the registers whose scope matches. No heading when none do."""
    chosen = [record for record in (records or []) if match(record.get("scope") or {})]
    if not chosen:
        return
    lines.append("### Decisions, risks and ADRs")
    lines.append("")
    for record in chosen:
        if level == "partner" and not record.get("partner_visible"):
            continue
        lines.append(register_block(record, level, {"since": since}))
        lines.append("")


def _register_records(rows):
    for _ws, row in rows:
        if row.get("registers"):
            return row["registers"]
    return []


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
            for item in row.get("items") or []:
                if item.get("source") != "SharePoint":
                    continue
                title = (item.get("title") or "file").replace("|", "\\|")
                lines.append(
                    f"| — | {_md_link(title, item.get('url'))} | file |  |  | "
                    f"{str(item.get('updated') or '')[:10]} |"
                )
            lines.append("")
    records = _register_records(rows)
    for record in records:
        lines.extend(_register_source_table(record))
        lines.append("")
    return "\n".join(lines)


def _register_source_table(record):
    """Summary page first, then every new and changed entry."""
    root = record.get("root") or {}
    lines = [
        f"### {record.get('name') or 'Register'}",
        "",
        "| Entry | Change | Status | Updated |",
        "|-------|--------|--------|---------|",
        f"| {_md_link(record.get('name') or 'summary', root.get('url'))} | summary |  | "
        f"{str(root.get('updated') or '')[:10]} |",
    ]
    for entry in record.get("entries") or []:
        if entry.get("change") not in ("new", "changed"):
            continue
        title = (entry.get("title") or "entry").replace("|", "\\|")
        lines.append(
            f"| {_md_link(title, entry.get('url'))} | {entry.get('change') or ''} | "
            f"{entry.get('status') or ''} | {str(entry.get('updated') or '')[:10]} |"
        )
    return lines


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


def _docs_under(pages, heading):
    block = docs_block(pages)
    if not block:
        return ""
    return block.replace("#### Documentation changed", heading, 1)


def render_pm(cfg, groups, rows, sections, window, scope_note, who="pm", team_pages=None):
    today = dt.date.today().isoformat()
    from core import audience
    name = audience.display_name(cfg, who)
    title = "# Weekly State-of-Product Report"
    if who != "pm":
        title += f" — {name}"
    label = (window or {}).get("label") or "since last report"
    lines = [
        title,
        f"_Audience: {name} · Window: {label} · Generated {today}_",
        "",
    ]
    if scope_note:
        lines.append(scope_note.strip())
        lines.append("")
    show_products = bool(product_core.listed_products(cfg)) or len(groups) > 1
    since = ""
    start = (window or {}).get("start")
    if hasattr(start, "isoformat"):
        since = start.isoformat()
    records = _register_records(rows)
    if show_products and groups:
        lines.append("## At a glance")
        lines.append("")
        lines.append(at_a_glance(groups, rows))
        lines.append("")
        block = _docs_under(team_pages, "### Team pages changed")
        if block:
            lines.extend([block, ""])
        append_registers(lines, records, who, since, lambda scope: not scope)
    else:
        block = _docs_under(team_pages, "## Team pages changed")
        if block:
            lines.extend([block, ""])
    body_by = {ws["abbrev"]: body for ws, body in sections}
    row_by = {ws["abbrev"]: row for ws, row in rows}
    for product, streams in groups or [({}, [ws for ws, _row in rows])]:
        product_docs = [it for ws in streams
                        for it in (row_by.get(ws["abbrev"]) or {}).get("items") or []
                        if it.get("product_only")]
        if show_products and product:
            lines.append(f"## {product.get('name')} ({product.get('abbrev')})")
            lines.append("")
            goal = checklist.product_goal(product)
            if goal:
                lines.append(f"Product Goal: {goal}")
                lines.append("")
            lines.extend(_increment_lines(cfg, product))
            block = _docs_under(product_docs, "### Product pages changed")
            if block:
                lines.extend([block, ""])
            abbrev = product.get("abbrev")
            append_registers(
                lines, records, who, since,
                lambda scope, abbrev=abbrev: scope.get("product") == abbrev)
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
                     if it.get("source") in ("Confluence", "SharePoint") and not it.get("epic")
                     and not (show_products and product and it.get("product_only"))]
            block = docs_block(loose)
            if block and heading != "###":
                block = block.replace("#### ", "### ", 1)
            if block:
                lines.append(block)
                lines.append("")
            abbrev = ws["abbrev"]
            append_registers(
                lines, records, who, since,
                lambda scope, abbrev=abbrev: scope.get("workstream") == abbrev)
    lines.append(sources_appendix(groups, rows))
    lines.append("")
    lines.append(SIGNAL_FOOTER)
    lines.append("")
    return "\n".join(lines)


def render_leadership(cfg, groups, rows, summaries, window):
    from core import audience
    today = dt.date.today().isoformat()
    name = audience.display_name(cfg, "leadership")
    label = (window or {}).get("label") or "since last report"
    several = len(groups) > 1
    lines = [
        f"# Weekly State-of-Product Report — {name}",
        f"_Audience: {name} · Window: {label} · Generated {today}_",
        "",
    ]
    if not several:
        lines.extend([
            "## Summary",
            "",
            "\n\n".join(summaries) if summaries else "Nothing this period.",
            "",
        ])
    by_ws = {ws["abbrev"]: row for ws, row in rows}
    for index, (product, streams) in enumerate(groups):
        lines.append(f"## {product.get('name')} ({product.get('abbrev')})")
        lines.append("")
        if several:
            lines.append(summaries[index] if index < len(summaries) else "Nothing this period.")
            lines.append("")
        lines.append("| Epic | Workstream | Status | Progress | Signal | Target |")
        lines.append("|------|------------|--------|---------:|--------|--------|")
        for ws in streams:
            for epic in (by_ws.get(ws["abbrev"]) or {}).get("epics") or []:
                if not epic.get("key"):
                    continue
                lines.append(
                    f"| {_md_link(epic['key'], epic.get('url'))} {epic.get('summary') or ''} | "
                    f"{ws['abbrev']} | {epic.get('status') or ''} | "
                    f"{epic.get('children_done') or 0} / {epic.get('children_total') or 0} | "
                    f"{epic.get('signal') or ''} | {epic.get('due') or '—'} |"
                )
        lines.append("")
        abbrev = product.get("abbrev")
        since = ""
        start = (window or {}).get("start")
        if hasattr(start, "isoformat"):
            since = start.isoformat()
        append_registers(
            lines, _register_records(rows), "leadership", since,
            lambda scope, abbrev=abbrev: scope.get("product") == abbrev)
    lines.extend(_leadership_sources(rows))
    lines.append(SIGNAL_FOOTER)
    lines.append("")
    return "\n".join(lines)


def _leadership_sources(rows):
    """Epics and documents only. No ticket rows."""
    lines = ["## Sources", ""]
    for _ws, row in rows:
        for epic in row.get("epics") or []:
            if not epic.get("key"):
                continue
            lines.append(f"- {_md_link(epic['key'], epic.get('url'))} {epic.get('summary') or ''}")
        for item in row.get("items") or []:
            if item.get("source") == "Jira":
                continue
            lines.append(f"- {_md_link(item.get('title') or 'page', item.get('url'))}")
    lines.append("")
    return lines


def render_partner(cfg, groups, rows, summaries, window):
    from core import audience
    today = dt.date.today().isoformat()
    name = audience.display_name(cfg, "partner")
    opts = audience.settings(cfg)["partner"]
    label = (window or {}).get("label") or "since last report"
    lines = [
        f"# Weekly State-of-Product Report — {name}",
        f"_Audience: {name} · Window: {label} · Generated {today}_",
        "",
        "\n\n".join(summaries),
        "",
    ]
    by_ws = {ws["abbrev"]: row for ws, row in rows}
    for product, streams in groups:
        lines.append(f"## {product.get('name')}")
        lines.append("")
        lines.append("| Feature | Status | Progress |")
        lines.append("|---------|--------|---------:|")
        for ws in streams:
            for epic in (by_ws.get(ws["abbrev"]) or {}).get("epics") or []:
                if not epic.get("key"):
                    continue
                if not audience.partner_visible_epic(epic, ws, opts):
                    continue
                total = epic.get("children_total") or 0
                done = epic.get("children_done") or 0
                pct = f"{int(100 * done / total)}%" if total else "0%"
                phrase = {"new": "Planned", "done": "Delivered"}.get(
                    (epic.get("status_category") or "").lower(), "In progress")
                feature = epic.get("summary") or epic["key"]
                if opts.get("include_jira_links"):
                    feature = _md_link(feature, epic.get("url"))
                lines.append(f"| {feature} | {phrase} | {pct} |")
        reading = []
        for ws in streams:
            for item in (by_ws.get(ws["abbrev"]) or {}).get("items") or []:
                if item.get("source") == "Jira":
                    continue
                if not audience.partner_visible_page(item, opts):
                    continue
                title = item.get("title") or "page"
                if opts.get("include_confluence_links"):
                    title = _md_link(title, item.get("url"))
                reading.append(f"- {title}")
        if reading:
            lines.append("Further reading:")
            lines.append("")
            lines.extend(reading)
        lines.append("")
    return "\n".join(lines)
