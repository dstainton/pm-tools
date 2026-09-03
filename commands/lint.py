"""`pm lint` — deterministic backlog quality checks.

No model involved. These are plain rules a computer can apply with certainty,
so you can trust the output completely and run it before every sprint planning.

Rules (all tunable in config under `lint:`):
  * missing-component            field hygiene (idea 3)
  * missing-epic                 field hygiene (idea 3)
  * vague-title                  cheap heuristic version of idea 1
  * missing-acceptance-criteria  keyword version of idea 2
  * no-estimate                  unestimated in-scope stories
  * bad-dates                    due before start / due in past (idea 4)
  * stale                        in progress but untouched for N days

Severities:
  error  - almost certainly wrong (date contradictions)
  warn   - should be fixed (missing fields, no estimate, stale)
  review - a judgement flag for a human to glance at (vague titles)
"""

import datetime as dt
import json
import re

from core import sources, workstreams


SEVERITY_ORDER = {"error": 0, "warn": 1, "review": 2}


# ---------------------------------------------------------------------------
#  Small date parsers (tolerant of Jira's formats)
# ---------------------------------------------------------------------------

def parse_date(value):
    """Parse 'YYYY-MM-DD' into a date, or return None."""
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def parse_datetime(value):
    """Parse Jira's ISO timestamp (e.g. 2026-08-10T09:12:00.000-0700)."""
    if not value:
        return None
    text = str(value)
    # Normalise a trailing timezone like -0700 to -07:00 for fromisoformat.
    text = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", text.replace("Z", "+00:00"))
    for candidate in (text, text.split(".")[0]):
        try:
            parsed = dt.datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
#  The checks — one issue in, a list of findings out
# ---------------------------------------------------------------------------

def check_issue(issue, lint_cfg, component_inherited=False):
    findings = []
    itype = (issue["issuetype"] or "").lower()
    is_epic = itype == "epic"
    done = issue["status_category"] == "done"
    in_progress = issue["status_category"] == "indeterminate"

    def add(rule, severity, message):
        findings.append({
            "key": issue["key"],
            "url": issue["url"],
            "title": issue["summary"],
            "type": issue["issuetype"],
            "rule": rule,
            "severity": severity,
            "message": message,
        })

    required = [r.lower() for r in lint_cfg.get("required_fields", [])]

    # --- Missing component -------------------------------------------------
    if ("component" in required or "components" in required) \
            and not is_epic and not component_inherited and not issue["components"]:
        add("missing-component", "warn", "No component set.")

    # --- Missing epic / parent --------------------------------------------
    if "epic" in required and not is_epic and not issue["epic"]:
        add("missing-epic", "warn", "Not linked to an epic/parent.")

    # --- Vague title -------------------------------------------------------
    title = (issue["summary"] or "").strip()
    tokens = set(re.findall(r"[a-z0-9]+", title.lower()))
    min_words = lint_cfg.get("min_title_words", 3)
    if len(title.split()) < min_words:
        add("vague-title", "review",
            f"Title is only {len(title.split())} word(s); may be too vague.")
    else:
        vague = [t.lower() for t in lint_cfg.get("vague_title_terms", [])]
        hits = [t for t in vague if t in tokens]
        if hits:
            add("vague-title", "review",
                f"Title contains vague term(s): {', '.join(sorted(hits))}.")

    # --- Missing acceptance criteria (stories/bugs) -----------------------
    story_types = [t.lower() for t in lint_cfg.get("story_types",
                                                   ["story", "bug"])]
    if lint_cfg.get("require_acceptance_criteria", True) and itype in story_types:
        if issue["acceptance_criteria"].strip():
            has_ac = True
        else:
            markers = [m.lower() for m in
                       lint_cfg.get("acceptance_criteria_markers", [])]
            haystack = (issue["acceptance_criteria"] + " "
                        + issue["description"]).lower()
            has_ac = any(m in haystack for m in markers)
        if not has_ac:
            add("missing-acceptance-criteria", "warn",
                "No acceptance criteria found.")

    # --- Missing estimate (stories only, and only if in scope) ------------
    if lint_cfg.get("require_estimate", True) and itype == "story" \
            and not done:
        sp = issue["story_points"]
        if sp in (None, "", 0, 0.0):
            add("no-estimate", "warn", "No story-point estimate.")

    # --- Date sanity -------------------------------------------------------
    start = parse_date(issue["start_date"])
    due = parse_date(issue["due_date"])
    today = dt.date.today()
    if start and due and due < start:
        add("bad-dates", "error",
            f"Due date {due} is before start date {start}.")
    if due and due < today and not done:
        add("bad-dates", "error",
            f"Due date {due} has passed but the item is not done.")

    # --- Stale in-progress -------------------------------------------------
    stale_days = lint_cfg.get("stale_days", 14)
    updated = parse_datetime(issue["updated"])
    if in_progress and updated:
        age = (dt.datetime.now(dt.timezone.utc) - updated).days
        if age > stale_days:
            add("stale", "warn",
                f"In progress but untouched for {age} days.")

    return findings


# ---------------------------------------------------------------------------
#  Output
# ---------------------------------------------------------------------------

def build_markdown(cfg, results):
    """results: list of (workstream, findings) tuples."""
    today = dt.date.today().isoformat()
    lines = [
        "# Backlog Lint Report",
        f"_Deterministic checks run on {today}. No model involved — every "
        "finding is a rule, not an opinion._",
        "",
    ]

    # Summary table across all workstreams.
    lines.append("## Summary")
    lines.append("")
    from core import products as product_core
    show_product = bool(product_core.listed_products(cfg))
    if show_product:
        lines.append("| Product | Workstream | Errors | Warnings | Review |")
        lines.append("|---------|-----------|-------:|---------:|-------:|")
    else:
        lines.append("| Workstream | Errors | Warnings | Review |")
        lines.append("|-----------|-------:|---------:|-------:|")
    grand = {"error": 0, "warn": 0, "review": 0}
    for ws, findings in results:
        counts = {"error": 0, "warn": 0, "review": 0}
        for fnd in findings:
            counts[fnd["severity"]] += 1
            grand[fnd["severity"]] += 1
        if show_product:
            lines.append(f"| {product_core.product_abbrev_of(ws)} | "
                         f"{ws['abbrev']} | {counts['error']} | "
                         f"{counts['warn']} | {counts['review']} |")
        else:
            lines.append(f"| {ws['abbrev']} | {counts['error']} | "
                         f"{counts['warn']} | {counts['review']} |")
    if show_product:
        lines.append(f"| | **Total** | **{grand['error']}** | "
                     f"**{grand['warn']}** | **{grand['review']}** |")
    else:
        lines.append(f"| **Total** | **{grand['error']}** | "
                     f"**{grand['warn']}** | **{grand['review']}** |")
    lines.append("")

    # Detail per workstream.
    icon = {"error": "🔴", "warn": "🟠", "review": "🔵"}
    for ws, findings in results:
        lines.append(f"## {ws['name']} ({ws['abbrev']})")
        lines.append("")
        if not findings:
            lines.append("_No issues found. Clean backlog._")
            lines.append("")
            continue
        # Sort: errors first, then warnings, then review; stable within.
        findings.sort(key=lambda f: (SEVERITY_ORDER[f["severity"]], f["rule"]))
        lines.append("| Issue | Type | Check | Finding | Link |")
        lines.append("|-------|------|-------|---------|------|")
        for f in findings:
            msg = f["message"].replace("|", "\\|")
            title = sources.short(f["title"], 60).replace("|", "\\|")
            lines.append(
                f"| {f['key']}: {title} | {f['type']} | "
                f"{icon[f['severity']]} {f['rule']} | {msg} | "
                f"[open]({f['url']}) |")
        lines.append("")

    return "\n".join(lines)


def run(cfg, args):
    """Entry point called by pm.py."""
    lint_cfg = cfg.get("lint", {})
    min_sev = SEVERITY_ORDER.get(getattr(args, "severity", None), 99)

    results = []
    flat = []  # for --json
    for ws in cfg["_workstreams"]:
        jql = workstreams.scope_jql(cfg, ws, "lint")
        if not jql:
            print(f"Skipping {ws['abbrev']}: nothing in its lint scope "
                  f"(no components matched, and no lint filter configured).")
            results.append((ws, []))
            continue

        print(f"Linting: {ws['name']} ({ws['abbrev']}) ...")
        issues = sources.fetch_jira_detailed(cfg["jira"], jql)
        component_inherited = workstreams.uses_component_scope(cfg, ws)

        findings = []
        for issue in issues:
            for fnd in check_issue(issue, lint_cfg, component_inherited):
                if SEVERITY_ORDER[fnd["severity"]] <= min_sev or min_sev == 99:
                    findings.append(fnd)
                    flat.append({**fnd, "workstream": ws["abbrev"]})

        print(f"  {len(issues)} issues checked — {len(findings)} findings.")
        results.append((ws, findings))

    if getattr(args, "json", False):
        out_path = "lint_report_{}.json".format(dt.date.today().isoformat())
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(flat, fh, indent=2)
        print(f"\nDone. Findings written to: {out_path}")
        return

    report = build_markdown(cfg, results)
    out_path = "lint_report_{}.md".format(dt.date.today().isoformat())
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"\nDone. Lint report written to: {out_path}")
