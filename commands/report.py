"""`pm report` — the weekly state-of-product report.

Gathers per workstream, works out what changed since last week, asks the local
model to write each section, then assembles a Markdown report with a reference
table of real links.

Reads the workstream list from `cfg['_workstreams']`, which pm.py has already
narrowed if --workstream was given.
"""

import datetime as dt
import sys

from core import checklist, citations, comments, epics, output, sources, model, state, workstreams
from core import products as product_core


def build_report(cfg, sections, all_items, scope_note):
    today = dt.date.today().isoformat()
    audience = cfg.get("output", {}).get("audience") or "stakeholders"
    lines = [
        "# Weekly State-of-Product Report",
        f"_Prepared for {audience} on {today}.{scope_note}_",
        "",
        "This snapshot covers in-sprint work, roadmap movement, decisions, "
        "dependencies, and open risks for each workstream. Every claim is "
        "tagged to a source; full links are in the reference table at the end.",
        "",
    ]

    body_by = {ws["abbrev"]: body for ws, body in sections}
    groups = product_core.group_workstreams(cfg, [ws for ws, _ in sections])
    show_products = bool(product_core.listed_products(cfg)) or len(groups) > 1

    if show_products and groups:
        lines.append("## Portfolio")
        lines.append("")
        lines.append("| Product | Workstreams | Items |")
        lines.append("|---------|-------------|------:|")
        items_by_ws = {}
        for it in all_items:
            # ref looks like SDX-J1; fall back to counting per section order
            prefix = it.get("workstream") or ""
            items_by_ws[prefix] = items_by_ws.get(prefix, 0) + 1
        for product, streams in groups:
            abbrevs = ", ".join(ws["abbrev"] for ws in streams)
            count = sum(items_by_ws.get(ws["abbrev"], 0) for ws in streams)
            lines.append(f"| {product['name']} ({product['abbrev']}) | "
                         f"{abbrevs} | {count} |")
        lines.append("")

    printed_shared_done = False
    for product, streams in groups or [({}, [ws for ws, _ in sections])]:
        if show_products and product:
            lines.append(f"## {product['name']} ({product['abbrev']})")
            lines.append("")
            goal = checklist.product_goal(product)
            if goal:
                lines.append(f"Product Goal: {goal}")
                lines.append("")
            lines.extend(_increment_lines(cfg, product))
        elif not printed_shared_done:
            lines.extend(_increment_lines(cfg, None))
            printed_shared_done = True
        for ws in streams:
            heading = (f"### {ws['name']} ({ws['abbrev']})"
                       if show_products and product
                       else f"## {ws['name']} ({ws['abbrev']})")
            lines.append(heading)
            lines.append("")
            lines.append(body_by.get(ws["abbrev"], ""))
            lines.append("")

    # Reference table — built from the real items, so links are guaranteed.
    lines.append("## References")
    lines.append("")
    if all_items:
        lines.append("| Ref | Source | Item | Link |")
        lines.append("|-----|--------|------|------|")
        for it in all_items:
            title = it["title"].replace("|", "\\|")
            lines.append(
                f"| {it['ref']} | {it['source']} | {title} | "
                f"[{it.get('ref') or 'link'}]({it['url']}) |")
    else:
        lines.append("_No source items were gathered this week._")
    lines.append("")
    return "\n".join(lines)


def _increment_lines(cfg, product):
    """Definition of Done next to the Increment. Omitted when unset."""
    items = checklist.definition_items(cfg, product)
    if not items:
        return []
    lines = ["### Increment", "",
             "Definition of Done for this Increment:", ""]
    for item in items:
        if item.get("label"):
            lines.append(f"- {item['text']} _(label: {item['label']})_")
        else:
            lines.append(f"- {item['text']}")
    lines.append("")
    return lines


def prepare(cfg, ws, previous, window=None):
    """Items and the change block `pm report` will send. Writes nothing."""
    prefix = ws["abbrev"]
    items = []
    idx = 1
    overrides = None
    if window and window.get("sprint_id"):
        overrides = {"sprint": window["sprint_id"]}
    sprint_jql = workstreams.scope_jql(cfg, ws, "report", overrides=overrides)
    roadmap_jql = workstreams.scope_jql(cfg, ws, "roadmap")
    got, idx = sources.fetch_jira(cfg["jira"], sprint_jql, prefix, idx)
    items += got
    got, idx = sources.fetch_jira(cfg["jira"], roadmap_jql, prefix, idx)
    items += got
    idx = 1
    from core import pages as page_core
    page_opts = page_core.settings(cfg)
    prev_snapshot = previous.get(prefix, {}) if isinstance(previous, dict) else {}
    if not isinstance(prev_snapshot, dict):
        prev_snapshot = {}
    if window and window.get("explicit") and window.get("start"):
        cutoff = dt.datetime.combine(
            window["start"], dt.time.min, tzinfo=dt.timezone.utc)
        page_since = window["start"]
    else:
        cutoff = comments.report_cutoff(prev_snapshot, comments.settings(cfg))
        page_since = None
    page_opts_full = page_core.page_settings(cfg)
    scope = "labelled" if page_opts_full.get("scope") == "labelled" else "space"
    types = page_opts_full["content_types"] + page_opts_full["title_only_types"]
    from core import filters
    cql = filters.build_cql(ws, cfg, scope=scope, types=types) or workstreams.confluence_cql(ws, cfg)
    got, idx = sources.fetch_confluence(cfg["confluence"],
                                        cql,
                                        prefix, idx, since=page_since)
    got = page_core.apply_excerpt(got, page_opts, cutoff=cutoff)
    items += got
    idx = 1
    got, idx = sources.fetch_sharepoint(cfg["sharepoint"],
                                        ws.get("sharepoint_query"), prefix, idx)
    items += got
    first_run = prefix not in previous
    for item in items:
        item["workstream"] = prefix
    docs = [it for it in items if it.get("source") != "Jira"]
    citations.assign_doc_tags(docs)
    jira_items = [it for it in items if it.get("source") == "Jira"]
    comments.attach(
        cfg, cfg.get("jira") or {}, jira_items,
        comments.report_cutoff(prev_snapshot, comments.settings(cfg)))
    new, changed, dropped = state.compute_changes(prev_snapshot, items)
    change_block = state.build_change_block(new, changed, dropped, first_run)
    epic_rows = epics.build(cfg, ws, items, window, (new, changed, dropped))
    page_core.map_to_epics(
        [it for it in items if it.get("source") == "Confluence"], epic_rows)
    return {
        "items": items,
        "change_block": change_block,
        "snapshot": state.snapshot_items(items),
        "first_run": first_run,
        "new": new,
        "changed": changed,
        "dropped": dropped,
        "epics": epic_rows,
    }


def run(cfg, args):
    """Entry point called by pm.py."""
    selected = cfg["_workstreams"]

    state_path = output.place(
        cfg, cfg["output"].get("state_file", "report_state.json"),
        getattr(args, "out", None))
    previous = state.load_state(state_path)
    new_state = dict(previous)   # keep untouched workstreams' memory intact

    from core import window as window_core
    projects = []
    for ws in selected:
        project = (ws.get("project") or (cfg.get("jira") or {}).get("project"))
        if project and project not in projects:
            projects.append(project)
    try:
        window = window_core.resolve(
            cfg, args, default_start=None, projects=projects)
    except window_core.WindowError as exc:
        sys.exit(str(exc))

    prepared = []
    for ws in selected:
        print(f"Gathering: {ws['name']} ({ws['abbrev']}) ...")
        row = prepare(cfg, ws, previous, window)
        if not row["first_run"]:
            print(f"  changes: {len(row['new'])} new, "
                  f"{len(row['changed'])} changed, "
                  f"{len(row['dropped'])} dropped")
        prepared.append((ws, row))
        snapshot = dict(row["snapshot"])
        snapshot["_ran_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        new_state[ws["abbrev"]] = snapshot

    sections = []
    all_items = []
    model.announce(cfg["model"], len(prepared), "pm report")

    for ws, row in prepared:
        print(f"  found {len(row['items'])} items — asking the model to write it up ...")
        model.tick(cfg["model"], ws["abbrev"])
        body = model.infer_report_section(
            cfg["model"], cfg["output"]["audience"],
            ws, row["items"], row["change_block"],
            comment_budget=comments.settings(cfg)["section_chars"],
            cfg=cfg)
        body, removed = citations.resolve(body, citations.citation_map(row["items"]))
        if removed:
            print(f"  ({ws['abbrev']}: {removed} citation removed — not in the material)")
            noun = "citation" if removed == 1 else "citations"
            verb = "it was" if removed == 1 else "they were"
            body = body.rstrip() + f"\n\n_{removed} {noun} removed: {verb} not in the material._\n"
        sections.append((ws, body))
        all_items += row["items"]

    if window.get("explicit"):
        print(f"Window: {window['label']} (this run does not move the "
              "last-report memory).")
    else:
        state.save_state(state_path, new_state)

    scope_note = ""
    if len(selected) < len(cfg["workstreams"]):
        scope_note = (" Scope: "
                      + ", ".join(w["abbrev"] for w in selected) + ".")

    report = build_report(cfg, sections, all_items, scope_note)
    try:
        from commands import metrics as metrics_cmd
        groups = metrics_cmd.gather(cfg, 8)
        report = report.rstrip() + "\n\n" + metrics_cmd.render(groups, 8)
    except Exception as exc:                              # noqa: BLE001
        print(f"Metrics appendix skipped: {exc}")
    out_path = output.place(
        cfg, cfg["output"]["file"].format(date=dt.date.today().isoformat()),
        getattr(args, "out", None))
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)

    print(f"\nDone. Report written to: {out_path}")
    preview = "\n".join(report.splitlines()[:24])
    print("\n" + preview)
    if getattr(args, "publish", False):
        from commands import publish as pub
        pub.publish_file(cfg, args, out_path)
