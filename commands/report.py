"""`pm report` — the weekly state-of-product report.

Gathers per workstream, works out what changed since last week, asks the local
model to write each section, then assembles a Markdown report with a reference
table of real links.

Reads the workstream list from `cfg['_workstreams']`, which pm.py has already
narrowed if --workstream was given.
"""

import datetime as dt

from core import sources, model, state, workstreams
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
            prefix = (it.get("ref") or "").split("-")[0]
            items_by_ws[prefix] = items_by_ws.get(prefix, 0) + 1
        for product, streams in groups:
            abbrevs = ", ".join(ws["abbrev"] for ws in streams)
            count = sum(items_by_ws.get(ws["abbrev"], 0) for ws in streams)
            lines.append(f"| {product['name']} ({product['abbrev']}) | "
                         f"{abbrevs} | {count} |")
        lines.append("")

    for product, streams in groups or [({}, [ws for ws, _ in sections])]:
        if show_products and product:
            lines.append(f"## {product['name']} ({product['abbrev']})")
            lines.append("")
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
                f"[open]({it['url']}) |")
    else:
        lines.append("_No source items were gathered this week._")
    lines.append("")
    return "\n".join(lines)


def run(cfg, args):
    """Entry point called by pm.py."""
    selected = cfg["_workstreams"]

    state_path = cfg["output"].get("state_file", "report_state.json")
    previous = state.load_state(state_path)
    new_state = dict(previous)   # keep untouched workstreams' memory intact

    sections = []
    all_items = []

    for ws in selected:
        prefix = ws["abbrev"]
        print(f"Gathering: {ws['name']} ({prefix}) ...")

        items = []
        idx = 1
        sprint_jql = workstreams.scope_jql(cfg, ws, "report")
        roadmap_jql = workstreams.scope_jql(cfg, ws, "roadmap")
        got, idx = sources.fetch_jira(cfg["jira"], sprint_jql, prefix, idx)
        items += got
        got, idx = sources.fetch_jira(cfg["jira"], roadmap_jql, prefix, idx)
        items += got
        idx = 1
        got, idx = sources.fetch_confluence(cfg["confluence"],
                                            workstreams.confluence_cql(ws),
                                            prefix, idx)
        items += got
        idx = 1
        got, idx = sources.fetch_sharepoint(cfg["sharepoint"],
                                            ws.get("sharepoint_query"), prefix, idx)
        items += got

        prev_snapshot = previous.get(prefix, {})
        first_run = prefix not in previous
        new, changed, dropped = state.compute_changes(prev_snapshot, items)
        change_block = state.build_change_block(new, changed, dropped, first_run)
        new_state[prefix] = state.snapshot_items(items)
        if not first_run:
            print(f"  changes: {len(new)} new, {len(changed)} changed, "
                  f"{len(dropped)} dropped")

        print(f"  found {len(items)} items — asking the model to write it up ...")
        body = model.infer_report_section(cfg["model"], cfg["output"]["audience"],
                                          ws, items, change_block)

        sections.append((ws, body))
        all_items += items

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
    except Exception:                              # noqa: BLE001
        pass
    out_path = cfg["output"]["file"].format(date=dt.date.today().isoformat())
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)

    print(f"\nDone. Report written to: {out_path}")
    if getattr(args, "publish", False):
        from commands import publish as pub
        pub.publish_file(cfg, args, out_path)
