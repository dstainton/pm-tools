"""`pm ready` — a Definition of Ready (DoR) gate.

Answers one question for each item about to enter a sprint: "Is this ready to
work on — yes or no?" It bundles the deterministic lint checks into a single
pass/fail verdict per ticket, using a checklist you define in config.

  pm ready            Fast gate — deterministic checks only.
  pm ready --deep     Also run the model reviews (title clarity, AC quality)
                      and treat those as blocking too.

How the verdict works:
  * Every DoR criterion maps to one or more lint rules (or a model review).
  * A ticket is READY only if none of its BLOCKING criteria are triggered.
  * Non-blocking criteria still show up as advisories but don't fail the gate.

This is the check to run just before sprint planning: green means "good to
pull in", red means "needs work first, here's exactly what".
"""

import datetime as dt

from core import sources, workstreams
from commands import lint, review


# Maps a friendly DoR criterion -> the lint rule(s) that prove it is met.
# You choose which of these BLOCK readiness in config under `ready:`.
CRITERION_RULES = {
    "clear-title": ["vague-title"],
    "has-acceptance-criteria": ["missing-acceptance-criteria"],
    "has-estimate": ["no-estimate"],
    "linked-to-epic": ["missing-epic"],
    "has-component": ["missing-component"],
    "sane-dates": ["bad-dates"],
}


def evaluate_issue(issue, lint_cfg, blocking, deep_findings, component_inherited=False):
    """Return a verdict dict for one issue.

    deep_findings: set of aspects ("titles"/"criteria") the model flagged for
    this issue, or None if --deep was not used.
    """
    # Run the deterministic checks and index them by rule.
    lint_findings = lint.check_issue(issue, lint_cfg, component_inherited)
    triggered_rules = {f["rule"]: f["message"] for f in lint_findings}

    failed, advisory = [], []
    for criterion, rules in CRITERION_RULES.items():
        hit_msg = next((triggered_rules[r] for r in rules
                        if r in triggered_rules), None)
        if hit_msg is None:
            continue
        entry = {"criterion": criterion, "reason": hit_msg}
        (failed if criterion in blocking else advisory).append(entry)

    # Fold in model reviews when --deep was used.
    if deep_findings is not None:
        if "titles" in deep_findings and "clear-title" in blocking:
            failed.append({"criterion": "clear-title (model)",
                           "reason": deep_findings["titles"]})
        elif "titles" in deep_findings:
            advisory.append({"criterion": "clear-title (model)",
                             "reason": deep_findings["titles"]})
        if "criteria" in deep_findings and "has-acceptance-criteria" in blocking:
            failed.append({"criterion": "acceptance-criteria (model)",
                           "reason": deep_findings["criteria"]})
        elif "criteria" in deep_findings:
            advisory.append({"criterion": "acceptance-criteria (model)",
                             "reason": deep_findings["criteria"]})

    return {
        "key": issue["key"],
        "url": issue["url"],
        "title": issue["summary"],
        "type": issue["issuetype"],
        "ready": len(failed) == 0,
        "failed": failed,
        "advisory": advisory,
    }


def build_markdown(cfg, results, deep):
    today = dt.date.today().isoformat()
    mode = "deep (rules + model)" if deep else "fast (rules only)"
    lines = [
        "# Definition of Ready — Gate Report",
        f"_Run on {today} in {mode} mode. A ticket is **Ready** only when every "
        "blocking criterion is met._",
        "",
    ]

    # Summary across workstreams.
    lines.append("## Summary")
    lines.append("")
    lines.append("| Workstream | Ready | Not ready | % ready |")
    lines.append("|-----------|------:|----------:|--------:|")
    g_ready = g_total = 0
    for ws, verdicts in results:
        ready = sum(1 for v in verdicts if v["ready"])
        total = len(verdicts)
        pct = f"{(100 * ready / total):.0f}%" if total else "—"
        lines.append(f"| {ws['abbrev']} | {ready} | {total - ready} | {pct} |")
        g_ready += ready
        g_total += total
    g_pct = f"{(100 * g_ready / g_total):.0f}%" if g_total else "—"
    lines.append(f"| **Total** | **{g_ready}** | **{g_total - g_ready}** | "
                 f"**{g_pct}** |")
    lines.append("")

    # Detail per workstream — not-ready items first, with reasons.
    for ws, verdicts in results:
        lines.append(f"## {ws['name']} ({ws['abbrev']})")
        lines.append("")
        if not verdicts:
            lines.append("_No items in the ready scope._")
            lines.append("")
            continue

        not_ready = [v for v in verdicts if not v["ready"]]
        ready = [v for v in verdicts if v["ready"]]

        if not_ready:
            lines.append("### 🔴 Not ready")
            lines.append("")
            lines.append("| Issue | Type | Blocking gaps | Link |")
            lines.append("|-------|------|---------------|------|")
            for v in not_ready:
                title = sources.short(v["title"], 55).replace("|", "\\|")
                gaps = "; ".join(f"{f['criterion']}: {f['reason']}"
                                 for f in v["failed"]).replace("|", "\\|")
                lines.append(f"| {v['key']}: {title} | {v['type']} | "
                             f"{gaps} | [open]({v['url']}) |")
            lines.append("")

        if ready:
            lines.append("### 🟢 Ready")
            lines.append("")
            for v in ready:
                title = sources.short(v["title"], 70)
                note = ""
                if v["advisory"]:
                    note = (f" _(advisory: "
                            + ", ".join(a["criterion"] for a in v["advisory"])
                            + ")_")
                lines.append(f"- **{v['key']}**: {title}{note}")
            lines.append("")

    return "\n".join(lines)


def _gather_deep(cfg, ws, issues):
    """Run model reviews for one workstream; return {issue_key: {aspect: reason}}."""
    deep = {}
    model_cfg = cfg["model"]
    batch = cfg.get("review", {}).get("batch_size", 8)
    for aspect in ("titles", "criteria"):
        findings, _errors = review.review_aspect(model_cfg, aspect, issues, batch)
        for f in findings:
            deep.setdefault(f["key"], {})[aspect] = f["problem"]
    return deep


def run(cfg, args):
    lint_cfg = cfg.get("lint", {})
    ready_cfg = cfg.get("ready", {})
    blocking = set(ready_cfg.get("blocking_criteria",
                                 list(CRITERION_RULES.keys())))
    deep = getattr(args, "deep", False)

    results = []
    for ws in cfg["_workstreams"]:
        jql = workstreams.scope_jql(cfg, ws, "ready")
        if not jql:
            print(f"Skipping {ws['abbrev']}: nothing in its ready scope.")
            results.append((ws, []))
            continue

        print(f"Checking readiness: {ws['name']} ({ws['abbrev']}) ...")
        issues = sources.fetch_jira_detailed(cfg["jira"], jql)
        component_inherited = workstreams.uses_component_scope(cfg, ws)

        deep_map = _gather_deep(cfg, ws, issues) if deep else {}

        verdicts = []
        for issue in issues:
            df = deep_map.get(issue["key"]) if deep else None
            verdicts.append(evaluate_issue(
                issue, lint_cfg, blocking, df, component_inherited))

        ready_n = sum(1 for v in verdicts if v["ready"])
        print(f"  {len(issues)} items — {ready_n} ready, "
              f"{len(issues) - ready_n} not ready.")
        results.append((ws, verdicts))

    report = build_markdown(cfg, results, deep)
    out_path = f"ready_report_{dt.date.today().isoformat()}.md"
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"\nDone. Readiness report written to: {out_path}")
