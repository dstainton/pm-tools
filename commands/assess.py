"""Phase 1C: concise terminal assessment and detailed Markdown evidence."""

import datetime as dt
import os
import sys

from core import assessment, inventory, output, workstreams, sources


def _projects(cfg, requested=None):
    if requested:
        return [part.strip() for part in requested.split(",") if part.strip()]
    selected = cfg.get("_workstreams") or []
    projects = sorted({workstreams.project_of(cfg, ws) for ws in selected
                       if workstreams.project_of(cfg, ws)})
    if not projects and (cfg.get("jira") or {}).get("project"):
        projects = [cfg["jira"]["project"]]
    return projects


def _claims(cfg, project):
    """Collect all configured workstream claims, not just a selected subset."""
    streams = [ws for ws in cfg.get("workstreams", [])
               if workstreams.project_of(cfg, ws) == project]
    if not streams:
        return None
    claims = {}
    for ws in streams:
        jql = workstreams.scope_jql(cfg, ws, "lint")
        if not jql:
            continue
        for key in sources.fetch_jira_keys(cfg["jira"], jql):
            claims.setdefault(key, set()).add(ws.get("abbrev") or "?")
    return {key: sorted(values) for key, values in claims.items()}


def _count_lines(result):
    return ["  {}: {}".format(key.replace("-", " "), value)
            for key, value in result["finding_counts"].items()]


def summary(results):
    lines = ["Backlog assessment", ""]
    for inventory_result, result in results:
        project = result["project"]
        lines.extend([
            "{} | {} | {} open issues".format(
                project, result["inventory_status"].upper(), result["count"]),
            "  Query: {}".format(inventory_result["jql"]),
            "  Workstream ownership: {}".format(
                "evaluated" if result["ownership_evaluated"] else "not evaluated"),
        ])
        if not result["complete"]:
            lines.append("  WARNING: incomplete inventory: " +
                         (result["inventory_reason"] or "retrieval was not complete"))
        if inventory_result["missing_config"]:
            lines.append("  Unconfigured optional fields: " +
                         ", ".join(inventory_result["missing_config"]))
        ranked = sorted(result["finding_counts"].items(),
                        key=lambda item: (-item[1], item[0]))
        lines.append("  Review signals:")
        lines.extend("    {}: {}".format(rule, count) for rule, count in ranked[:8])
        if not ranked:
            lines.append("    None in the retrieved records")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def markdown(results):
    lines = ["# Backlog assessment", "",
             "This is a read-only review of open Jira work. Findings are "
             "investigation signals, not strategic priorities or proof that "
             "an issue should be closed.", ""]
    for inv, result in results:
        lines.extend([
            "## " + str(result["project"]), "",
            "- Assessment date: " + result["today"],
            "- Retrieved at: " + inv["retrieved_at"],
            "- Retrieval status: **" + result["inventory_status"] + "**",
            "- Open issues retrieved: **" + str(result["count"]) + "**",
            "- Pages retrieved: " + str(inv["pages"]),
            "- Query: `" + inv["jql"] + "`",
            "- Workstream ownership: " + (
                "evaluated" if result["ownership_evaluated"] else
                "not evaluated (workstreams not configured)"),
        ])
        if result["inventory_reason"]:
            lines.append("- Coverage limitation: **" + result["inventory_reason"] + "**")
        if inv["missing_config"]:
            lines.append("- Unconfigured optional fields: " +
                         ", ".join(inv["missing_config"]))
        for title, values in (("Issue types", result["by_type"]),
                              ("Status categories", result["by_status_category"]),
                              ("Created age (days)", result["created_age_bands"]),
                              ("Updated age (days)", result["updated_age_bands"])):
            lines.extend(["", "### " + title, "", "| Category | Count |",
                          "| --- | ---: |"])
            lines.extend("| {} | {} |".format(key, count)
                         for key, count in values.items())
        lines.extend(["", "### Review signals", "",
                      "| Finding | Count |", "| --- | ---: |"])
        lines.extend("| {} | {} |".format(key, count)
                     for key, count in sorted(
                         result["finding_counts"].items(),
                         key=lambda item: (-item[1], item[0])))
        if not result["finding_counts"]:
            lines.append("| None observed | 0 |")
        lines.extend(["", "### Issue evidence", "",
                      "| Finding | Issue | Detail |", "| --- | --- | --- |"])
        for finding in result["findings"]:
            key = finding["key"]
            url = finding["url"]
            link = "[{}]({})".format(key, url) if url else key
            detail = str(finding["detail"]).replace("|", "\\|").replace("\n", " ")
            lines.append("| {} | {} | {} |".format(finding["rule"], link, detail))
        if not result["findings"]:
            lines.append("| None observed | | |")
        lines.extend(["", "Missing labels and components may be intentional; "
                      "absence is not automatically a defect. Jira last-updated "
                      "age does not prove when a human last reviewed the need.", ""])
    return "\n".join(lines).rstrip() + "\n"


def run(cfg, args):
    projects = _projects(cfg, getattr(args, "project", None))
    if not projects:
        sys.exit("No Jira project found. Use pm assess --project KEY or configure jira.project.")
    today = dt.date.today()
    results = []
    for project in projects:
        inv = inventory.open_issues(cfg, project)
        if inv["status"] == "failed":
            sys.exit("Jira inventory failed for {}: {}".format(
                project, inv["reason"] or "unknown error"))
        try:
            claims = _claims(cfg, project)
        except Exception as exc:
            sys.exit("Workstream membership could not be verified for {}: {}: {}".format(
                project, type(exc).__name__, exc))
        results.append((inv, assessment.analyze(inv, today, claims=claims)))
    print(summary(results), end="")
    filename = "assessment-{}.md".format(today.isoformat())
    target = output.place(cfg, filename, getattr(args, "out", None))
    with open(target, "w", encoding="utf-8") as stream:
        stream.write(markdown(results))
    print("Detailed report: " + target)
    if any(not result["complete"] for _, result in results):
        sys.exit(1)
