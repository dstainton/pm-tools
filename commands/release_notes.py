"""`pm release-notes` — done work since a date or in a fixVersion.

Read-only. The issue list comes from Jira. The model may draft prose from
that list when it is up; it does not choose which issues are included.
When the model is down, the command prints the bullets and says so.

  pm release-notes --since 2026-08-01
  pm release-notes --version 2026.9
"""

import datetime as dt
import sys

from core import comments, filters, model, output, prompts, queries, sources, workstreams
from core import products as product_core


def _since(value):
    if not value:
        return None
    try:
        dt.date.fromisoformat(str(value))
    except ValueError:
        sys.exit("--since needs a date, e.g. 2026-08-01.")
    return str(value)


def _window(since, version):
    parts = []
    if since:
        parts.append(queries.render(None, "release_notes.since", since=since))
    if version:
        parts.append(queries.render(None, "release_notes.version", version=version))
    return " AND ".join(parts)


def _row(product, ws, issue):
    return {
        "product_name": product.get("name") or "Unassigned",
        "product_abbrev": product.get("abbrev") or "UNASSIGNED",
        "workstream_name": ws.get("name") or "Unclaimed",
        "workstream_abbrev": ws.get("abbrev") or "—",
        "key": issue.get("key"),
        "summary": issue.get("summary") or "",
        "url": issue.get("url") or "",
        "updated": issue.get("updated"),
        "comments": [],
        "epic": issue.get("epic") or "",
        "labels": list(issue.get("labels") or []),
    }


def collect(cfg, since, version):
    """Done issues in the window, grouped by the workstream that claims them.

    Issues no selected workstream claims land under Unassigned.
    """
    window = _window(since, version)
    overrides = {"status": "done", "sprint": "any", "extra_jql": window}
    rows = []
    claimed = set()
    streams = cfg.get("_workstreams") or []
    for product, group in product_core.group_workstreams(cfg, streams):
        for ws in group:
            jql = workstreams.scope_jql(cfg, ws, "lint", overrides=overrides)
            issues = (sources.fetch_jira_detailed(cfg["jira"], jql)
                      if jql else [])
            for issue in issues:
                claimed.add(issue.get("key"))
                rows.append(_row(product, ws, issue))

    projects = []
    for ws in streams:
        project = workstreams.project_of(cfg, ws)
        if project and project not in projects:
            projects.append(project)
    for project in projects:
        jql = queries.render(cfg, "release_notes.done", project=project, window=window)
        for issue in sources.fetch_jira_detailed(cfg["jira"], jql):
            if issue.get("key") in claimed:
                continue
            rows.append(_row(
                {"name": "Unassigned", "abbrev": "UNASSIGNED"},
                {"name": "Unclaimed", "abbrev": "—"},
                issue))
    _attach_comments(cfg, rows, since)
    return rows


def _attach_comments(cfg, rows, since):
    """Comments on or after --since. A version with no date keeps the newest few."""
    if not rows:
        return
    cutoff = sources.parse_timestamp(since) if since else None
    groups = {}
    for row in rows:
        groups.setdefault(row.get("workstream_abbrev") or "—", []).append(row)
    jira = cfg.get("jira") or {}
    for group in groups.values():
        comments.attach(cfg, jira, group, cutoff)


def bullet_lines(rows, comment_budget=6000, level="pm"):
    """Markdown bullets grouped by product, then workstream."""
    if not rows:
        return ["_No done issues in that window._", ""]
    limit = 0 if comment_budget is None else int(comment_budget)
    lines = []
    order = []
    by_product = {}
    for row in rows:
        key = row["product_abbrev"]
        if key not in by_product:
            order.append(key)
            by_product[key] = {"name": row["product_name"], "streams": []}
        streams = by_product[key]["streams"]
        found = next((s for s in streams
                      if s["abbrev"] == row["workstream_abbrev"]), None)
        if found is None:
            found = {"abbrev": row["workstream_abbrev"],
                     "name": row["workstream_name"], "issues": []}
            streams.append(found)
        found["issues"].append(row)
    for abbrev in order:
        block = by_product[abbrev]
        lines.append(f"## {block['name']} ({abbrev})")
        lines.append("")
        for stream in block["streams"]:
            lines.append(f"### {stream['name']} ({stream['abbrev']})")
            lines.append("")
            used = 0
            omitted = 0
            if level == "leadership":
                by_epic = {}
                for issue in stream["issues"]:
                    by_epic.setdefault(issue.get("epic") or "Not under an Epic", []).append(issue)
                for epic, issues in by_epic.items():
                    lines.append(f"- {epic} — {len(issues)} done this window")
                lines.append("")
                continue
            shown = stream["issues"]
            if level == "partner":
                shown = [issue for issue in shown
                         if "partner-visible" in [str(l).lower() for l in issue.get("labels") or []]
                         or "partner-visible" in str(issue.get("epic") or "").lower()]
            for issue in shown:
                if issue.get("epic"):
                    lines.append(f"**{issue['epic']}**")
                lines.append(f"- {issue['key']}: {issue['summary']}")
                wrote = False
                for line in issue.get("comments") or []:
                    if used + len(line) > limit:
                        break
                    lines.append(f"  - {line}")
                    used += len(line)
                    wrote = True
                if (issue.get("comments") or []) and not wrote:
                    omitted += 1
            if omitted:
                lines.append(
                    f"(+{omitted} commented issues omitted "
                    f"to keep the prompt short.)")
            lines.append("")
    return lines


def _skipped(text):
    if not text:
        return True
    return text.startswith("_Could not reach") or text.startswith("_The model")


def draft(cfg, bullets):
    """Model prose, or None when the model was skipped."""
    raw = model.call_model(cfg["model"], prompts.get(cfg, "release_notes.prose"),
                           "\n".join(bullets))
    if _skipped(raw):
        return None
    return raw.strip()


def render(since, version, rows, prose, comment_budget=6000, level="pm"):
    bits = []
    if since:
        bits.append(f"since {since}")
    if version:
        bits.append(f"fixVersion {version}")
    window = ", ".join(bits) or "the selected window"
    lines = [
        "# Release notes",
        f"_{window}. The model does not choose which issues are included._",
        "",
    ]
    bullets = bullet_lines(rows, comment_budget, level)
    if prose:
        lines.append(prose)
        lines.append("")
        lines.append("## Issues")
        lines.append("")
    else:
        lines.append("The model was skipped.")
        lines.append("")
    lines.extend(bullets)
    return "\n".join(lines).rstrip() + "\n"


def run(cfg, args):
    since = _since(getattr(args, "since", None))
    version = getattr(args, "version", None) or None
    if not since and not version:
        sys.exit("Pass --since YYYY-MM-DD, --version NAME, or both.\n"
                 "  pm release-notes --since 2026-08-01\n"
                 "  pm release-notes --version 2026.9")
    print("Gathering done issues ...")
    rows = collect(cfg, since, version)
    budget = comments.settings(cfg)["section_chars"]
    from core import audience
    level = audience.level(cfg, args)
    bullets = bullet_lines(rows, budget, level)
    prose = draft(cfg, bullets) if rows else None
    text = render(since, version, rows, prose, budget, level)
    path = output.place(
        cfg, f"release_notes_{dt.date.today().isoformat()}.md",
        getattr(args, "out", None))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text)
    print(f"Done. Release notes written to: {path}")
