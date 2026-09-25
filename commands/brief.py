"""`pm brief` — meeting prep for one audience, and the debrief afterwards.

Prep is deterministic: per product, what changed since you last met *that*
audience, the decisions you need from them, and the risks worth their
attention. Debrief asks the local model to turn scribbles into a decision
list and an action list; `--apply` creates the action tickets after a preview.
"""

import datetime as dt
import json
import os
import re
import sys

from commands import today as today_cmd
from core import (
    checklist, comments, conventions, filters, model, output, paths, prompts, queries, registers, sources, state,
    workstreams, writes,
)
from core import products as product_core


def _slug(name):
    text = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return text or "audience"


def _state_path(cfg, audience):
    return os.path.join(paths.briefs_dir(cfg), f"{_slug(audience)}.json")


def _as_items(issues):
    items = []
    for issue in issues:
        items.append({
            "uid": issue["key"],
            "title": issue.get("summary") or issue["key"],
            "watch": issue.get("status") or "",
            "ref": issue["key"],
            "url": issue.get("url") or "",
        })
    return items


def _needs(issues, cfg):
    rows = []
    for issue in issues:
        kind = today_cmd.classify_need(issue, untouched_days=3, cfg=cfg)
        if not kind:
            continue
        rows.append((kind, issue))
    rank = {"overdue": 0, "blocked": 1, "unassigned": 2, "untouched": 3}
    rows.sort(key=lambda r: (rank.get(r[0], 9), r[1].get("key") or ""))
    return rows[:3]


def _risk_cql(ws, cfg=None):
    """Pages the workstream labelled as risks.

    The label is the author's statement. A title that happens to contain
    the word is not, and a title that does not is still a risk page.
    """
    labels = [str(label).strip() for label in (ws.get("confluence_labels") or [])]
    wanted = str(conventions.get(cfg, "risk_label") or "risk").lower()
    risk = next((label for label in labels if label.lower() == wanted), None)
    from core import confluence_tree
    located = confluence_tree.locate_workstream(cfg, ws)
    space = located.get("space") or ws.get("confluence_space")
    if risk and space and not located.get("missing"):
        cql = queries.render(cfg, "brief.risk_pages", space=space, label=risk)
        if located.get("ancestor_id"):
            cql += " AND " + queries.render(
                cfg, "confluence.ancestor", page_id=located["ancestor_id"])
        return cql
    if located.get("missing"):
        return None
    return workstreams.confluence_cql(ws, cfg)


def _risks(cfg, ws, since=None):
    cql = _risk_cql(ws, cfg)
    if not cql:
        return []
    items, _idx = sources.fetch_confluence(
        cfg["confluence"], cql, ws["abbrev"], 1, since=since)
    return items[:3]


def gather(cfg, audience, window=None):
    streams = cfg.get("_workstreams") or []
    prev = state.load_state(_state_path(cfg, audience))
    last = prev.get("_last")
    snapshot = {}
    sections = []
    for product, group in product_core.group_workstreams(cfg, streams):
        product_issues = []
        product_pages = []
        for ws in group:
            jql = workstreams.scope_jql(cfg, ws, "lint")
            issues = (sources.fetch_jira_detailed(cfg["jira"], jql)
                      if jql else [])
            comments.attach(
                cfg, cfg.get("jira") or {}, issues,
                comments.audience_cutoff(last, comments.settings(cfg)))
            for issue in issues:
                issue["workstream"] = ws["abbrev"]
                product_issues.append(today_cmd._tag_issue(issue, ws, product))
            page_since = window["start"] if window and window.get("start") else None
            from core import pages as page_core
            page_window = {"start": page_since} if page_since else (window or {})
            product_pages.extend(page_core.gather(cfg, ws, window=page_window))
        items = _as_items(product_issues)
        from core import epics as epic_core
        epic_rows = []
        for ws in group:
            ws_issues = [issue for issue in product_issues if issue.get("workstream") == ws["abbrev"]]
            report_items = []
            for issue in ws_issues:
                report_items.append({
                    "source": "Jira", "key": issue["key"], "uid": issue["key"],
                    "summary": issue.get("summary") or "",
                    "issuetype": issue.get("issuetype") or "",
                    "status": issue.get("status") or "",
                    "status_category": issue.get("status_category") or "",
                    "parent": issue.get("epic"),
                    "labels": list(issue.get("labels") or []),
                    "due": issue.get("due_date") or "",
                    "updated": str(issue.get("updated") or "")[:10],
                    "url": issue.get("url") or "",
                })
            epic_rows.extend(epic_core.build(cfg, ws, report_items, window, ([], [], [])))
        key = product.get("abbrev") or "UNASSIGNED"
        prev_snap = prev.get(key) or {}
        first = key not in prev
        new, changed, dropped = state.compute_changes(prev_snap, items)
        snapshot[key] = state.snapshot_items(items)
        sections.append({
            "product": product,
            "issues": product_issues,
            "needs": _needs(product_issues, cfg),
            "change": state.build_change_block(new, changed, dropped, first),
            "first": first,
            "risks": [],
            "pages": product_pages[:5],
            "epics": epic_rows,
            "registers": [],
            "new": len(new),
            "changed": len(changed),
            "dropped": len(dropped),
        })
    found, _skip = registers.gather(cfg, window or {"start": None}, prev)
    from core import page_summaries
    for section in sections:
        page_summaries.fill(cfg, section.get("pages") or [])
        section["registers"] = found
        if any(record.get("type") == "risk" for record in found):
            section["risks"] = []
        else:
            section["risks"] = [page for page in section.get("pages") or []
                                if (page.get("kind") or "").lower() == "risk"][:3]
    snapshot["_registers"] = registers.saved_memory(cfg, found)
    snapshot["_last"] = dt.date.today().isoformat()
    snapshot["_audience"] = audience
    return sections, snapshot, last


def _leadership_prep(section):
    """Epic table, decisions the room must make, and counts owed per Epic."""
    lines = [
        "| Epic | Status | Progress | Signal | Target |",
        "|------|--------|---------:|--------|--------|",
    ]
    for epic in section.get("epics") or []:
        if not epic.get("key"):
            continue
        signal = epic.get("signal") or ""
        reason = epic.get("signal_reason") or ""
        if signal == "At risk" and reason:
            signal = f"{signal} — {reason}"
        lines.append(
            f"| {epic['key']} {epic.get('summary') or ''} | {epic.get('status') or ''} | "
            f"{epic.get('children_done') or 0} / {epic.get('children_total') or 0} | "
            f"{signal} | {epic.get('due') or '—'} |"
        )
    lines.append("")
    lines.append("### Decisions you need from the room")
    lines.append("")
    decisions = [page for page in section.get("pages") or []
                 if (page.get("kind") or "").lower() == "decision"]
    at_risk = [epic for epic in section.get("epics") or []
               if epic.get("key") and epic.get("signal") == "At risk"]
    if not decisions and not at_risk:
        lines.append("_Nothing waiting on this room._")
    for page in decisions:
        lines.append(f"- {page.get('title') or 'page'}")
    for epic in at_risk:
        lines.append(f"- {epic['key']} {epic.get('summary') or ''} is at risk.")
    lines.append("")
    lines.append("### What you owe the room")
    lines.append("")
    owed = [(kind, issue) for kind, issue in section["needs"] if kind in ("overdue", "blocked")]
    if not owed:
        lines.append("_Nothing you owe this room._")
    by_epic = {}
    for kind, issue in owed:
        by_epic.setdefault(issue.get("epic") or "Not under an Epic", []).append(kind)
    for epic, kinds in by_epic.items():
        overdue = kinds.count("overdue")
        blocked = kinds.count("blocked")
        lines.append(f"- {epic}: {overdue} overdue, {blocked} blocked.")
    lines.append("")
    from core.report_render import SIGNAL_FOOTER
    lines.append(SIGNAL_FOOTER)
    lines.append("")
    return lines


def _partner_prep(cfg, section):
    """Visible Epics and the overdue or blocked items inside them."""
    from core import audience as audience_core
    opts = audience_core.settings(cfg)["partner"]
    lines = []
    visible_keys = set()
    excluded = {str(label).lower() for label in opts.get("exclude_labels") or []}
    for epic in section.get("epics") or []:
        if not epic.get("key"):
            continue
        if not audience_core.partner_visible_epic(epic, {}, opts):
            continue
        lines.append(f"**{epic.get('summary') or epic['key']}**")
        lines.append("")
        visible_keys.add(epic["key"])
        for item in epic.get("items") or []:
            labels = {str(label).lower() for label in item.get("labels") or []}
            if labels & excluded:
                continue
            lines.append(f"- {item.get('summary') or item.get('key')}")
            if item.get("key"):
                visible_keys.add(item["key"])
        lines.append("")
    lines.append("### What you owe the room")
    lines.append("")
    owed = [(kind, issue) for kind, issue in section.get("needs") or []
            if kind in ("overdue", "blocked")
            and (issue.get("key") in visible_keys or issue.get("epic") in visible_keys)]
    if not owed:
        lines.append("_Nothing you owe this room._")
    for kind, issue in owed:
        lines.append(f"- {issue.get('summary') or issue.get('key')} ({kind})")
    lines.append("")
    return lines


def render_prep(audience, sections, last, level="pm", cfg=None):
    today = dt.date.today()
    since = f"since {last}" if last else "first time with this audience"
    lines = [
        f"# Brief — {audience}",
        f"_{today.strftime(f'%A {today.day} %B')} · {since}_",
        "",
    ]
    if level == "partner":
        lines.append("_Prep for a partner meeting — internal, do not forward._")
        lines.append("")
    for section in sections:
        product = section["product"]
        lines.append(f"## {product.get('name')} ({product.get('abbrev')})")
        lines.append("")
        goal = checklist.product_goal(product)
        if goal:
            lines.append(f"Product Goal: {goal}")
            lines.append("")
        if level == "leadership":
            lines.extend(_leadership_prep(section))
            from core import report_render
            if section.get("registers"):
                report_render.append_registers(
                    lines, section["registers"], level, "", lambda scope: True)
            continue
        if level == "partner":
            lines.extend(_partner_prep(cfg, section))
            continue
        lines.append("### What changed")
        lines.append("")
        lines.append(section["change"])
        notes = []
        for issue in section["issues"]:
            for line in issue.get("comments") or []:
                notes.append(f"- {issue['key']} — {line}")
        if notes:
            lines.append("")
            lines.extend(notes)
        lines.append("")
        owed = [(k, i) for k, i in section["needs"]
                if k in ("overdue", "blocked")]
        needed = [(k, i) for k, i in section["needs"]
                  if k not in ("overdue", "blocked")]
        lines.append("### What you owe the room")
        lines.append("")
        if level == "leadership":
            overdue = sum(1 for kind, _issue in section["needs"] if kind == "overdue")
            blocked = sum(1 for kind, _issue in section["needs"] if kind == "blocked")
            lines.append(f"- {overdue} overdue, {blocked} blocked.")
        elif not owed:
            lines.append("_Nothing you owe this room._")
        else:
            for kind, issue in owed:
                if level == "partner":
                    lines.append(f"- {issue.get('summary')} ({kind})")
                else:
                    lines.append(
                        f"- {issue['key']}: {issue.get('summary')} "
                        f"({kind} — {today_cmd.describe_action(kind, issue)})")
        lines.append("")
        lines.append("### What you need from the room")
        lines.append("")
        if not needed:
            lines.append("_Nothing waiting on this room._")
        for kind, issue in needed:
            lines.append(
                f"- {issue['key']}: {issue.get('summary')} "
                f"({kind} — {today_cmd.describe_action(kind, issue)})")
        lines.append("")
        lines.append("### Risks")
        lines.append("")
        from core import render as render_core
        from core import report_render
        risk_regs = [record for record in (section.get("registers") or [])
                     if record.get("type") == "risk"]
        if risk_regs:
            for record in risk_regs:
                lines.append(report_render.register_block(record, level, {}))
                lines.append("")
        elif not section["risks"]:
            lines.append("_No recent risk pages._")
        for risk in section["risks"]:
            title = risk.get("title") or "page"
            link = render_core.markdown_link(title, risk.get("url"))
            sentence = risk.get("summary") or sources.short(risk.get("detail") or "", 200)
            lines.append(f"- {link}" + (f" — {sentence}" if sentence else ""))
        lines.append("")
        docs = section.get("pages") or []
        if level == "pm" and docs:
            lines.append("### Documents changed")
            lines.append("")
            for page in docs[:5]:
                title = page.get("title") or "page"
                link = render_core.markdown_link(title, page.get("url"))
                summary = page.get("summary") or ""
                lines.append(f"- {link}" + (f" — {summary}" if summary else ""))
            lines.append("")
        from core import report_render
        records = [row for row in (section.get("registers") or [])
                   if (row.get("scope") or {}).get("product") in (None, product.get("abbrev"))
                   or not (row.get("scope") or {})]
        if records:
            report_render.append_registers(
                lines, records, level, "",
                lambda scope: True)
    return "\n".join(lines)


def run_prep(cfg, args):
    audience = getattr(args, "for_audience", None) or getattr(args, "for", None)
    if not audience:
        sys.exit("Which audience? e.g.  pm brief --for \"Monthly portfolio review\"")
    from core import audience as audience_core
    previous = state.load_state(_state_path(cfg, audience))
    level = getattr(args, "audience", None) or previous.get("_audience_level") or "pm"
    print(f"Preparing the brief for {audience} ({level}) ...")
    from core import window as window_core
    try:
        window = window_core.resolve(cfg, args, default_start=None, projects=[])
    except window_core.WindowError as exc:
        sys.exit(str(exc))
    sections, snapshot, last = gather(cfg, audience, window)
    text = render_prep(audience, sections, last, level, cfg=cfg)
    snapshot["_audience_level"] = level
    path = output.place(
        cfg, f"brief_{_slug(audience)}_{dt.date.today().isoformat()}.md",
        getattr(args, "out", None))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    state.save_state(_state_path(cfg, audience), snapshot)
    print(text)
    print(f"\nDone. Brief written to: {path}")
    if getattr(args, "publish", False):
        from commands import publish as pub
        pub.publish_file(cfg, args, path, title=f"{audience} — {dt.date.today().isoformat()}",
                         labels=["pm-report", "pm-brief"])
    return path


def _catalogue(cfg):
    streams = cfg.get("workstreams") or []
    return "Workstreams: " + ", ".join(
        f"{w['abbrev']} ({w.get('product') or 'UNASSIGNED'})" for w in streams)


def _parse_debrief(raw):
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        return {"decisions": [], "actions": []}
    try:
        data = json.loads(raw[start:end + 1])
    except ValueError:
        return {"decisions": [], "actions": []}
    if not isinstance(data, dict):
        return {"decisions": [], "actions": []}
    return {
        "decisions": data.get("decisions") or [],
        "actions": data.get("actions") or [],
    }


def render_debrief(audience, notes_name, extracted):
    lines = [
        f"# Debrief — {audience}",
        f"_From {notes_name} on {dt.date.today().isoformat()}_",
        "",
        "## Decisions",
        "",
    ]
    if not extracted["decisions"]:
        lines.append("_None extracted._")
    for item in extracted["decisions"]:
        owner = f" — {item['owner']}" if item.get("owner") else ""
        lines.append(f"- {item.get('text')}{owner}")
    lines.append("")
    lines.append("## Actions")
    lines.append("")
    if not extracted["actions"]:
        lines.append("_None extracted._")
    for item in extracted["actions"]:
        bits = [item.get("title") or ""]
        if item.get("owner"):
            bits.append(item["owner"])
        if item.get("workstream"):
            bits.append(item["workstream"])
        lines.append("- " + " · ".join(bits))
    lines.append("")
    lines.append("Create the action tickets with:  pm brief --debrief "
                 f"{notes_name} --apply")
    return "\n".join(lines)


def _action_ticket(cfg, item):
    ws = None
    abbrev = item.get("workstream") or ""
    if abbrev:
        ws = next((w for w in (cfg.get("workstreams") or [])
                   if w["abbrev"].lower() == str(abbrev).lower()), None)
    project = (workstreams.project_of(cfg, ws) if ws
               else (cfg.get("jira") or {}).get("project"))
    fields = {
        "project": {"key": project},
        "summary": item.get("title") or "Follow-up",
        "issuetype": {"name": item.get("issuetype") or conventions.get(cfg, "action_issuetype")},
        "description": writes.adf_doc(
            f"From debrief. Owner: {item.get('owner') or 'unassigned'}."),
    }
    if ws:
        comps = workstreams.components_of(ws)
        if comps:
            fields["components"] = [{"name": c} for c in comps]
    return writes.action_create_issue(
        fields, kind="debrief-action", summary=fields["summary"])


def run_debrief(cfg, args):
    notes = getattr(args, "debrief", None)
    if not notes or not os.path.exists(notes):
        sys.exit(f"No notes file at {notes!r}.")
    audience = getattr(args, "for_audience", None) or "meeting"
    with open(notes, encoding="utf-8") as fh:
        text = fh.read()
    raw = model.call_model(
        cfg["model"], prompts.get(cfg, "brief.debrief"),
        f"{_catalogue(cfg)}\n\nNotes:\n{text}\n\nReturn the JSON object now.")
    extracted = _parse_debrief(raw)
    out = output.place(
        cfg, f"debrief_{_slug(audience)}_{dt.date.today().isoformat()}.md",
        getattr(args, "out", None))
    body = render_debrief(audience, notes, extracted)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(body)
    print(body)
    print(f"\nDone. Debrief written to: {out}")
    if not getattr(args, "apply", False):
        return
    actions = [_action_ticket(cfg, item) for item in extracted["actions"]
               if item.get("title")]
    if not actions:
        print("Nothing to create.")
        return
    print(f"\n{len(actions)} ticket(s) to create\n")
    for action in actions:
        writes.preview(action)
        print("")
    if not writes.should_write(args):
        return
    for action in actions:
        try:
            result = writes.execute(cfg, action)
            writes.log_write(cfg, action, result=result)
            if result.get("key"):
                print(f"Created {result['key']}.")
        except Exception as err:                   # noqa: BLE001
            writes.log_write(cfg, action, error=err)
            sys.exit(f"Write failed: {err}")


def run(cfg, args):
    if getattr(args, "debrief", None):
        return run_debrief(cfg, args)
    return run_prep(cfg, args)
