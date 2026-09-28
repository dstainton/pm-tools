"""`pm warm` — fill the model cache before you need the answer.

Read-only. It writes no Jira, edits no config, and writes no report. The
only side effect is reply files under the model cache. Stop it whenever
you like: every reply already stored is kept, and the next run continues
from there.

`pm schedule add warm --at 07:00` runs it before you sit down. `pm review`
and `pm ready --deep` ask the same questions, so warming one warms the other.
"""

from commands import inbox, review
from core import comments, model, output, progress, state


def _wanted(args):
    review_on = bool(getattr(args, "review", False) or getattr(args, "deep", False))
    report_on = bool(getattr(args, "report", False))
    pages_on = bool(getattr(args, "pages", False))
    inbox_on = bool(getattr(args, "inbox", False))
    if not (review_on or report_on or inbox_on or pages_on):
        return {"review": True, "pages": True, "report": True, "inbox": True}
    return {"review": review_on, "pages": pages_on, "report": report_on, "inbox": inbox_on}


def _warm_pages(cfg):
    from core import page_summaries, pages, window as window_core
    window = window_core.resolve(cfg, None, default_start=None, projects=[])
    collected = []
    for ws in cfg.get("_workstreams") or []:
        collected.extend(pages.gather(cfg, ws, window=window))
    from core import registers
    found, _skip = registers.gather(cfg, window, {})
    for record in found:
        collected.extend(record.get("entries") or [])
    print(f"Summarising {len(collected)} page(s) ...")
    page_summaries.fill(cfg, collected)


def _prepare_report(cfg, author):
    """The same gather `pm report` does for one shape, without writing a file."""
    from commands import report as report_cmd
    from core import products as product_core
    from core import registers
    from core import window as window_core
    state_path = output.place(
        cfg, cfg["output"].get("state_file", "report_state.json"), None)
    previous = state.load_state(state_path)
    window = window_core.resolve(cfg, None, default_start=None, projects=[])
    found_registers, skip_ids = registers.gather(cfg, window, previous)
    prepared = []
    streams = cfg["_workstreams"]
    for index, ws in enumerate(streams, 1):
        label = progress.numbered(index, len(streams), f"{ws['name']} ({ws['abbrev']})")
        row = report_cmd.prepare(
            cfg, ws, previous, window, skip_ids=skip_ids,
            progress_label=label, author=author)
        row["registers"] = found_registers
        report_cmd.stamp_register_entries(row)
        prepared.append((ws, row))
    groups = product_core.group_workstreams(cfg, [ws for ws, _row in prepared])
    if report_cmd._will_read_product_pages(cfg):
        progress.start("Reading product pages")
    report_cmd._attach_product_pages(cfg, groups, prepared, window, skip_ids)
    return prepared, groups


def _infer_sections(cfg, prepared, names, section_roles):
    from commands import report as report_cmd
    sections = []
    if not prepared or not section_roles:
        return [(ws, "") for ws, _row in prepared]
    model.announce(cfg["model"], len(prepared), "pm warm report")
    for ws, row in prepared:
        model.tick(cfg["model"], ws["abbrev"])
        body = model.infer_report_section(
            cfg["model"], cfg["output"]["audience"],
            ws, row["items"], row["change_block"],
            comment_budget=comments.settings(cfg)["section_chars"],
            cfg=cfg, material=report_cmd.section_material(cfg, row, names=names),
            section_roles=section_roles)
        sections.append((ws, body))
    return sections


def _warm_report(cfg, levels):
    """Cache the same section prompt `pm report` will send for each profile."""
    from commands import report as report_cmd
    from core import report_profiles
    prepared_by_names = {}

    def prepared_for(names):
        if names not in prepared_by_names:
            prepared_by_names[names] = _prepare_report(cfg, author=names)
        return prepared_by_names[names]

    cached = {}
    profiles = []
    for level in levels:
        if level not in report_profiles.PROFILES:
            raise SystemExit(
                f"Unknown audience {level}. Use {', '.join(report_profiles.known())}.")
        profiles.append(report_profiles.get(level))
    for profile in profiles:
        roles = report_profiles.sections(profile["id"])
        names = report_profiles.names_people(profile["id"])
        key = (names, roles)
        if not roles or key in cached:
            continue
        prepared, groups = prepared_for(names)
        cached[key] = (prepared, groups, _infer_sections(cfg, prepared, names, roles))
    for profile in profiles:
        if profile["id"] not in ("leadership", "partner"):
            continue
        names = False
        roles = report_profiles.sections(profile["id"])
        if (names, roles) in cached:
            prepared, groups, sections = cached[(names, roles)]
        else:
            prepared, groups = prepared_for(names)
            sections = [(ws, "") for ws, _row in prepared]
        report_cmd._audience_summaries(
            cfg, groups, prepared, sections, profile["privacy"])


def _warm_inbox(cfg):
    store = inbox._load(cfg)
    notes = [n for n in store.get("notes") or [] if not n.get("dropped")]
    if not notes:
        print("Inbox is empty.")
        return
    model.announce(cfg["model"], len(notes), "pm warm inbox")
    for note in notes:
        model.tick(cfg["model"], f"note {note['n']}")
        inbox._suggest(cfg, note)


def run(cfg, args):
    wanted = _wanted(args)
    if wanted["review"]:
        print("Warming review (this also covers pm ready --deep) ...")
        review.evaluate(cfg, ["titles", "criteria"])
    if wanted.get("pages"):
        print("Warming page summaries ...")
        _warm_pages(cfg)
    if wanted["report"]:
        from core import audience
        raw = getattr(args, "audience", None)
        if raw:
            levels = [part.strip() for part in str(raw).split(",") if part.strip()]
        else:
            levels = list(audience.settings(cfg)["warm"] or ["pm"])
        print("Warming report ...")
        _warm_report(cfg, levels)
    if wanted["inbox"]:
        print("Warming inbox ...")
        _warm_inbox(cfg)
    calls = int((cfg.get("model") or {}).get("_calls") or 0)
    hits = int((cfg.get("model") or {}).get("_cache_hits") or 0)
    print(f"\nCache warm. {calls} model call(s), {hits} already cached.")
