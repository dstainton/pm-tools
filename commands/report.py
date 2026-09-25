"""`pm report` — the weekly state-of-product report.

Gathers per workstream, works out what changed since last week, asks the local
model to write each section, then assembles a Markdown report with a reference
table of real links.

Reads the workstream list from `cfg['_workstreams']`, which pm.py has already
narrowed if --workstream was given.
"""

import datetime as dt
import sys

from core import audience, checklist, citations, comments, epics, output, pages as page_core, registers, report_render, sources, model, state, workstreams
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


def prepare(cfg, ws, previous, window=None, skip_ids=None):
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
    page_window = dict(window or {})
    if page_since:
        page_window["start"] = page_since
    elif cutoff is not None:
        page_window.setdefault("start", cutoff.date() if hasattr(cutoff, "date") else cutoff)
    got = page_core.gather(cfg, ws, window=page_window, skip_ids=skip_ids)
    from core import page_summaries
    page_summaries.fill(cfg, got)
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
        [it for it in items if it.get("source") == "Confluence"], epic_rows,
        cfg=cfg)
    return {
        "items": items,
        "change_block": change_block,
        "snapshot": state.snapshot_items(items),
        "first_run": first_run,
        "new": new,
        "changed": changed,
        "dropped": dropped,
        "epics": epic_rows,
        "loose_pages": [it for it in items
                        if it.get("source") == "Confluence" and not it.get("epic")
                        and not it.get("product_only")],
    }


def _seen_page_ids(prepared):
    seen = set()
    for _ws, row in prepared:
        for item in row.get("items") or []:
            if item.get("page_id"):
                seen.add(str(item["page_id"]))
    return seen


def _inside(page, folder_ids):
    return any(str(a) in folder_ids for a in page.get("ancestor_ids") or [])


def _attach_product_pages(cfg, groups, prepared, window, skip_ids):
    """Pages from a product space or folder, attached to the owning workstream.

    A product folder is read once. Pages already gathered for a workstream,
    or kept inside a workstream folder, are left to that workstream. A
    product that only sets `confluence_space` still contributes the whole
    space. A page that no in-scope Epic owns is marked `product_only`; it is
    material for the first workstream and is listed under the product.
    """
    from core import confluence_tree, page_summaries
    from core import pages as page_core
    by_abbrev = {ws["abbrev"]: row for ws, row in prepared}
    seen = _seen_page_ids(prepared)
    stream_folders = set(confluence_tree.folder_ids(cfg, "workstream"))
    for product, streams in groups:
        if not streams:
            continue
        located = confluence_tree.locate_product(cfg, product)
        has_page = product.get("confluence_page") or product.get("confluence_page_id")
        if has_page and (located.get("missing") or not located.get("ancestor_id")):
            continue
        if located.get("ancestor_id") and located.get("space"):
            fake_ws = {
                "abbrev": product.get("abbrev") or "",
                "confluence_space": located["space"],
                "confluence_page_id": located["ancestor_id"],
                "confluence_labels": [],
                "product": product.get("abbrev") or "",
            }
        else:
            space = product.get("confluence_space")
            if not space:
                continue
            fake_ws = {
                "abbrev": product.get("abbrev") or "",
                "confluence_space": space,
                "confluence_labels": [],
                "product": product.get("abbrev") or "",
            }
        epics = []
        owner = {}
        for ws in streams:
            for epic in (by_abbrev[ws["abbrev"]].get("epics") or []):
                epics.append(epic)
                if epic.get("key"):
                    owner[epic["key"]] = ws["abbrev"]
        found = page_core.gather(
            cfg, fake_ws, product=product, epics=epics, window=window, skip_ids=skip_ids)
        found = [page for page in found if not _inside(page, stream_folders)
                 and str(page.get("page_id") or "") not in seen]
        page_summaries.fill(cfg, found)
        page_core.map_to_epics(found, epics, cfg=cfg)
        for page in found:
            if str(page.get("page_id") or "") in seen:
                continue
            seen.add(str(page.get("page_id") or ""))
            target = owner.get(page.get("epic"))
            if not target:
                page["product_only"] = True
                target = streams[0]["abbrev"]
            row = by_abbrev[target]
            row["items"].append(page)
            if page.get("product_only"):
                row.setdefault("product_pages", []).append(page)
            elif page.get("epic"):
                pass
            else:
                row.setdefault("loose_pages", []).append(page)
        for ws in streams:
            row = by_abbrev[ws["abbrev"]]
            docs = [it for it in row["items"] if it.get("source") != "Jira"]
            citations.assign_doc_tags(docs)
            loose = [it for it in docs if it.get("source") == "Confluence"
                     and not it.get("epic") and not it.get("product_only")]
            row["loose_pages"] = loose


def _product_pages(prepared, streams):
    abbrevs = {ws["abbrev"] for ws in streams}
    return [item for ws, row in prepared if ws["abbrev"] in abbrevs
            for item in row.get("items") or [] if item.get("product_only")]


def team_pages(cfg, prepared, window, skip_ids):
    """Changed pages under the team page that sit in no product or workstream folder.

    A page an in-scope Epic owns joins that workstream instead. The rest are
    marked `team_only` and listed once, near the top of the report.
    """
    from core import confluence_tree, page_summaries
    from core import pages as page_core
    if not confluence_tree.has_team_page(cfg):
        return []
    root = confluence_tree.team_root_id(cfg)
    space = confluence_tree.team_space(cfg)
    if not root or not space:
        return []
    folders = set(confluence_tree.folder_ids(cfg))
    folders.discard(root)
    seen = _seen_page_ids(prepared)
    by_abbrev = {ws["abbrev"]: row for ws, row in prepared}
    epics, owner = [], {}
    for ws, row in prepared:
        for epic in row.get("epics") or []:
            epics.append(epic)
            if epic.get("key"):
                owner[epic["key"]] = ws["abbrev"]
    fake_ws = {"abbrev": "TEAM", "confluence_space": space,
               "confluence_page_id": root, "confluence_labels": []}
    found = page_core.gather(cfg, fake_ws, epics=None, window=window, skip_ids=skip_ids)
    found = [page for page in found if not _inside(page, folders)
             and str(page.get("page_id") or "") not in seen
             and str(page.get("page_id") or "") != root]
    page_summaries.fill(cfg, found)
    page_core.map_to_epics(found, epics, cfg=cfg)
    team = []
    for page in found:
        target = owner.get(page.get("epic"))
        if target:
            row = by_abbrev[target]
            row["items"].append(page)
            continue
        page["team_only"] = True
        team.append(page)
    return team


def section_material(cfg, row):
    """The exact text `pm report` and `pm warm` send for one workstream."""
    from core import pages as page_core
    opts = page_core.settings(cfg)
    entries = []
    abbrev = None
    for epic in row.get("epics") or []:
        for item in epic.get("items") or []:
            if item.get("workstream"):
                abbrev = item["workstream"]
                break
    epic_keys = {epic.get("key") for epic in row.get("epics") or [] if epic.get("key")}
    for record in row.get("registers") or []:
        scope = record.get("scope") or {}
        if scope.get("workstream") and scope.get("workstream") != abbrev:
            continue
        if scope.get("product"):
            # Product and portfolio entries join this section only when an
            # Epic in this workstream owns them.
            pass
        elif scope.get("workstream") and scope.get("workstream") != abbrev:
            continue
        for entry in record.get("entries") or []:
            matched = entry.get("epic") if entry.get("epic") in epic_keys else ""
            if not matched:
                for key in entry.get("keys") or []:
                    if key in epic_keys:
                        matched = key
                        break
            if scope.get("product") or not scope:
                if not matched:
                    continue
            copied = dict(entry)
            copied["epic"] = matched
            entries.append(copied)
    return model.build_grouped_material(
        row.get("epics") or [],
        row.get("loose_pages") or [],
        comment_budget=comments.settings(cfg)["section_chars"],
        page_budget=opts["section_chars"],
        register_entries=entries,
    )


def _audience_summaries(cfg, groups, prepared, sections, who):
    """One model call per product. Leadership may cite Epics, not child keys."""
    from core import prompts
    by_ws = {ws["abbrev"]: (ws, row, body) for (ws, row), (_w, body) in zip(prepared, sections)}
    summaries = []
    roles = ("waiting", "risks", "dependencies")
    role_names = [prompts.heading(cfg, "report.section", role) for role in roles]
    for product, streams in groups:
        facts = []
        allowed = []
        docs = []
        for ws in streams:
            row = by_ws.get(ws["abbrev"], (None, {}, ""))[1]
            body = by_ws.get(ws["abbrev"], (None, {}, ""))[2]
            for epic in row.get("epics") or []:
                if not epic.get("key"):
                    continue
                if who == "partner" and not audience.partner_visible_epic(
                        epic, ws, audience.settings(cfg)["partner"]):
                    continue
                allowed.append(epic["key"])
                done = epic.get("children_done") or 0
                total = epic.get("children_total") or 0
                due = f" | due {epic['due']}" if epic.get("due") else ""
                signal = epic.get("signal") or ""
                reason = epic.get("signal_reason") or ""
                if signal == "At risk" and reason:
                    signal = f"{signal}: {reason}"
                facts.append(
                    f"- [{epic['key']}] {epic.get('summary')} | {ws['abbrev']} | "
                    f"{epic.get('status')} | {done} of {total} done{due} | {signal}"
                )
            for item in row.get("items") or []:
                if item.get("source") == "Jira":
                    continue
                kind = (item.get("kind") or "").lower()
                if kind in ("decision", "risk", "dependency") or item.get("is_new"):
                    docs.append(item)
        if who == "partner" and not facts:
            continue
        from core import checklist
        goal = checklist.product_goal(product) or "none"
        if who == "partner":
            text = _partner_facts(cfg, product, streams, by_ws)
        else:
            text = f"Product Goal: {goal}\n\nEpics:\n" + ("\n".join(facts) or "- none")
        if who == "leadership":
            if docs:
                lines = []
                for page in docs[:5]:
                    summary = f" {page['summary']}" if page.get("summary") else ""
                    lines.append(
                        f"- [{page.get('ref') or 'D?'}] {page.get('kind') or page.get('type')}: "
                        f"{page.get('title')}.{summary}"
                    )
                text += "\n\nDocuments:\n" + "\n".join(lines)
            reg_lines = []
            for record in _register_records_from(prepared):
                for entry in record.get("entries") or []:
                    if entry.get("change") not in ("new", "changed"):
                        continue
                    reg_lines.append(
                        f"- [{entry.get('ref') or 'D?'}] {record.get('type')}, "
                        f"{entry.get('change')}, {entry.get('status') or ''}: "
                        f"{entry.get('title')}. {entry.get('summary') or ''}".rstrip()
                    )
                    if entry.get("ref"):
                        allowed.append(entry["ref"])
            if reg_lines:
                text += "\n\nRegisters:\n" + "\n".join(reg_lines)
            team = []
            for ws in streams:
                body = by_ws.get(ws["abbrev"], (None, {}, ""))[2]
                pulled = report_render.extract_sections(body, role_names)
                for name in role_names:
                    chunk = report_render.strip_links(pulled.get(name) or "")
                    if chunk:
                        team.append(f"{ws['abbrev']}, {name}: {chunk}")
            if team:
                text += "\n\nFrom the team reports:\n" + "\n".join(team)
        model.tick(cfg["model"], product.get("abbrev") or "product")
        if who == "leadership":
            body = model.infer_leadership(cfg["model"], product, text, cfg=cfg)
            base = ((cfg.get("jira") or {}).get("base_url") or "").rstrip("/")
            cite = {key: (key, f"{base}/browse/{key}") for key in allowed if "-" in str(key) and not str(key).startswith("D")}
            for page in docs:
                if page.get("ref"):
                    cite[page["ref"]] = (page.get("title") or page["ref"], page.get("url") or "")
            body, removed = citations.resolve(body, cite)
            if removed:
                print(f"  ({product.get('abbrev')}: {removed} citation removed — not in the material)")
        else:
            body = model.infer_partner(cfg["model"], product, text, cfg=cfg)
        summaries.append(body)
    return summaries


def _partner_facts(cfg, product, streams, by_ws):
    """Feature names, status phrases, and progress. No keys or team names."""
    opts = audience.settings(cfg)["partner"]
    lines = [f"Product: {product.get('name')}", "", "Features:"]
    docs = []
    for ws in streams:
        row = by_ws.get(ws["abbrev"], (None, {}, ""))[1]
        for epic in row.get("epics") or []:
            if not epic.get("key"):
                continue
            if not audience.partner_visible_epic(epic, ws, opts):
                continue
            total = epic.get("children_total") or 0
            done = epic.get("children_done") or 0
            pct = f"{int(100 * done / total)}%" if total else "0%"
            phrase = {"new": "Planned", "done": "Delivered"}.get(
                (epic.get("status_category") or "").lower(), "In progress")
            due = ""
            if opts.get("show_target_dates") and epic.get("due"):
                due = f" | target {epic['due']}"
            lines.append(f"- {epic.get('summary') or 'Feature'} | {phrase} | {pct} done{due}")
            titles = []
            excluded = {str(label).lower() for label in opts.get("exclude_labels") or []}
            for item in epic.get("items") or []:
                labels = {str(label).lower() for label in item.get("labels") or []}
                if labels & excluded:
                    continue
                if (item.get("status_category") or "").lower() == "done":
                    titles.append(item.get("summary") or "")
            if titles:
                lines.append("  Done this period: " + ", ".join(titles))
        for item in row.get("items") or []:
            if item.get("source") == "Jira":
                continue
            if audience.partner_visible_page(item, opts):
                docs.append(item)
    if not any(line.startswith("- ") for line in lines):
        lines.append("- none")
    if docs:
        lines.append("")
        lines.append("Documents:")
        for page in docs[:5]:
            summary = f" {page['summary']}" if page.get("summary") else ""
            lines.append(f"- {page.get('title') or 'page'}.{summary}")
    return "\n".join(lines)


def stamp_register_entries(row):
    """Attach matched register entries to the Epic that owns them."""
    by_key = {epic.get("key"): epic for epic in row.get("epics") or [] if epic.get("key")}
    abbrev = ""
    for epic in row.get("epics") or []:
        for item in epic.get("items") or []:
            if item.get("workstream"):
                abbrev = item["workstream"]
                break
    for record in row.get("registers") or []:
        scope = record.get("scope") or {}
        if scope.get("workstream") and abbrev and scope.get("workstream") != abbrev:
            continue
        for entry in record.get("entries") or []:
            matched = entry.get("epic") if entry.get("epic") in by_key else ""
            if not matched:
                for key in entry.get("keys") or []:
                    if key in by_key:
                        matched = key
                        break
            if not matched:
                continue
            copied = dict(entry)
            copied["register_type"] = record.get("type")
            by_key[matched].setdefault("register_entries", []).append(copied)


def _register_records_from(prepared):
    for _ws, row in prepared:
        if row.get("registers"):
            return row["registers"]
    return []


def run(cfg, args):
    """Entry point called by pm.py."""
    selected = cfg["_workstreams"]

    who = audience.level(cfg, args)
    if who == "partner" and getattr(args, "publish", False):
        sys.exit("Read a partner report before it leaves. "
                 "Publish it with: pm publish <file>")
    state_path = audience.state_path(cfg, who, args)
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

    found_registers, skip_ids = registers.gather(cfg, window, previous)
    prepared = []
    for ws in selected:
        print(f"Gathering: {ws['name']} ({ws['abbrev']}) ...")
        row = prepare(cfg, ws, previous, window, skip_ids=skip_ids)
        row["registers"] = found_registers
        stamp_register_entries(row)
        if not row["first_run"]:
            print(f"  changes: {len(row['new'])} new, "
                  f"{len(row['changed'])} changed, "
                  f"{len(row['dropped'])} dropped")
        prepared.append((ws, row))
        snapshot = dict(row["snapshot"])
        snapshot["_ran_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        new_state[ws["abbrev"]] = snapshot

    groups = product_core.group_workstreams(cfg, [ws for ws, _row in prepared])
    team = []
    if len(selected) == len(cfg["workstreams"]):
        team = team_pages(cfg, prepared, window, skip_ids)
    _attach_product_pages(cfg, groups, prepared, window, skip_ids)

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
            cfg=cfg, material=section_material(cfg, row))
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
        # `_registers` is not a workstream abbrev; state walks abbrevs only.
        new_state["_registers"] = registers.saved_memory(cfg, found_registers)
        state.save_state(state_path, new_state)

    scope_note = ""
    if len(selected) < len(cfg["workstreams"]):
        scope_note = (" Scope: "
                      + ", ".join(w["abbrev"] for w in selected) + ".")

    base = ((cfg.get("jira") or {}).get("base_url") or "").rstrip("/")
    for _ws, row in prepared:
        for epic in row.get("epics") or []:
            if epic.get("key") and not epic.get("url") and base:
                epic["url"] = f"{base}/browse/{epic['key']}"
    if who == "leadership":
        summaries = _audience_summaries(cfg, groups, prepared, sections, who)
        report = report_render.render_leadership(cfg, groups, prepared, summaries, window)
        try:
            from commands import metrics as metrics_cmd
            report = report.rstrip() + "\n\n" + metrics_cmd.render_headline(
                metrics_cmd.gather(cfg, 8), 8)
        except Exception as exc:                              # noqa: BLE001
            print(f"Delivery table skipped: {exc}")
    elif who == "partner":
        opts = audience.settings(cfg)["partner"]
        visible = []
        for ws, row in prepared:
            for epic in row.get("epics") or []:
                if epic.get("key") and audience.partner_visible_epic(epic, ws, opts):
                    visible.append(epic)
        if not visible:
            sys.exit("No Epic is marked for partners. Add the label "
                     "partner-visible to an Epic, or set partner_visible: true "
                     "on a workstream.")
        summaries = _audience_summaries(cfg, groups, prepared, sections, who)
        report = report_render.render_partner(cfg, groups, prepared, summaries, window)
        names = set()
        for _ws, row in prepared:
            for item in row["items"]:
                if item.get("assignee"):
                    names.add(item["assignee"])
                if item.get("updated_by"):
                    names.add(item["updated_by"])
        allowed = {epic["key"] for epic in visible} if opts.get("include_jira_links") else set()
        report, removed = audience.redact(report, names, allowed, drop_all_keys=not opts.get("include_jira_links"))
        if removed:
            print(f"{removed} line{'s' if removed != 1 else ''} removed")
    else:
        report = report_render.render_pm(
            cfg, groups, prepared, sections, window, scope_note, who=who,
            team_pages=team)
    if who == "pm":
        try:
            from commands import metrics as metrics_cmd
            report = report.rstrip() + "\n\n" + metrics_cmd.render(metrics_cmd.gather(cfg, 8), 8)
        except Exception as exc:                              # noqa: BLE001
            print(f"Metrics appendix skipped: {exc}")
    out_path = output.place(
        cfg, audience.output_name(cfg, who, dt.date.today().isoformat()),
        getattr(args, "out", None))
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)

    if getattr(args, "json", False):
        import json
        payload = {"audience": who, "window": window, "products": [],
                   "team_pages": team}
        for product, streams in groups:
            block = {"abbrev": product.get("abbrev") or "", "workstreams": [],
                     "pages": _product_pages(prepared, streams)}
            for ws in streams:
                row = next(r for w, r in prepared if w["abbrev"] == ws["abbrev"])
                section = next((body for w, body in sections if w["abbrev"] == ws["abbrev"]), "")
                block["workstreams"].append({
                    "abbrev": ws["abbrev"],
                    "epics": row.get("epics") or [],
                    "pages": [it for it in row["items"] if it.get("source") != "Jira"
                              and not it.get("product_only")],
                    "section": section,
                })
            payload["products"].append(block)
        json_path = out_path.replace(".md", ".json")
        if json_path == out_path:
            json_path = out_path + ".json"
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, default=str, indent=2)
    calls = int((cfg.get("model") or {}).get("_calls") or 0)
    hits = int((cfg.get("model") or {}).get("_cache_hits") or 0)
    print(f"{calls} model call(s), {hits} already cached.")
    print(f"\nDone. Report written to: {out_path}")
    preview = "\n".join(report.splitlines()[:24])
    print("\n" + preview)
    if getattr(args, "publish", False):
        from commands import publish as pub
        pub.publish_file(cfg, args, out_path,
                         labels=["pm-report", f"pm-audience-{who}"])
