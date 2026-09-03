"""`pm refine` — the refinement queue, with drafts instead of blank fields.

Lint finds the gaps. This command drafts a title, acceptance criteria and
an estimate for each one, writes an editable worksheet, and `--apply`
sends back only what you left in the file.

`pm review` is kept as a deprecated alias for one release.
"""

import datetime as dt
import os
import re
import statistics
import sys

from commands import lint, ready, review
from core import decisions, model, sources, workstreams, writes


TITLE_DRAFT_PROMPT = """\
Draft a clearer title for each Jira item. Keep the meaning. Do not invent scope.

Return a JSON array. Each object has exactly two keys:
- "key": the issue key, copied exactly
- "title": the rewritten title

If you would not change a title, omit that item.

Draft a clearer title. Do not write any text outside the JSON array.
"""

CRITERIA_DRAFT_PROMPT = """\
Draft testable acceptance criteria for each story that is missing them.

Return a JSON array. Each object has exactly two keys:
- "key": the issue key, copied exactly
- "criteria": 2 to 4 short Given/When/Then lines, separated by newlines

Draft acceptance criteria. Do not write any text outside the JSON array.
"""


def _median_estimate(closed_points):
    values = [p for p in closed_points if isinstance(p, (int, float)) and p > 0]
    if not values:
        return None
    return int(round(statistics.median(values)))


def _closed_points(cfg, ws):
    """Story-point estimates on closed work in this workstream."""
    options = {"status": "done", "types": ["Story"]}
    jql = workstreams.scope_jql(cfg, ws, "lint", overrides=options)
    if not jql:
        return []
    issues = sources.fetch_jira_detailed(cfg["jira"], jql)
    return [i.get("story_points") for i in issues]


def _gaps(cfg, ws, store, show_all=False):
    jql = workstreams.scope_jql(cfg, ws, "ready")
    if not jql:
        return [], []
    issues = sources.fetch_jira_detailed(cfg["jira"], jql)
    inherited = workstreams.uses_component_scope(cfg, ws)
    lint_cfg = cfg.get("lint", {})
    blocking = set((cfg.get("ready") or {}).get(
        "blocking_criteria", list(ready.CRITERION_RULES.keys())))
    out, hidden = [], []
    for issue in issues:
        verdict = ready.evaluate_issue(issue, lint_cfg, blocking, None, inherited)
        if verdict["ready"]:
            continue
        findings = lint.check_issue(issue, lint_cfg, inherited)
        if not show_all:
            visible = [f for f in findings if not decisions.is_hidden(store, f)]
            hidden.extend(f for f in findings if decisions.is_hidden(store, f))
            findings = visible
        if not findings and verdict["ready"]:
            continue
        if not findings:
            continue
        out.append((issue, findings, verdict))
    return out, hidden


def _chunks(items, size):
    size = max(1, int(size or 8))
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _drafts(cfg, issues):
    batch = cfg.get("review", {}).get("batch_size", 8)
    titles, criteria = {}, {}
    need_titles = [i for i in issues
                   if any(f.get("rule") == "vague-title"
                          for f in i.get("_findings") or [])]
    need_ac = [i for i in issues
               if any(f.get("rule") == "missing-acceptance-criteria"
                      for f in i.get("_findings") or [])]
    for group in _chunks(need_titles, batch):
        data, _err = model.call_model_json(
            cfg["model"], TITLE_DRAFT_PROMPT,
            "\n".join(f"{i['key']}: {i['summary']}" for i in group)
            + "\n\nReturn the JSON array now.")
        for obj in data or []:
            if obj.get("key") and obj.get("title"):
                titles[obj["key"]] = obj["title"].strip()
    for group in _chunks(need_ac, batch):
        data, _err = model.call_model_json(
            cfg["model"], CRITERIA_DRAFT_PROMPT,
            "\n".join(f"{i['key']}: {i['summary']}" for i in group)
            + "\n\nReturn the JSON array now.")
        for obj in data or []:
            if obj.get("key") and obj.get("criteria"):
                criteria[obj["key"]] = obj["criteria"].strip()
    return titles, criteria


def _worksheet_path(ws):
    return f"refine_{ws['abbrev']}_{dt.date.today().isoformat()}.md"


def build_worksheet(cfg, ws, rows, titles, criteria, estimate):
    lines = [
        f"# Refine {ws['abbrev']} {dt.date.today().isoformat()}",
        "",
        "Edit or delete any field you disagree with, then:",
        f"  pm refine --apply -w {ws['abbrev']}",
        "",
        "A deleted field is not written. Leave a field as-is to send the draft.",
        "",
    ]
    for issue, findings, _verdict in rows:
        rules = {f["rule"] for f in findings}
        lines.append(f"## {issue['key']}")
        lines.append(f"# was: {issue['summary']}")
        if "vague-title" in rules:
            lines.append(f"title: {titles.get(issue['key'], issue['summary'])}")
        if "missing-acceptance-criteria" in rules:
            drafted = criteria.get(issue["key"], "")
            lines.append("criteria: |")
            if drafted:
                for part in drafted.splitlines():
                    lines.append(f"  {part}")
            else:
                lines.append("  Given ...")
                lines.append("  When ...")
                lines.append("  Then ...")
        if "no-estimate" in rules:
            hint = f"{estimate}" if estimate is not None else ""
            lines.append(f"estimate: {hint}".rstrip())
        lines.append("")
    return "\n".join(lines)


SECTION_RE = re.compile(r"^##\s+(\S+)\s*$")
FIELD_RE = re.compile(r"^(title|criteria|estimate):\s*(.*)$")


def parse_worksheet(text):
    """Return {key: {title, criteria, estimate}} from an edited worksheet."""
    current = None
    fields = {}
    in_criteria = False
    criteria_lines = []
    for raw in text.splitlines():
        match = SECTION_RE.match(raw)
        if match:
            if current and in_criteria:
                fields[current]["criteria"] = "\n".join(criteria_lines).strip()
            current = match.group(1)
            fields[current] = {}
            in_criteria = False
            criteria_lines = []
            continue
        if current is None or raw.startswith("#"):
            continue
        if in_criteria:
            if raw.startswith("  "):
                criteria_lines.append(raw[2:])
                continue
            fields[current]["criteria"] = "\n".join(criteria_lines).strip()
            in_criteria = False
        field = FIELD_RE.match(raw)
        if not field:
            continue
        name, value = field.group(1), field.group(2)
        if name == "criteria":
            in_criteria = True
            criteria_lines = [value.lstrip("| ").rstrip()] if value.strip() \
                and value.strip() != "|" else []
        elif name == "estimate":
            value = value.strip()
            if value:
                try:
                    fields[current]["estimate"] = float(value) if "." in value \
                        else int(value)
                except ValueError:
                    pass
        else:
            if value.strip():
                fields[current]["title"] = value.strip()
    if current and in_criteria:
        fields[current]["criteria"] = "\n".join(criteria_lines).strip()
    return {k: v for k, v in fields.items() if v}


def _apply_one(cfg, args, key, changes, issue):
    fields = {}
    jira = cfg["jira"]
    if changes.get("title") and changes["title"] != issue.get("summary"):
        fields["summary"] = changes["title"]
    if changes.get("criteria"):
        ac_field = jira.get("acceptance_criteria_field") or ""
        body = writes.adf_doc(changes["criteria"])
        if ac_field:
            fields[ac_field] = body
        else:
            existing = issue.get("description") or ""
            merged = (existing.rstrip() + "\n\nAcceptance criteria:\n"
                      + changes["criteria"]).strip()
            fields["description"] = writes.adf_doc(merged)
    if changes.get("estimate") is not None:
        sp = jira.get("story_points_field")
        if sp:
            fields[sp] = changes["estimate"]
    if not fields:
        return None
    return writes.action_update_issue(
        key, fields, kind="refine", summary=issue.get("summary") or key,
        description="write the kept drafts")


def run(cfg, args):
    if getattr(args, "command", "") == "review":
        print("Note: `pm review` is a deprecated alias of `pm refine` "
              "and will be removed in a later release.\n")
        if not getattr(args, "apply", False):
            return review.run(cfg, args)

    store = decisions.load(cfg)
    apply = getattr(args, "apply", False)
    selected = cfg.get("_workstreams") or []
    if apply:
        for ws in selected:
            path = _worksheet_path(ws)
            if not os.path.exists(path):
                sys.exit(f"No worksheet at {path}. Run `pm refine -w "
                         f"{ws['abbrev']}` first, edit the file, then --apply.")
            with open(path, encoding="utf-8") as fh:
                planned = parse_worksheet(fh.read())
            jql = workstreams.scope_jql(cfg, ws, "ready")
            issues = {i["key"]: i for i in
                      (sources.fetch_jira_detailed(cfg["jira"], jql) if jql else [])}
            actions = []
            for key, changes in planned.items():
                issue = issues.get(key) or {"key": key, "summary": key,
                                            "description": ""}
                action = _apply_one(cfg, args, key, changes, issue)
                if action:
                    actions.append(action)
            if not actions:
                print(f"{ws['abbrev']}: nothing left to write.")
                continue
            print(f"{ws['abbrev']}: {len(actions)} update(s)\n")
            for action in actions:
                writes.preview(action)
                print("")
            if not writes.should_write(args):
                return
            for action in actions:
                try:
                    writes.execute(cfg, action)
                    writes.log_write(cfg, action, result={})
                except Exception as err:           # noqa: BLE001
                    writes.log_write(cfg, action, error=err)
                    sys.exit(f"Jira write failed on {action['key']}: {err}")
            print("Sent.")
        return

    for ws in selected:
        rows, hidden = _gaps(cfg, ws, store)
        if hidden:
            print(f"  {len(hidden)} finding(s) hidden by earlier decisions.")
        if not rows:
            print(f"{ws['abbrev']}: nothing failing the ready agreement.")
            continue
        issues = []
        for issue, findings, verdict in rows:
            issue = dict(issue)
            issue["_findings"] = findings
            issue["_verdict"] = verdict
            issues.append(issue)
        rows = [(i, i["_findings"], i["_verdict"]) for i in issues]
        print(f"{len(rows)} ticket(s) fail the ready agreement in {ws['abbrev']}.")
        titles, criteria = _drafts(cfg, issues)
        estimate = _median_estimate(_closed_points(cfg, ws))
        text = build_worksheet(cfg, ws, rows, titles, criteria, estimate)
        path = _worksheet_path(ws)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        for issue, findings, _v in rows:
            rules = ", ".join(sorted({f["rule"] for f in findings}))
            extra = ""
            if issue["key"] in titles:
                extra = f'  → "{titles[issue["key"]]}"'
            print(f"  {issue['key']:<8} {rules}{extra}")
        print(f"Drafts in {path}")
        print(f"Edit the file, then:  pm refine --apply -w {ws['abbrev']}")
