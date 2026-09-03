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
from core import model, paths, sources, state, workstreams, writes
from core import products as product_core


DEBRIEF_PROMPT = """\
Extract decisions and actions from these meeting notes.

Return a JSON object with exactly two keys:
- "decisions": array of {"text": string, "owner": string or ""}
- "actions": array of {"title": string, "owner": string or "",
  "issuetype": "Story" or "Task", "workstream": abbrev or ""}

Use ONLY workstream abbrevs from the list. Do not invent dates.
Extract decisions and actions. Do not write any text outside the JSON object.
"""


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


def _needs(issues):
    rows = []
    for issue in issues:
        kind = today_cmd.classify_need(issue, untouched_days=3)
        if not kind:
            continue
        rows.append((kind, issue))
    rank = {"overdue": 0, "blocked": 1, "unassigned": 2, "untouched": 3}
    rows.sort(key=lambda r: (rank.get(r[0], 9), r[1].get("key") or ""))
    return rows[:3]


def _risks(cfg, ws):
    cql = workstreams.confluence_cql(ws)
    if not cql:
        return []
    # Narrow to risk-labelled pages when the workstream names that label.
    labels = [str(l).lower() for l in (ws.get("confluence_labels") or [])]
    items, _idx = sources.fetch_confluence(cfg["confluence"], cql, ws["abbrev"], 1)
    if "risk" in labels:
        return [i for i in items if "risk" in (i.get("title") or "").lower()
                or "risk" in (i.get("detail") or "").lower()
                or "risk" in (i.get("meta") or "").lower()] or items[:2]
    return items[:2]


def gather(cfg, audience):
    streams = cfg.get("_workstreams") or []
    prev = state.load_state(_state_path(cfg, audience))
    last = prev.get("_last")
    snapshot = {}
    sections = []
    for product, group in product_core.group_workstreams(cfg, streams):
        product_issues = []
        risks = []
        for ws in group:
            jql = workstreams.scope_jql(cfg, ws, "lint")
            issues = (sources.fetch_jira_detailed(cfg["jira"], jql)
                      if jql else [])
            for issue in issues:
                product_issues.append(today_cmd._tag_issue(issue, ws, product))
            risks.extend(_risks(cfg, ws))
        items = _as_items(product_issues)
        key = product.get("abbrev") or "UNASSIGNED"
        prev_snap = prev.get(key) or {}
        first = key not in prev
        new, changed, dropped = state.compute_changes(prev_snap, items)
        snapshot[key] = state.snapshot_items(items)
        sections.append({
            "product": product,
            "issues": product_issues,
            "needs": _needs(product_issues),
            "change": state.build_change_block(new, changed, dropped, first),
            "first": first,
            "risks": risks[:3],
            "new": len(new),
            "changed": len(changed),
            "dropped": len(dropped),
        })
    snapshot["_last"] = dt.date.today().isoformat()
    snapshot["_audience"] = audience
    return sections, snapshot, last


def render_prep(audience, sections, last):
    today = dt.date.today()
    since = f"since {last}" if last else "first time with this audience"
    lines = [
        f"# Brief — {audience}",
        f"_{today.strftime(f'%A {today.day} %B')} · {since}_",
        "",
    ]
    for section in sections:
        product = section["product"]
        lines.append(f"## {product.get('name')} ({product.get('abbrev')})")
        lines.append("")
        lines.append("### What changed")
        lines.append("")
        lines.append(section["change"])
        lines.append("")
        lines.append("### Decisions needed")
        lines.append("")
        if not section["needs"]:
            lines.append("_Nothing waiting on this room._")
        for kind, issue in section["needs"]:
            lines.append(
                f"- {issue['key']}: {issue.get('summary')} "
                f"({kind} — {today_cmd.describe_action(kind, issue)})")
        lines.append("")
        lines.append("### Risks")
        lines.append("")
        if not section["risks"]:
            lines.append("_No recent risk pages._")
        for risk in section["risks"]:
            lines.append(f"- {risk.get('title')} "
                         f"{('— ' + risk['url']) if risk.get('url') else ''}")
        lines.append("")
    return "\n".join(lines)


def run_prep(cfg, args):
    audience = getattr(args, "for_audience", None) or getattr(args, "for", None)
    if not audience:
        sys.exit("Which audience? e.g.  pm brief --for \"Monthly portfolio review\"")
    print(f"Preparing the brief for {audience} ...")
    sections, snapshot, last = gather(cfg, audience)
    text = render_prep(audience, sections, last)
    path = f"brief_{_slug(audience)}_{dt.date.today().isoformat()}.md"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    state.save_state(_state_path(cfg, audience), snapshot)
    print(text)
    print(f"\nDone. Brief written to: {path}")
    if getattr(args, "publish", False):
        from commands import publish as pub
        pub.publish_file(cfg, args, path, title=f"{audience} — {dt.date.today().isoformat()}")
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
        "issuetype": {"name": item.get("issuetype") or "Task"},
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
        cfg["model"], DEBRIEF_PROMPT,
        f"{_catalogue(cfg)}\n\nNotes:\n{text}\n\nReturn the JSON object now.")
    extracted = _parse_debrief(raw)
    out = f"debrief_{_slug(audience)}_{dt.date.today().isoformat()}.md"
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
