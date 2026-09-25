"""`pm ready` — the team's working agreement for pulling work into a Sprint.

Answers one question for each item about to enter a sprint: "Is this ready to
work on — yes or no?" It bundles the deterministic lint checks into a single
pass/fail verdict per ticket, using the criteria the team listed in config.
That list is a working agreement, not a Scrum rule.

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

import sys

from core import checklist, model, output, sources, workstreams
from core import products as product_core
from commands import lint, review


# Maps a friendly DoR criterion -> the lint rule(s) that prove it is met.
# You choose which of these BLOCK readiness in config under `ready:`.
CRITERION_RULES = {
    "clear-title": ["vague-title"],
    "has-acceptance-criteria": ["missing-acceptance-criteria"],
    "has-estimate": ["no-estimate"],
    "linked-to-parent": ["missing-parent"],
    "has-component": ["missing-component"],
    "sane-dates": ["bad-dates"],
}


def _positive_points(issue):
    """A real estimate, or None. Missing and zero are not 'too big'."""
    value = issue.get("story_points")
    if value in (None, "", 0, 0.0):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None
    if value <= 0:
        return None
    return value


def size_failure(issue, max_points):
    """Why `too-big-for-a-sprint` fails, or None.

    An item with no estimate does not fail this rule. `has-estimate` covers
    that case.
    """
    points = _positive_points(issue)
    if points is None:
        return None
    limit = float(max_points if max_points is not None else 8)
    if points > limit:
        return f"{points:g} points is above the sprint size of {limit:g}"
    return None


def evaluate_issue(issue, lint_cfg, blocking, deep_findings,
                   component_inherited=False, max_points=8):
    """Return a verdict dict for one issue.

    deep_findings: set of aspects ("titles"/"criteria") the model flagged for
    this issue, or None if --deep was not used.
    """
    # Run the deterministic checks and index them by rule.
    lint_findings = lint.check_issue(issue, lint_cfg, component_inherited)
    triggered_rules = {f["rule"]: f["message"] for f in lint_findings}

    failed, advisory = [], []
    if "too-big-for-a-sprint" in blocking:
        reason = size_failure(issue, max_points)
        if reason:
            failed.append({"criterion": "too-big-for-a-sprint", "reason": reason})

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


def label_gaps(done_issues, items):
    """Done items missing a Definition of Done label. Reminders are skipped."""
    labeled = [item for item in items if item.get("label")]
    gaps = []
    for issue in done_issues or []:
        present = {str(label).lower() for label in (issue.get("labels") or [])}
        for item in labeled:
            if item["label"].lower() not in present:
                gaps.append({
                    "key": issue.get("key"),
                    "summary": issue.get("summary") or "",
                    "label": item["label"],
                    "text": item["text"],
                })
    return gaps


def _checklist_for(cfg, ws):
    product = None
    abbrev = (ws.get("product") or "").strip()
    if abbrev:
        product = product_core.resolve_product(cfg, abbrev)
    return checklist.definition_items(cfg, product)


def build_markdown(cfg, results, deep, reminders=None, gaps=None):
    today = dt.date.today().isoformat()
    mode = "deep (rules + model)" if deep else "fast (rules only)"
    lines = [
        "# Ready agreement",
        f"_Run on {today} in {mode} mode. This is the team's working agreement "
        "for pulling work into a Sprint. A ticket is **Ready** only when every "
        "blocking criterion is met._",
        "",
    ]

    # Summary across workstreams.
    lines.append("## Summary")
    lines.append("")
    from core import products as product_core
    show_product = bool(product_core.listed_products(cfg))
    if show_product:
        lines.append("| Product | Workstream | Ready | Not ready | % ready |")
        lines.append("|---------|-----------|------:|----------:|--------:|")
    else:
        lines.append("| Workstream | Ready | Not ready | % ready |")
        lines.append("|-----------|------:|----------:|--------:|")
    g_ready = g_total = 0
    for ws, verdicts in results:
        ready = sum(1 for v in verdicts if v["ready"])
        total = len(verdicts)
        pct = f"{(100 * ready / total):.0f}%" if total else "—"
        if show_product:
            lines.append(f"| {product_core.product_abbrev_of(ws)} | "
                         f"{ws['abbrev']} | {ready} | {total - ready} | {pct} |")
        else:
            lines.append(f"| {ws['abbrev']} | {ready} | {total - ready} | {pct} |")
        g_ready += ready
        g_total += total
    g_pct = f"{(100 * g_ready / g_total):.0f}%" if g_total else "—"
    if show_product:
        lines.append(f"| | **Total** | **{g_ready}** | **{g_total - g_ready}** | "
                     f"**{g_pct}** |")
    else:
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
                gap_text = "; ".join(f"{f['criterion']}: {f['reason']}"
                                     for f in v["failed"]).replace("|", "\\|")
                lines.append(f"| {v['key']}: {title} | {v['type']} | "
                             f"{gap_text} | [{v.get('key') or 'link'}]({v['url']}) |")
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

    reminders = list(reminders or [])
    gaps = list(gaps or [])
    if reminders or gaps:
        lines.append("## Definition of Done")
        lines.append("")
        lines.append("A checklist, not a verifier. Lines without a label "
                     "are reminders only.")
        lines.append("")
        if reminders:
            for text in reminders:
                lines.append(f"- {text}")
            lines.append("")
        if gaps:
            lines.append("Done items missing a label:")
            lines.append("")
            for gap in gaps:
                lines.append(
                    f"- **{gap['key']}** lacks `{gap['label']}` "
                    f"({gap['text']})")
            lines.append("")

    return "\n".join(lines)


def _gather_deep(cfg, ws, issues):
    """Run model reviews for one workstream; return {issue_key: {aspect: reason}}."""
    deep = {}
    model_cfg = cfg["model"]
    batch = cfg.get("review", {}).get("batch_size", 8)
    total = review.call_count(("titles", "criteria"), issues, batch)
    model.announce(model_cfg, total, f"pm ready --deep ({ws['abbrev']})")
    for aspect in ("titles", "criteria"):
        model_cfg["_progress_detail"] = f"{ws['abbrev']}, {aspect}"
        findings, _errors = review.review_aspect(
            model_cfg, aspect, issues, batch, cfg)
        for f in findings:
            deep.setdefault(f["key"], {})[aspect] = f["problem"]
    model_cfg.pop("_progress_detail", None)
    return deep


def run(cfg, args):
    lint_cfg = cfg.get("lint", {})
    ready_cfg = cfg.get("ready", {})
    blocking = set(ready_cfg.get("blocking_criteria",
                                 list(CRITERION_RULES.keys())))
    max_points = ready_cfg.get("max_points", 8)
    deep = getattr(args, "deep", False)

    results = []
    reminders = []
    gaps = []
    seen_reminders = set()
    for ws in cfg["_workstreams"]:
        items = _checklist_for(cfg, ws)
        for item in items:
            if not item.get("label") and item["text"] not in seen_reminders:
                seen_reminders.add(item["text"])
                reminders.append(item["text"])

        jql = workstreams.scope_jql(cfg, ws, "ready")
        if not jql:
            print(f"Skipping {ws['abbrev']}: nothing in its ready scope.")
            results.append((ws, []))
            continue

        from core import progress
        progress.start(f"Checking readiness: {ws['name']} ({ws['abbrev']})")
        issues = sources.fetch_jira_detailed(cfg["jira"], jql)
        component_inherited = workstreams.uses_component_scope(cfg, ws)

        deep_map = _gather_deep(cfg, ws, issues) if deep else {}

        verdicts = []
        for issue in issues:
            df = deep_map.get(issue["key"]) if deep else None
            verdicts.append(evaluate_issue(
                issue, lint_cfg, blocking, df, component_inherited,
                max_points=max_points))

        ready_n = sum(1 for v in verdicts if v["ready"])
        print(f"  {len(issues)} items — {ready_n} ready, "
              f"{len(issues) - ready_n} not ready.")
        results.append((ws, verdicts))

        if any(item.get("label") for item in items):
            done_jql = workstreams.scope_jql(
                cfg, ws, "ready", overrides={"status": "done"})
            done = (sources.fetch_jira_detailed(cfg["jira"], done_jql)
                    if done_jql else [])
            gaps.extend(label_gaps(done, items))

    report = build_markdown(cfg, results, deep, reminders=reminders, gaps=gaps)
    out_path = output.place(
        cfg, f"ready_report_{dt.date.today().isoformat()}.md",
        getattr(args, "out", None))
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"\nDone. Readiness report written to: {out_path}")

    fail_under = getattr(args, "fail_under", None)
    if fail_under is not None:
        total = sum(len(verdicts) for _ws, verdicts in results)
        ready_n = sum(1 for _ws, verdicts in results
                      for verdict in verdicts if verdict["ready"])
        percent = 100.0 if total == 0 else (100.0 * ready_n / total)
        if percent < fail_under:
            sys.exit(1)
