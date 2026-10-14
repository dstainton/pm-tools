"""Phase 1C: concise terminal assessment and detailed Markdown evidence."""

import datetime as dt
import os
import sys

from core import assessment, dispositions, inventory, output, progress, queries, review_queue, workstreams, sources


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



def _completed(cfg, project, jql_override=None):
    """Separate approximate completed count; never mix with open inventory."""
    jql = jql_override or "project = {} AND {}".format(
        queries.quote(project), queries.render(cfg, "status.done"))
    try:
        return {"status": "approximate", "count": sources.approximate_count(
            cfg["jira"], jql), "jql": jql}
    except Exception as exc:
        return {"status": "unavailable", "count": None, "jql": jql,
                "reason": "{}: {}".format(type(exc).__name__, exc)}


def _completed_line(inv):
    item = inv.get("completed_summary") or {"status": "unavailable"}
    if item["status"] == "approximate":
        return "Approximately {} completed issues (separate Jira count)".format(
            item["count"])
    return "Completed-work count unavailable" + (
        ": " + item["reason"] if item.get("reason") else "")


def _distribution(inv, facts):
    groups = review_queue.build(inv, facts)
    return groups, max(0, facts["count"] - sum(g["count"] for g in groups))


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
        groups, without = _distribution(inventory_result, result)
        lines.append("  Completed work: " + _completed_line(inventory_result))
        lines.append("  Excluded work: " + _completed_line({"completed_summary": inventory_result.get("excluded_summary")}))
        lines.append("  Investigation queue (all groups):")
        lines.extend("    {} ({} issues)".format(g["title"], g["count"])
                     for g in groups)
        lines.append("    No review signals ({} issues)".format(without))
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
        lines.extend(["", "### Completed work (separate population)", "",
                      _completed_line(inv) + "."])
        completed = inv.get("completed_summary") or {}
        if completed.get("jql"):
            lines.append("Jira query: `" + completed["jql"] + "`")
        lines.append("This is an approximate Jira count, not a complete inventory; "
                     "completed issues are excluded from the open-work assessment.")
        scope = inv.get("dispositions") or {}
        if scope:
            lines.extend(["", "### Effective disposition rules", ""])
            for kind in ("active", "completed", "excluded"):
                lines.append("- {}: {} (JQL: `{}`)".format(
                    kind.capitalize(), ", ".join(scope["status_names"][kind]) or "(none)",
                    scope["jql"][kind]))
            excluded = inv.get("excluded_summary") or {}
            lines.append("- Excluded-work count: " + (
                str(excluded["count"]) + " (approximate)"
                if excluded.get("status") == "approximate" else "unavailable"))
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
        groups, without = _distribution(inv, result)
        lines.extend(["", "### Investigation queue", "",
                      "Each issue appears in only one review group. This is an "
                      "investigation order, not an implementation priority. "
                      "Sample rows are limited to 12 per group; complete rule "
                      "evidence appears in the appendix.", ""])
        lines.append("**{} issues in review groups; {} issues with no review signals.**".format(
            sum(g["count"] for g in groups), without))
        if not groups:
            lines.append("No review signals for the retrieved records.")
        for group in groups:
            lines.extend(["", "#### {} ({} issues)".format(
                group["title"], group["count"]), "",
                group["rationale"], "",
                "| Issue | Status | Last updated | Summary |",
                "| --- | --- | ---: | --- |"])
            for row in group["sample"]:
                key, url = row["key"], row["url"]
                link = "[{}]({})".format(key, url) if url else key
                days = row["updated_age_days"]
                age = "{} days ago".format(days) if days is not None else "Unknown"
                title = str(row["title"]).replace("|", "\\|").replace("\\n", " ")
                lines.append("| {} | {} | {} | {} |".format(
                    link, row["status"], age, title))
            if group["count"] > len(group["sample"]):
                lines.append("")
                lines.append("{} further issues. See the evidence appendix.".format(
                    group["count"] - len(group["sample"])))
        lines.extend(["", "### Interpretation and limitations", "",
                      "- Last Jira update does not establish business relevance, "
                      "obsolescence, or delivery progress.",
                      "- Workstream claims reflect configured membership rules, "
                      "not definitive accountability.",
                      "- Investigation order is not a validated product priority.",
                      "- Optional and missing Jira fields may be intentional; "
                      "unconfigured fields cannot be checked.",
                      "- Review groups are exclusive; individual review "
                      "signals can overlap.", ""])
        lines.extend(["", "### Complete rule evidence (appendix)", "",
                      "Each issue can appear more than once here because it "
                      "may have multiple independent review signals.", "",
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
    for index, project in enumerate(projects, 1):
        progress.start(progress.numbered(index, len(projects),
                                         'Resolving Jira dispositions in ' + project))
        try:
            scope = dispositions.resolve(cfg, project)
        except Exception as exc:
            sys.exit('Cannot classify Jira statuses for {}: {}'.format(project, exc))
        progress.start('Reading active Jira issues in ' + project)
        inv = inventory.open_issues(cfg, project, jql_override=scope['jql']['active'])
        inv['dispositions'] = scope
        if inv["status"] == "failed":
            sys.exit("Jira inventory failed for {}: {}".format(
                project, inv["reason"] or "unknown error"))
        progress.start('Checking workstream ownership in ' + project)
        try:
            claims = _claims(cfg, project)
        except Exception as exc:
            sys.exit("Workstream membership could not be verified for {}: {}: {}".format(
                project, type(exc).__name__, exc))
        progress.start('Counting completed work in ' + project)
        inv['completed_summary'] = _completed(cfg, project, scope['jql']['completed'])
        progress.start('Counting excluded work in ' + project)
        inv['excluded_summary'] = _completed(cfg, project, scope['jql']['excluded'])
        progress.start('Analyzing backlog in ' + project)
        results.append((inv, assessment.analyze(inv, today, claims=claims)))
    progress.finish()
    print(summary(results), end="")
    filename = "assessment-{}.md".format(today.isoformat())
    progress.start('Writing Markdown assessment report')
    target = output.place(cfg, filename, getattr(args, "out", None))
    with open(target, "w", encoding="utf-8") as stream:
        stream.write(markdown(results))
    progress.finish()
    print("Detailed report: " + target)
    if any(not result["complete"] for _, result in results):
        sys.exit(1)
