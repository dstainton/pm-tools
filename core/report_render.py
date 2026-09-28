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


def _decision_needed(entry):
    """An open ask, not every decision that was recorded."""
    status = str(entry.get("status") or "").strip().lower()
    if any(word in status for word in ("wait", "open", "proposed", "needed", "pending")):
        return True
    if not status and entry.get("change") == "new":
        return True
    return False


def _glance_counts(records, product, ws, epics, today):
    """At risk, due soon, open decisions, and new high risks for one row."""
    today = today or dt.date.today()
    soon = today + dt.timedelta(days=14)
    active = []
    at_risk = 0
    blocked = 0
    due = 0
    for epic in epics:
        if not epic.get("key"):
            continue
        if str(epic.get("status_category") or "").lower() == "done":
            continue
        active.append(epic)
        if epic.get("signal") == "At risk":
            at_risk += 1
        blocked += int(epic.get("blocked") or 0)
        due_date = None
        if epic.get("due"):
            try:
                due_date = dt.date.fromisoformat(str(epic["due"])[:10])
            except ValueError:
                due_date = None
        if due_date and due_date <= soon:
            due += 1
    decisions = 0
    high_risks = 0
    epic_keys = {epic.get("key") for epic in epics if epic.get("key")}
    for record in records or []:
        kind = record.get("type")
        scope = record.get("scope") or {}
        owns = False
        if scope.get("workstream"):
            owns = scope.get("workstream") == ws.get("abbrev")
        elif scope.get("product"):
            owns = scope.get("product") == (product.get("abbrev") or "")
        else:
            owns = True
        if not owns and not epic_keys:
            continue
        for entry in record.get("entries") or []:
            matched = any(key in epic_keys for key in (entry.get("keys") or []))
            if scope.get("workstream") and not owns:
                continue
            if scope.get("product") and not owns and not matched:
                continue
            if not scope and not matched and not owns:
                continue
            if kind == "decision" and _decision_needed(entry):
                decisions += 1
            if kind == "risk" and entry.get("high") and entry.get("change") == "new":
                high_risks += 1
    return {
        "active": len(active),
        "at_risk": at_risk,
        "blocked": blocked,
        "due": due,
        "decisions": decisions,
        "high_risks": high_risks,
    }


def at_a_glance(groups, rows, today=None):
    """Portfolio row: state that changes a decision, not activity volume."""
    by_ws = {ws["abbrev"]: row for ws, row in rows}
    head = ["Product", "Workstream", "Active Epics", "At risk", "Blocked",
            "Due soon", "Decisions needed", "New high risks", "Docs changed"]
    align = ["---------", "------------", "-------------:", "--------:",
             "--------:", "---------:", "------------------:", "---------------:",
             "-------------:"]
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join(align) + "|"]
    records = _register_records(rows)
    for product, streams in groups:
        for ws in streams:
            row = by_ws.get(ws["abbrev"]) or {}
            epics = [e for e in row.get("epics") or [] if e.get("key")]
            docs = [it for it in row.get("items") or [] if it.get("source") != "Jira"]
            counts = _glance_counts(records, product, ws, epics, today)
            cells = [
                product.get("abbrev") or "—",
                ws["abbrev"],
                str(counts["active"]),
                str(counts["at_risk"]),
                str(counts["blocked"]),
                str(counts["due"]),
                str(counts["decisions"]),
                str(counts["high_risks"]),
                str(len(docs)),
            ]
            lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _due_date(epic):
    if not epic.get("due"):
        return None
    try:
        return dt.date.fromisoformat(str(epic["due"])[:10])
    except ValueError:
        return None


def _marked_for(entry, room):
    """True when a field or label names the room. A title is not enough."""
    room = (room or "").lower()
    fields = entry.get("fields") or {}
    for key, value in fields.items():
        blob = f"{key} {value}".lower()
        if room and room in blob:
            text = str(value).strip().lower()
            if text in ("no", "false", "none", "n/a", "-", ""):
                continue
            return True
    for label in entry.get("labels") or []:
        if room and room in str(label).lower():
            return True
    return False


def needs_attention(groups, rows, profile, dependencies=None, today=None):
    """Deterministic lines for the first screen. One epic, one line."""
    today = today or dt.date.today()
    soon = today + dt.timedelta(days=14)
    mode = (profile or {}).get("attention") or "pm"
    by_ws = {ws["abbrev"]: row for ws, row in rows}
    records = _register_records(rows)
    lines = []
    seen_epics = set()

    def epic_line(epic, ws, reason):
        key = epic.get("key")
        if not key or key in seen_epics:
            return
        seen_epics.add(key)
        label = epic.get("summary") or key
        lines.append(f"- {key} {label} ({ws.get('abbrev') or ''}): {reason}".rstrip())

    if mode in ("pm", "analyst", "developer", "service"):
        for product, streams in groups:
            for ws in streams:
                row = by_ws.get(ws["abbrev"]) or {}
                for epic in row.get("epics") or []:
                    if not epic.get("key"):
                        continue
                    if epic.get("signal") == "At risk":
                        reason = epic.get("signal_reason") or "at risk"
                        epic_line(epic, ws, reason)
                    elif mode == "pm":
                        due = _due_date(epic)
                        if due and due < today:
                            epic_line(epic, ws, f"overdue, due {epic.get('due')}")
                        elif due and due <= soon:
                            epic_line(epic, ws, f"due {epic.get('due')}")
                    blocked_n = int(epic.get("blocked") or 0)
                    if blocked_n and epic.get("key") not in seen_epics and mode in ("pm", "developer"):
                        epic_line(epic, ws, f"{blocked_n} blocked")

    for record in records:
        kind = record.get("type")
        allowed = set((profile or {}).get("registers") or ())
        if allowed and kind not in allowed:
            continue
        for entry in record.get("entries") or []:
            title = entry.get("title") or "entry"
            if kind == "decision" and _decision_needed(entry):
                if mode == "service" and not _page_hints(entry, profile.get("doc_hints") or ("experience", "service", "design")):
                    continue
                if mode == "analyst":
                    lines.append(f"- Decision affecting requirements: {title}")
                elif mode == "developer":
                    lines.append(f"- Technical decision: {title}")
                else:
                    lines.append(f"- Decision needed: {title}")
            if kind == "risk" and (entry.get("high") or entry.get("change") == "new"):
                prefix = "Service risk" if mode == "service" else "Risk"
                high = " (high)" if entry.get("high") else ""
                lines.append(f"- {prefix}{high}: {title}")
            if kind == "dependency" and entry.get("change") in ("new", "changed"):
                lines.append(f"- Dependency: {title}")
            if kind == "adr" and mode == "developer" and entry.get("change") in ("new", "changed"):
                lines.append(f"- ADR: {title}")

    for line in dependencies or []:
        if line not in lines:
            lines.append(line if line.startswith("- ") else f"- {line}")

    if mode == "service":
        for product, streams in groups:
            for ws in streams:
                row = by_ws.get(ws["abbrev"]) or {}
                for item in row.get("items") or []:
                    if item.get("source") == "Jira":
                        continue
                    if _page_hints(item, profile.get("doc_hints") or ()):
                        lines.append(f"- Service documentation changed: {item.get('title') or 'page'}")

    # Keep the first screen short. Later sections still have the detail.
    trimmed = []
    seen = set()
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        trimmed.append(line)
        if len(trimmed) >= 12:
            break
    return trimmed


def _page_hints(page, hints):
    from core import report_profiles
    return report_profiles.page_matches(page, hints)


def epic_block(epic, links=True, names=False):
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
    label = f"{epic['key']} {epic.get('summary') or ''}".strip()
    head = (
        f"**{_md_link(label, epic.get('url') or '', links)}**"
        f" — {epic.get('status') or '—'} · {done} of {total} done{due_bit}"
        f"{(' · ' + signal) if signal else ''}{scope}"
    )
    def linked(item):
        text = _link(item, links)
        if names and item.get("assignee"):
            text += f" ({item['assignee']})"
        return text

    lines = [head, ""]
    for item in epic.get("moved") or []:
        lines.append(f"- Moved: {linked(item)}")
    rest = [it for it in epic.get("items") or [] if it not in (epic.get("moved") or [])]
    if rest:
        bits = ", ".join(linked(it) for it in rest[:8])
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


def docs_block(pages, names=True):
    if not pages:
        return ""
    lines = ["#### Documentation changed", ""]
    for page in pages:
        when = page.get("updated") or ""
        who = ""
        if names and page.get("updated_by"):
            who = f" by {page['updated_by']}"
        extra = " (Listed by title.)" if page.get("title_only") or page.get("unsummarised") else ""
        summary = f" {page['summary']}" if page.get("summary") else ""
        lines.append(
            f"- {_md_link(page.get('title') or 'page', page.get('url'))} — "
            f"{page.get('type') or 'page'}, updated {when}{who}.{summary}{extra}"
        )
    return "\n".join(lines)


def register_block(record, level="pm", opts=None):
    opts = opts or {}
    from core.audience import names_people
    show_names = opts["names"] if "names" in opts else names_people(level)
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
        who = ""
        if show_names and root.get("updated_by"):
            who = f" by {root['updated_by']}"
        count += f" · summary page updated {root.get('updated') or ''}{who}"
    lines = [f"**{_md_link(record.get('name') or 'Register', root.get('url'))}** — {count}", ""]
    show_status = level != "partner"
    show_owner = show_names
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


def append_registers(lines, records, level, since, match, names=None,
                     types=None, elevate=None):
    """Print the registers whose scope matches. No heading when none do."""
    from core.audience import names_people
    if names is None:
        names = names_people(level)
    chosen = [record for record in (records or []) if match(record.get("scope") or {})]
    if types:
        allowed = set(types)
        chosen = [record for record in chosen if record.get("type") in allowed]
    if elevate:
        rank = {kind: index for index, kind in enumerate(elevate)}
        chosen = sorted(chosen, key=lambda record: rank.get(record.get("type"), 50))
    if not chosen:
        return
    lines.append("### Decisions, risks and ADRs")
    lines.append("")
    for record in chosen:
        if level == "partner" and not record.get("partner_visible"):
            continue
        lines.append(register_block(record, level, {"since": since, "names": names}))
        lines.append("")


def _register_records(rows):
    for _ws, row in rows:
        if row.get("registers"):
            return row["registers"]
    return []


def sources_appendix(groups, rows, names=True):
    by_ws = {ws["abbrev"]: row for ws, row in rows}
    lines = ["## Sources", ""]
    if names:
        header = "| Epic | Item | Type | Status | Assignee | Updated |"
        rule = "|------|------|------|--------|----------|---------|"
    else:
        header = "| Epic | Item | Type | Status | Updated |"
        rule = "|------|------|------|--------|---------|"
    for product, streams in groups:
        for ws in streams:
            row = by_ws.get(ws["abbrev"]) or {}
            lines.append(f"### {ws['name']} ({ws['abbrev']})")
            lines.append("")
            lines.append(header)
            lines.append(rule)
            for epic in row.get("epics") or []:
                label = epic.get("summary") or "Not under an Epic"
                if epic.get("key"):
                    label = f"{epic['key']} {label}"
                for item in epic.get("items") or []:
                    title = (item.get("summary") or item.get("title") or "").replace("|", "\\|")
                    link = _md_link(item.get("key") or title, item.get("url"))
                    status = item.get("status") or ""
                    updated = str(item.get("updated") or "")[:10]
                    kind = item.get("issuetype") or ""
                    if names:
                        lines.append(
                            f"| {label} | {link} {title} | {kind} | "
                            f"{status} | {item.get('assignee') or ''} | {updated} |"
                        )
                    else:
                        lines.append(
                            f"| {label} | {link} {title} | {kind} | {status} | {updated} |"
                        )
            for item in row.get("items") or []:
                if item.get("source") != "SharePoint":
                    continue
                title = (item.get("title") or "file").replace("|", "\\|")
                link = _md_link(title, item.get("url"))
                updated = str(item.get("updated") or "")[:10]
                if names:
                    lines.append(f"| — | {link} | file |  |  | {updated} |")
                else:
                    lines.append(f"| — | {link} | file |  | {updated} |")
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


def _docs_under(pages, heading, names=True):
    block = docs_block(pages, names=names)
    if not block:
        return ""
    return block.replace("#### Documentation changed", heading, 1)


def _profile_for(who):
    from core import report_profiles
    if who in report_profiles.PROFILES:
        return report_profiles.get(who)
    return report_profiles.get("pm")


def _generated_body(cfg, body, roles, levels):
    """Profile sections only. An unexpected reply is kept so a link is not lost."""
    if not body:
        return ""
    if not roles:
        return ""
    from core import prompts
    names = [prompts.heading(cfg, "report.section", role) for role in roles]
    pulled = extract_sections(body, names)
    if not any((pulled.get(name) or "").strip() for name in names):
        return demote(body, levels)
    chunks = []
    quiet = {"No update this week.", "No update in this window.", "Nothing this period."}
    for name in names:
        chunk = (pulled.get(name) or "").strip()
        if not chunk or chunk in quiet:
            continue
        chunks.append(f"### {name}\n\n{chunk}")
    return demote("\n\n".join(chunks), levels)


def _append_docs(lines, pages, profile, names, heading):
    from core import report_profiles
    chosen = report_profiles.select_pages(pages, profile)
    block = docs_block(chosen, names=names)
    if not block:
        return
    if heading:
        block = block.replace("#### Documentation changed", heading, 1)
    lines.append(block)
    lines.append("")


def render_pm(cfg, groups, rows, sections, window, scope_note, who="pm",
              team_pages=None, sources="compact", dependencies=None):
    today = dt.date.today().isoformat()
    from core import report_profiles
    profile = _profile_for(who)
    name = report_profiles.display_name(cfg, profile["id"] if who in report_profiles.PROFILES else who)
    if who not in report_profiles.PROFILES:
        from core import audience
        name = audience.display_name(cfg, who)
    names = report_profiles.names_people(profile["id"])
    title = "# Weekly State-of-Product Report"
    if profile["id"] != "pm":
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
    attention = needs_attention(groups or [], rows, profile, dependencies)
    lines.append("## Needs attention")
    lines.append("")
    if attention:
        lines.extend(attention)
    else:
        lines.append("_Nothing in this window needs a decision from this report._")
    lines.append("")
    if show_products and groups:
        lines.append("## At a glance")
        lines.append("")
        lines.append(at_a_glance(groups, rows))
        lines.append("")
        if profile.get("documents"):
            _append_docs(lines, team_pages, profile, names, "### Team pages changed")
        append_registers(
            lines, records, profile["privacy"], since, lambda scope: not scope,
            names=names, types=profile.get("registers"))
    elif profile.get("documents"):
        _append_docs(lines, team_pages, profile, names, "## Team pages changed")
    body_by = {ws["abbrev"]: body for ws, body in sections}
    row_by = {ws["abbrev"]: row for ws, row in rows}
    roles = report_profiles.sections(profile["id"])
    for product, streams in groups or [({}, [ws for ws, _row in rows])]:
        product_docs = [it for ws in streams
                        for it in (row_by.get(ws["abbrev"]) or {}).get("items") or []
                        if it.get("product_only")]
        if show_products and product:
            lines.append(f"## {product.get('name')} ({product.get('abbrev')})")
            lines.append("")
            if profile.get("goal"):
                goal = checklist.product_goal(product)
                if goal:
                    lines.append(f"Product Goal: {goal}")
                    lines.append("")
            if profile.get("increment"):
                lines.extend(_increment_lines(cfg, product))
            if profile.get("documents") and not profile.get("docs_before_epics"):
                _append_docs(lines, product_docs, profile, names, "### Product pages changed")
            abbrev = product.get("abbrev")
            if not profile.get("docs_before_epics"):
                append_registers(
                    lines, records, profile["privacy"], since,
                    lambda scope, abbrev=abbrev: scope.get("product") == abbrev,
                    names=names, types=profile.get("registers"))
        for ws in streams:
            heading = "###" if show_products and product else "##"
            lines.append(f"{heading} {ws['name']} ({ws['abbrev']})")
            lines.append("")
            row = row_by.get(ws["abbrev"]) or {}
            loose = [it for it in row.get("items") or []
                     if it.get("source") in ("Confluence", "SharePoint") and not it.get("epic")
                     and not (show_products and product and it.get("product_only"))]
            doc_heading = "#### Documentation changed" if heading == "###" else "### Documentation changed"
            if profile.get("documents") and profile.get("docs_before_epics"):
                _append_docs(lines, loose, profile, names, doc_heading)
            body = _generated_body(
                cfg, body_by.get(ws["abbrev"]) or "", roles,
                1 if heading == "###" else 0)
            if body.strip():
                lines.append(body)
                lines.append("")
            epics = row.get("epics") or []
            if profile.get("epics") and epics:
                lines.append("#### Epics" if heading == "###" else "### Epics")
                lines.append("")
                for epic in epics:
                    if not epic.get("key") and not epic.get("items"):
                        continue
                    lines.append(epic_block(epic, names=names))
                    lines.append("")
            if profile.get("documents") and not profile.get("docs_before_epics"):
                _append_docs(lines, loose, profile, names, doc_heading)
            abbrev = ws["abbrev"]
            append_registers(
                lines, records, profile["privacy"], since,
                lambda scope, abbrev=abbrev: scope.get("workstream") == abbrev,
                names=names, types=profile.get("registers"),
                elevate=profile.get("elevate"))
        if show_products and product and profile.get("docs_before_epics"):
            _append_docs(lines, product_docs, profile, names, "### Product pages changed")
            abbrev = product.get("abbrev")
            append_registers(
                lines, records, profile["privacy"], since,
                lambda scope, abbrev=abbrev: scope.get("product") == abbrev,
                names=names, types=profile.get("registers"),
                elevate=profile.get("elevate"))
    if sources == "full":
        lines.append(sources_appendix(groups, rows, names=names))
        lines.append("")
    else:
        lines.append("## Sources")
        lines.append("")
        lines.append(
            "Citations in the sections above point at the Epic, item, or page. "
            "Full source tables: `pm report --sources full`."
        )
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
        goal = checklist.product_goal(product)
        if goal:
            lines.append(f"Product Goal: {goal}")
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


def _partner_input(rows, product_abbrev=None):
    """Partner-visible decisions whose fields say the partner needs to act."""
    lines = []
    seen = set()
    for record in _register_records(rows):
        if record.get("type") != "decision" or not record.get("partner_visible"):
            continue
        scope = record.get("scope") or {}
        if product_abbrev and scope.get("product") and scope.get("product") != product_abbrev:
            continue
        for entry in record.get("entries") or []:
            if not _marked_for(entry, "partner"):
                continue
            title = entry.get("title") or "decision"
            if title in seen:
                continue
            seen.add(title)
            lines.append(f"- {title}")
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
        show_percent = bool(opts.get("show_backlog_percent"))
        if show_percent:
            lines.append("| Feature | Status | Items complete | Backlog items complete |")
            lines.append("|---------|--------|---------------:|-----------------------:|")
        else:
            lines.append("| Feature | Status | Items complete |")
            lines.append("|---------|--------|---------------:|")
        for ws in streams:
            for epic in (by_ws.get(ws["abbrev"]) or {}).get("epics") or []:
                if not epic.get("key"):
                    continue
                if not audience.partner_visible_epic(epic, ws, opts):
                    continue
                total = epic.get("children_total") or 0
                done = epic.get("children_done") or 0
                phrase = {"new": "Planned", "done": "Delivered"}.get(
                    (epic.get("status_category") or "").lower(), "In progress")
                items = f"{done} of {total}" if total else "0 of 0"
                feature = epic.get("summary") or epic["key"]
                if opts.get("include_jira_links"):
                    feature = _md_link(feature, epic.get("url"))
                if show_percent:
                    pct = f"{int(100 * done / total)}%" if total else "0%"
                    lines.append(f"| {feature} | {phrase} | {items} | {pct} |")
                else:
                    lines.append(f"| {feature} | {phrase} | {items} |")
        needed = _partner_input(rows, product.get("abbrev"))
        if needed:
            lines.append("")
            lines.append("Input needed")
            lines.append("")
            lines.extend(needed)
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
