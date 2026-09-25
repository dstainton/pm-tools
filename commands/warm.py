"""`pm warm` — fill the model cache before you need the answer.

Read-only. It writes no Jira, edits no config, and writes no report. The
only side effect is reply files under the model cache. Stop it whenever
you like: every reply already stored is kept, and the next run continues
from there.

`pm schedule add warm --at 07:00` runs it before you sit down. `pm review`
and `pm ready --deep` ask the same questions, so warming one warms the other.
"""

from commands import inbox, review
from core import comments, model, output, state


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
    print(f"Summarising {len(collected)} page(s) ...")
    page_summaries.fill(cfg, collected)


def _warm_report(cfg, levels):
    from commands import report as report_cmd
    from core import products as product_core
    state_path = output.place(
        cfg, cfg["output"].get("state_file", "report_state.json"), None)
    previous = state.load_state(state_path)
    prepared = []
    from core import window as window_core
    window = window_core.resolve(cfg, None, default_start=None, projects=[])
    for ws in cfg["_workstreams"]:
        print(f"Gathering: {ws['name']} ({ws['abbrev']}) ...")
        prepared.append((ws, report_cmd.prepare(cfg, ws, previous, window)))
    sections = []
    if "pm" in levels or "leadership" in levels:
        model.announce(cfg["model"], len(prepared), "pm warm report")
        for ws, row in prepared:
            model.tick(cfg["model"], ws["abbrev"])
            body = model.infer_report_section(
                cfg["model"], cfg["output"]["audience"],
                ws, row["items"], row["change_block"],
                comment_budget=comments.settings(cfg)["section_chars"],
                cfg=cfg)
            sections.append((ws, body))
    groups = product_core.group_workstreams(cfg, [ws for ws, _row in prepared])
    if "leadership" in levels and sections:
        report_cmd._audience_summaries(cfg, groups, prepared, sections, "leadership")
    if "partner" in levels:
        report_cmd._audience_summaries(cfg, groups, prepared, sections or [
            (ws, "") for ws, _row in prepared], "partner")


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
            bad = [part for part in levels if part not in audience.LEVELS]
            if bad:
                raise SystemExit(
                    f"Unknown audience {bad[0]}. Use {', '.join(audience.LEVELS)}.")
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
