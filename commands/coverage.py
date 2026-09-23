"""`pm coverage` — open work no workstream claims, and the reverse.

Membership is the clauses in `core/workstreams.py`. This command lists the
open issues those clauses miss, the open issues two or more workstreams
claim, and Jira components in the team project that no workstream names.

The workstreams used for claims are every workstream in the project, not
only the ones `--workstream` selected. The selection chooses which projects
to inspect. Exit 1 when unclaimed open work exists.
"""

import sys

from core import filters, sources, workstreams


def classify(issues, claims, component_names, named_components):
    """Split open issues and component names. No Jira calls.

    `claims` maps an issue key to the workstream abbrevs that claim it.
    `named_components` are the Component names workstreams list.
    """
    unclaimed = []
    overlap = []
    for issue in issues:
        owners = list(claims.get(issue.get("key")) or [])
        if not owners:
            unclaimed.append(issue)
        elif len(owners) >= 2:
            row = dict(issue)
            row["workstreams"] = owners
            overlap.append(row)
    named = {name.lower() for name in named_components}
    unused = [name for name in component_names if name.lower() not in named]
    return {"unclaimed": unclaimed, "overlap": overlap, "unused": unused}


def _projects(cfg):
    seen = []
    for ws in cfg.get("_workstreams") or []:
        project = workstreams.project_of(cfg, ws)
        if project and project not in seen:
            seen.append(project)
    return seen


def _streams_in(cfg, project):
    return [ws for ws in (cfg.get("workstreams") or [])
            if workstreams.project_of(cfg, ws) == project]


def _claims(cfg, project, streams):
    claims = {}
    for ws in streams:
        jql = workstreams.scope_jql(cfg, ws, "lint")
        if not jql:
            continue
        abbrev = ws.get("abbrev") or "?"
        for key in sources.fetch_jira_keys(cfg["jira"], jql):
            claims.setdefault(key, [])
            if abbrev not in claims[key]:
                claims[key].append(abbrev)
    return claims


def _open_issues(cfg, project):
    jql = (f"project = {filters.quote(project)} "
           f"AND statusCategory != Done")
    return sources.fetch_jira_detailed(cfg["jira"], jql)


def inspect_project(cfg, project):
    streams = _streams_in(cfg, project)
    named = []
    for ws in streams:
        for name in workstreams.components_of(ws):
            if name not in named:
                named.append(name)
    components = sources.fetch_project_components(cfg["jira"], project)
    result = classify(
        _open_issues(cfg, project),
        _claims(cfg, project, streams),
        components,
        named,
    )
    result["project"] = project
    return result


def render(reports):
    lines = []
    for report in reports:
        project = report["project"]
        lines.append(f"Coverage — {project}")
        lines.append("")
        unclaimed = report["unclaimed"]
        lines.append(f"Unclaimed open issues ({len(unclaimed)})")
        if not unclaimed:
            lines.append("  None.")
        for issue in unclaimed:
            lines.append(f"  {issue.get('key'):<8} {issue.get('summary') or ''}")
        lines.append("")
        overlap = report["overlap"]
        lines.append(f"Claimed by more than one workstream ({len(overlap)})")
        if not overlap:
            lines.append("  None.")
        for issue in overlap:
            owners = ", ".join(issue.get("workstreams") or [])
            lines.append(
                f"  {issue.get('key'):<8} {issue.get('summary') or ''}  ({owners})")
        lines.append("")
        unused = report["unused"]
        lines.append(f"Components no workstream names ({len(unused)})")
        if not unused:
            lines.append("  None.")
        for name in unused:
            lines.append(f"  {name}")
        lines.append("")
    if not reports:
        lines.append("No project to inspect.")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def run(cfg, args):
    projects = _projects(cfg)
    reports = []
    for project in projects:
        print(f"Checking coverage in {project} ...")
        reports.append(inspect_project(cfg, project))
    text = render(reports)
    print(text, end="")
    unclaimed = sum(len(report["unclaimed"]) for report in reports)
    if unclaimed:
        sys.exit(1)
