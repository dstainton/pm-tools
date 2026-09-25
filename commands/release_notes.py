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
        "parent": issue.get("epic") or "",
        "issuetype": issue.get("issuetype") or "",
        "labels": list(issue.get("labels") or []),
        "assignee": issue.get("assignee") or "",
    }


def collect(cfg, since, version):
    """Done issues in the window, grouped by the workstream that claims them.

    Issues no selected workstream claims land under Unassigned.
    """
    from core import progress
    window = _window(since, version)
    overrides = {"status": "done", "sprint": "any", "extra_jql": window}
    rows = []
    claimed = set()
    streams = cfg.get("_workstreams") or []
    seen = 0
    for product, group in product_core.group_workstreams(cfg, streams):
        for ws in group:
            seen += 1
            progress.start(progress.numbered(
                seen, len(streams),
                f"{ws.get('name')} — reading done issues"))
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
    if projects:
        progress.start("Reading issues no workstream claims")
    for project in projects:
        jql = queries.render(cfg, "release_notes.done", project=project, window=window)
        for issue in sources.fetch_jira_detailed(cfg["jira"], jql):
            if issue.get("key") in claimed:
                continue
            rows.append(_row(
                {"name": "Unassigned", "abbrev": "UNASSIGNED"},
                {"name": "Unclaimed", "abbrev": "—"},
                issue))
    if rows and comments.settings(cfg).get("enabled"):
        progress.start("Reading comments")
    _attach_comments(cfg, rows, since)
    _walk_epics(cfg, rows)
    progress.finish()
    return rows


def _walk_epics(cfg, rows):
    """A Sub-task's parent is its Story. Walk up to the Epic."""
    from core import epics
    if not rows:
        return
    epic_types = workstreams.membership_settings(cfg)["epic_types"]
    items = []
    for row in rows:
        items.append({
            "key": row.get("key"),
            "parent": row.get("parent") or None,
            "issuetype": row.get("issuetype") or "",
            "source": "Jira",
            "summary": row.get("summary") or "",
            "status": "",
        })
    parents, fields = epics.parent_map(cfg, items, epic_types)
    types = {key: (info.get("issuetype") or "") for key, info in fields.items()}
    for row in rows:
        found = epics.epic_of(row.get("key"), parents, types, epic_types)
        if found:
            row["epic"] = found
            info = fields.get(found) or {}
            if info.get("summary"):
                row["epic_summary"] = info["summary"]


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


def bullet_lines(rows, comment_budget=6000, level="pm", cfg=None):
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
            shown = list(stream["issues"])
            if level == "partner":
                shown = [issue for issue in shown if issue.get("partner_visible")]
            buckets = []
            for issue in shown:
                label = issue.get("epic") or ""
                title = issue.get("epic_summary") or label
                if not buckets or buckets[-1][0] != label:
                    buckets.append((label, title, []))
                buckets[-1][2].append(issue)
            if level == "leadership":
                from core import epics
                keys = [label for label, _title, _issues in buckets if label]
                counts = epics.child_counts(cfg, keys, cfg) if cfg is not None and keys else {}
                for label, title, issues in buckets:
                    name = title or "Not under an Epic"
                    extra = ""
                    bucket = counts.get(label) or {}
                    if bucket.get("total"):
                        extra = f" ({bucket.get('done') or 0} of {bucket['total']})"
                    if label:
                        url = ""
                        sample = issues[0].get("url") or ""
                        if "/browse/" in sample:
                            url = sample.split("/browse/")[0] + "/browse/" + label
                        shown = f"[{label}]({url}) {name}" if url else f"{label} {name}"
                    else:
                        shown = name
                    lines.append(f"- {shown} — {len(issues)} done this window{extra}")
                lines.append("")
                continue
            multiple = len(buckets) > 1 or (buckets and buckets[0][0])
            for label, title, issues in buckets:
                if multiple and (label or len(buckets) > 1):
                    heading = f"{label} {title}".strip() if label else "Not under an Epic"
                    lines.append(f"**{heading}**")
                    lines.append("")
                for issue in issues:
                    if level == "partner" and not issue.get("show_keys"):
                        lines.append(f"- {issue['summary']}")
                    else:
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


def draft(cfg, bullets, level="pm"):
    """Model prose, or None when the model was skipped."""
    system = prompts.get(cfg, "release_notes.prose")
    if level == "partner":
        system = system + "\n" + prompts.get(cfg, "release_notes.partner_rules")
    from core import progress
    progress.start("Writing the release notes")
    raw = model.call_model(cfg["model"], system, "\n".join(bullets))
    if _skipped(raw):
        return None
    return raw.strip()


def render(since, version, rows, prose, comment_budget=6000, level="pm", extras=None, cfg=None):
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
    bullets = bullet_lines(rows, comment_budget, level, cfg=cfg)
    if prose:
        lines.append(prose)
        lines.append("")
        lines.append("## Issues")
        lines.append("")
    else:
        lines.append("The model was skipped.")
        lines.append("")
    lines.extend(bullets)
    lines.extend(extras or [])
    return "\n".join(lines).rstrip() + "\n"


def _mark_partner(cfg, rows):
    from core import audience, sources as source_core
    opts = audience.settings(cfg)["partner"]
    wanted = {str(label).lower() for label in opts.get("epic_labels") or []}
    excluded = {str(label).lower() for label in opts.get("exclude_labels") or []}
    parents = sorted({row.get("epic") for row in rows if row.get("epic")})
    labels = {}
    if parents:
        for raw in source_core.fetch_issues_by_key(cfg.get("jira") or {}, parents, ["labels", "summary"]):
            fields = raw.get("fields") or {}
            labels[raw.get("key")] = {
                "labels": list(fields.get("labels") or []),
                "summary": fields.get("summary") or "",
            }
    show_keys = bool(opts.get("include_jira_links"))
    for row in rows:
        info = labels.get(row.get("epic")) or {}
        row["epic_summary"] = info.get("summary") or ""
        own = {str(label).lower() for label in row.get("labels") or []}
        epic_labels = {str(label).lower() for label in info.get("labels") or []}
        row["partner_visible"] = bool((own | epic_labels) & wanted) and not (own & excluded)
        row["show_keys"] = show_keys


def _extras(cfg, since, version, level, rows=None):
    lines = []
    if version and not since:
        lines.extend(["## Further reading", "",
                      "_Skipped: only a fixVersion was given._", ""])
        return lines
    if since and level != "partner":
        from core import registers
        import datetime as dt
        found, _skip = registers.gather(
            cfg, {"start": dt.date.fromisoformat(since)}, {})
        decisions = []
        for record in found:
            if record.get("type") not in ("decision", "adr"):
                continue
            for entry in record.get("entries") or []:
                if str(entry.get("status") or "").lower() != "accepted":
                    continue
                if entry.get("change") not in ("new", "changed"):
                    continue
                decisions.append(f"- {entry.get('title')}")
        if decisions:
            lines.extend(["## Decisions made in this release", ""] + decisions + [""])
    if since:
        from core import pages as page_core
        import datetime as dt
        window = {"start": dt.date.fromisoformat(since)}
        collected = []
        for ws in cfg.get("_workstreams") or []:
            collected.extend(page_core.gather(cfg, ws, window=window))
        stubs = []
        seen = set()
        for row in rows or []:
            key = row.get("epic")
            if key and key not in seen:
                seen.add(key)
                stubs.append({"key": key, "summary": row.get("epic_summary") or key,
                              "pages": [], "in_scope": True})
        if stubs:
            page_core.map_to_epics(collected, stubs, cfg=cfg)
        by_epic = {}
        for page in collected:
            by_epic.setdefault(page.get("epic") or "", []).append(page)
        reading = []
        for key, pages in by_epic.items():
            stub = next((row for row in stubs if row.get("key") == key), None)
            title = (stub or {}).get("summary") or key or "Not under an Epic"
            heading = f"**{key} {title}**".strip() if key else "**Not under an Epic**"
            reading.append(heading)
            reading.append("")
            for page in pages:
                reading.append(f"- {page.get('title')}")
            reading.append("")
        if reading:
            lines.extend(["## Further reading", ""] + reading)
    return lines


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
    _mark_partner(cfg, rows)
    bullets = bullet_lines(rows, budget, level, cfg=cfg)
    prose = draft(cfg, bullets, level) if rows else None
    text = render(since, version, rows, prose, budget, level,
                  _extras(cfg, since, version, level, rows), cfg=cfg)
    if level == "partner":
        from core import audience
        names = {row.get("assignee") for row in rows if row.get("assignee")}
        opts = audience.settings(cfg)["partner"]
        text, removed = audience.redact(
            text, names, set(), drop_all_keys=not opts.get("include_jira_links"))
        if removed:
            print(f"{removed} line{'s' if removed != 1 else ''} removed")
    path = output.place(
        cfg, f"release_notes_{dt.date.today().isoformat()}.md",
        getattr(args, "out", None))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text)
    print(f"Done. Release notes written to: {path}")
