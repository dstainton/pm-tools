"""`pm metrics` — portfolio health from the changelog.

Deterministic. No inference model used. Per product and workstream: throughput,
story points, cycle time, aging work in progress, sprint scope change,
forecast accuracy, and a landing range from the weekly rate.
"""

import datetime as dt
import json
import sys

from core import fiscal
from core import metrics as core
from core import output
from core import products as product_core
from core import progress, render as render_core, sources, statuses, terminal, workstreams


def _history(cfg, project, jql):
    issues = sources.fetch_jira_history(cfg["jira"], jql) if jql else []
    index, _detail = statuses.load_index(cfg["jira"], project)
    return statuses.annotate(issues, index)


def year_end_of(cfg):
    """The configured month-day, or 31 March."""
    block = cfg.get("metrics") if isinstance(cfg.get("metrics"), dict) else {}
    return fiscal.canonical(block.get("year_end") or "03-31")


def settings(cfg, args=None):
    block = cfg.get("metrics") if isinstance(cfg.get("metrics"), dict) else {}
    weeks = getattr(args, "weeks", None) if args is not None else None
    if weeks is None:
        weeks = block.get("weeks", 8)
    return {"weeks": max(1, int(weeks or 8)), "year_end": year_end_of(cfg)}


def gather(cfg, weeks, today=None):
    today = today or dt.date.today()
    streams = cfg.get("_workstreams") or []
    groups = product_core.group_workstreams(cfg, streams)
    out = []
    seen_projects = {}
    seen = 0
    for product, group in groups:
        product_rows = []
        for ws in group:
            seen += 1
            progress.start(progress.numbered(
                seen, len(streams),
                f"Measuring {ws.get('name')} ({ws.get('abbrev')})"))
            project = workstreams.project_of(cfg, ws)
            if project and project not in seen_projects:
                seen_projects[project] = sources.fetch_active_sprints(
                    cfg["jira"], project)
            jql = workstreams.scope_jql(
                cfg, ws, "lint", overrides={"status": "any", "sprint": "any"})
            issues = _history(cfg, project, jql)
            bundle = core.summarise_stream(
                issues, weeks, sprints=seen_projects.get(project) or [],
                today=today,
                epic_types=workstreams.membership_settings(cfg)["epic_types"])
            bundle["workstream"] = ws.get("abbrev")
            bundle["workstream_name"] = ws.get("name")
            product_rows.append(bundle)
        out.append((product, product_rows))
    progress.finish()
    return out


def _as_date(value):
    if not value:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _fmt_date(value, today=None):
    today = today or dt.date.today()
    value = _as_date(value)
    if not value:
        return "—"
    return fiscal.format_day(value, with_year=value.year != today.year)


def _fmt_pair(early, late, today):
    """Two dates. The year is shown when the pair is not entirely in `today`'s year."""
    show_year = (early.year != late.year or early.year != today.year
                 or late.year != today.year)
    return (f"{fiscal.format_day(early, with_year=show_year)} – "
            f"{fiscal.format_day(late, with_year=show_year)}")


def _landing_cell(row, year_end, today):
    """A date range, with the fiscal quarter each end falls in."""
    span = row.get("landing")
    if not span:
        return "—"
    if isinstance(span, (dt.date, dt.datetime, str)):
        early = _as_date(span)
        late = early
        open_ended = False
    else:
        early = _as_date(span.get("early"))
        late = _as_date(span.get("late"))
        open_ended = bool(span.get("open_ended"))
    if not early:
        return "—"
    if open_ended or late is None:
        text = f"{_fmt_date(early, today)} or later"
        ref = fiscal.span_label(early, early, year_end)
    elif late == early:
        text = _fmt_date(early, today)
        ref = fiscal.span_label(early, early, year_end)
    else:
        text = _fmt_pair(early, late, today)
        ref = fiscal.span_label(early, late, year_end)
    return f"{text} ({ref})"


def _window_start(groups, weeks, today):
    for _product, rows in groups:
        for row in rows:
            buckets = row.get("throughput") or []
            if buckets and buckets[0].get("start"):
                found = _as_date(buckets[0]["start"])
                if found:
                    return found
    return core.week_start(today) - dt.timedelta(weeks=max(weeks, 1) - 1)


def _facts_line(groups, weeks, year_end, today):
    start = _window_start(groups, weeks, today)
    ref = fiscal.span_label(start, today, year_end)
    noun = "week" if weeks == 1 else "weeks"
    return (f"_Last {weeks} {noun} ({ref}). "
            f"Facts from the changelog — no inference model used._")


def _fiscal_line(year_end, today):
    close = fiscal.next_year_end(today, year_end)
    period = fiscal.period_containing(today, year_end)
    ended = fiscal.format_day(close, with_year=True)
    return (f"_FY{close.year} ends {ended}. "
            f"This quarter is {fiscal.period_phrase(period)}._")


def _landing_note():
    return ("_Landing is the weekly rate, one standard deviation faster and "
            "slower. It is a projection, not a commitment. "
            "It is shown after three items finish in the window._")


def render(groups, weeks, year_end="03-31", today=None):
    today = today or dt.date.today()
    year_end = fiscal.canonical(year_end)
    lines = [
        "# Delivery metrics",
        _facts_line(groups, weeks, year_end, today),
        _fiscal_line(year_end, today),
        _landing_note(),
        "",
    ]
    for product, rows in groups:
        lines.append(f"## {product.get('name')} ({product.get('abbrev')})")
        lines.append("")
        lines.append("| Workstream | Done / week | Points / week | "
                     "Cycle (med / p85) | Open | Open pts | Landing | "
                     "Scope added | Forecast pts |")
        lines.append("|-----------|------------:|--------------:|"
                     "------------------:|-----:|---------:|--------:|"
                     "------------:|-------------:|")
        for row in rows:
            cycle = row["cycle"]
            cycle_txt = ("—" if not cycle["n"]
                         else f"{cycle['median']} / {cycle['p85']} d")
            rate = f"{row['weekly_rate']:.1f}"
            points = f"{row.get('weekly_points') or 0:.1f}"
            landing = _landing_cell(row, year_end, today)
            added = row["scope_change"]["added"]
            acc = row["accuracy"]
            forecast = f"{acc['done']:.0f} / {acc['forecast']:.0f}"
            lines.append(
                f"| {row['workstream']} | {rate} | {points} | {cycle_txt} | "
                f"{row['open']} | {row.get('open_points') or 0:.0f} | "
                f"{landing} | {added} | {forecast} |")
        lines.append("")
        for row in rows:
            if not row["aging"]:
                continue
            lines.append(f"Aging in {row['workstream']} "
                         f"({len(row['aging'])} of {row['aging_total']})")
            lines.append("")
            for item in row["aging"]:
                key = render_core.markdown_link(item["key"], item.get("url"))
                lines.append(
                    f"- {key} {item['status']}, {item['age']} days — "
                    f"{item['summary']}")
            lines.append("")
        weeks_row = rows[0]["throughput"] if rows else []
        if weeks_row:
            lines.append("Throughput by week")
            names = []
            for row in rows:
                names.append(row["workstream"])
                names.append(f"{row['workstream']} pts")
            header = "| Week | Quarter | " + " | ".join(names) + " |"
            lines.append(header)
            lines.append("|------|---------|" + "|".join(["------:"] * len(names)) + "|")
            for i, bucket in enumerate(weeks_row):
                day = _as_date(bucket.get("end")) or _as_date(bucket.get("start")) or today
                cells = [bucket["week"], fiscal.period_label(
                    fiscal.period_containing(day, year_end))]
                for row in rows:
                    cells.append(str(row["throughput"][i]["done"]))
                    cells.append(f"{row['throughput'][i].get('points') or 0:.0f}")
                lines.append("| " + " | ".join(cells) + " |")
            lines.append("")
    return "\n".join(lines)


def render_headline(groups, weeks, year_end="03-31", today=None):
    """Leadership delivery table: rate, points, cycle, open, and a projection."""
    today = today or dt.date.today()
    year_end = fiscal.canonical(year_end)
    lines = ["## Delivery", ""]
    lines.append(_fiscal_line(year_end, today))
    lines.append(_landing_note())
    lines.append("")
    for product, rows in groups:
        lines.append(f"### {product.get('name')} ({product.get('abbrev')})")
        lines.append("")
        lines.append("| Workstream | Done / week | Points / week | "
                     "Cycle (median) | Open | Open pts | "
                     "Landing (projection) |")
        lines.append("|------------|------------:|--------------:|"
                     "---------------:|-----:|---------:|"
                     "----------------------|")
        for row in rows:
            cycle = row["cycle"]
            cycle_txt = "—" if not cycle["n"] else f"{cycle['median']} d"
            landing = _landing_cell(row, year_end, today)
            lines.append(
                f"| {row['workstream']} | {row['weekly_rate']:.1f} | "
                f"{row.get('weekly_points') or 0:.1f} | {cycle_txt} | "
                f"{row['open']} | {row.get('open_points') or 0:.0f} | {landing} |")
        lines.append("")
    return "\n".join(lines)


def render_pulse(groups, weeks, year_end="03-31", today=None):
    """Short delivery note for a report. Full tables stay on `pm metrics`."""
    today = today or dt.date.today()
    year_end = fiscal.canonical(year_end)
    lines = [
        "## Delivery pulse",
        "",
        "_Done per week, story points per week, median cycle time, and open count. "
        "A landing range is the weekly rate, one standard deviation either side, "
        "not a commitment. "
        "Full detail: `pm metrics`._",
        "",
        _fiscal_line(year_end, today),
        "",
    ]
    lines.append("| Workstream | Done / week | Points / week | "
                 "Cycle (median) | Open | Open pts | Landing (projection) |")
    lines.append("|------------|------------:|--------------:|"
                 "---------------:|-----:|---------:|----------------------|")
    for _product, rows in groups:
        for row in rows:
            cycle = row["cycle"]
            cycle_txt = "—" if not cycle["n"] else f"{cycle['median']} d"
            landing = _landing_cell(row, year_end, today)
            lines.append(
                f"| {row['workstream']} | {row['weekly_rate']:.1f} | "
                f"{row.get('weekly_points') or 0:.1f} | {cycle_txt} | "
                f"{row['open']} | {row.get('open_points') or 0:.0f} | {landing} |")
    lines.append("")
    return "\n".join(lines)


def _sprint_fiscal_line(groups, year_end):
    start = end = None
    for _product, rows in groups:
        for row in rows:
            found = _as_date(row.get("start"))
            finish = _as_date(row.get("end"))
            if found and (start is None or found < start):
                start = found
            if finish and (end is None or finish > end):
                end = finish
    if not start:
        return ""
    ref = fiscal.span_label(start, end or start, year_end)
    return f"_{ref}._"


def render_sprint_context(sprint_name, groups, year_end="03-31"):
    """Sprint delivery for a developer report. No portfolio forecast."""
    year_end = fiscal.canonical(year_end)
    lines = ["## This sprint", ""]
    if sprint_name:
        lines.append(f"_{sprint_name}_")
        lines.append("")
    fiscal_line = _sprint_fiscal_line(groups, year_end)
    if fiscal_line:
        lines.append(fiscal_line)
        lines.append("")
    lines.append("| Workstream | Forecast at start | Delivered | Added | "
                 "Carried in | Unfinished |")
    lines.append("|-----------|------------------:|----------:|------:|"
                 "-----------:|-----------:|")
    any_sprint = False
    for _product, rows in groups:
        for row in rows:
            if row.get("forecast") is None:
                lines.append(f"| {row.get('workstream')} | — | — | — | — | — |")
                continue
            any_sprint = True
            unfinished = len(row.get("unfinished") or [])
            lines.append(
                f"| {row.get('workstream')} | {row['forecast']:.0f} | "
                f"{row['done']:.0f} | {row['added_points']:.0f} | "
                f"{row['carried']} | {unfinished} |")
    lines.append("")
    if not any_sprint:
        lines.append("_No open sprint._")
        lines.append("")
    lines.append("Sprint review: `pm metrics --sprint`. Full history: `pm metrics`.")
    lines.append("")
    return "\n".join(lines)


def as_json(groups, weeks):
    payload = {"weeks": weeks, "products": []}
    for product, rows in groups:
        payload["products"].append({
            "abbrev": product.get("abbrev"),
            "name": product.get("name"),
            "workstreams": rows,
        })
    return payload


def gather_sprint(cfg):
    """One row per workstream for the project's open sprint."""
    streams = cfg.get("_workstreams") or []
    groups = product_core.group_workstreams(cfg, streams)
    seen = {}
    out = []
    sprint_name = ""
    for product, group in groups:
        rows = []
        for ws in group:
            project = workstreams.project_of(cfg, ws)
            if project not in seen:
                sprints = (sources.fetch_active_sprints(cfg["jira"], project)
                           if project else [])
                seen[project] = sprints[0] if sprints else None
            sprint = seen.get(project)
            if sprint and not sprint_name:
                sprint_name = sprint.get("name") or ""
            if not sprint:
                rows.append({
                    "workstream": ws.get("abbrev"),
                    "name": "",
                    "forecast": None,
                })
                continue
            jql = workstreams.scope_jql(
                cfg, ws, "lint",
                overrides={"status": "any", "sprint": "open"})
            issues = _history(cfg, project, jql)
            snap = core.sprint_snapshot(issues, sprint)
            snap["goal"] = (sprint.get("goal") or "").strip()
            snap["workstream"] = ws.get("abbrev")
            rows.append(snap)
        out.append((product, rows))
    return sprint_name, out


def _sprint_cards(rows, field, limit=12):
    cards = []
    for row in rows:
        for card in row.get(field) or []:
            cards.append(card)
    return cards[:limit], len(cards)


def _card_ref(card):
    return render_core.markdown_link(card.get("key"), card.get("url"))


def render_sprint(sprint_name, groups, cfg=None, year_end=None):
    """Sprint review: goal, forecast, what finished, and what did not."""
    if year_end is None and isinstance(cfg, dict):
        try:
            year_end = year_end_of(cfg)
        except ValueError:
            year_end = "03-31"
    year_end = fiscal.canonical(year_end or "03-31")
    title = sprint_name or "Open sprint"
    goal = ""
    for _product, rows in groups:
        for row in rows:
            if row.get("goal"):
                goal = row["goal"]
                break
        if goal:
            break
    lines = [
        f"# {title}",
        "_Sprint review. Forecast, delivered, and added figures are story points. "
        "Facts from the changelog — no inference model used. "
        "A forecast is not a commitment._",
        "",
    ]
    fiscal_line = _sprint_fiscal_line(groups, year_end)
    if fiscal_line:
        lines.append(fiscal_line)
        lines.append("")
    if goal:
        lines.append(f"Sprint Goal: {goal}")
        lines.append("")
    any_sprint = False
    for product, rows in groups:
        lines.append(f"## {product.get('name')} ({product.get('abbrev')})")
        lines.append("")
        lines.append("| Workstream | Forecast at start | Delivered | "
                     "Added after start | Carried in | Carried out |")
        lines.append("|-----------|------------------:|----------:|"
                     "------------------:|-----------:|------------:|")
        for row in rows:
            if row.get("forecast") is None:
                lines.append(f"| {row['workstream']} | — | — | — | — | — |")
                continue
            any_sprint = True
            lines.append(
                f"| {row['workstream']} | {row['forecast']:.0f} | "
                f"{row['done']:.0f} | {row['added_points']:.0f} | "
                f"{row['carried']} | {len(row.get('carried_out') or [])} |")
        lines.append("")
        epics = []
        for row in rows:
            for epic in row.get("epics") or []:
                if epic not in epics:
                    epics.append(epic)
        if epics:
            sample = next((card.get("url") for row in rows
                           for card in (row.get("completed") or []) if card.get("url")), "")
            lines.append("Epics advanced")
            lines.append("")
            for epic in epics:
                lines.append(f"- {render_core.markdown_link(epic, render_core.browse_url(cfg, epic, sample))}")
            lines.append("")
        done_cards, done_n = _sprint_cards(rows, "completed")
        open_cards, open_n = _sprint_cards(rows, "unfinished")
        if done_cards:
            lines.append(f"Completed ({done_n})")
            lines.append("")
            for card in done_cards:
                lines.append(f"- {_card_ref(card)} {card.get('summary') or ''}".rstrip())
            if done_n > len(done_cards):
                lines.append(f"- {done_n - len(done_cards)} more")
            lines.append("")
        if open_cards:
            lines.append(f"Incomplete ({open_n})")
            lines.append("")
            for card in open_cards:
                lines.append(f"- {_card_ref(card)} {card.get('summary') or ''}".rstrip())
            if open_n > len(open_cards):
                lines.append(f"- {open_n - len(open_cards)} more")
            lines.append("")
        if cfg is not None:
            from core import checklist
            items = checklist.definition_items(cfg, product)
            if items:
                lines.append("Definition of Done")
                lines.append("")
                for item in items:
                    lines.append(f"- {item.get('text')}")
                lines.append("")
    if not any_sprint:
        lines.append("_No open sprint._")
        lines.append("")
    return "\n".join(lines)


def run_sprint(cfg, args):
    print("Measuring the open sprint ...")
    sprint_name, groups = gather_sprint(cfg)
    if getattr(args, "json", False):
        payload = {"sprint": sprint_name, "products": []}
        for product, rows in groups:
            payload["products"].append({
                "abbrev": product.get("abbrev"),
                "name": product.get("name"),
                "workstreams": rows,
            })
        path = output.place(
            cfg, f"sprint_metrics_{dt.date.today().isoformat()}.json",
            getattr(args, "out", None))
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, default=str)
        print(f"\nDone. Sprint metrics written to: {path}")
        return
    text = render_sprint(sprint_name, groups, cfg=cfg, year_end=year_end_of(cfg))
    path = output.place(
        cfg, f"sprint_metrics_{dt.date.today().isoformat()}.md",
        getattr(args, "out", None))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    terminal.show(text, args)
    print(f"\nDone. Sprint metrics written to: {path}")


def run(cfg, args):
    from core import report_profiles
    profile_id = report_profiles.resolve(cfg, args)
    privacy = report_profiles.privacy(profile_id)
    who = privacy
    if privacy == "partner":
        sys.exit("pm metrics has no partner view.")
    if getattr(args, "sprint", False):
        run_sprint(cfg, args)
        return
    opts = settings(cfg, args)
    print(f"Measuring the last {opts['weeks']} weeks ...")
    groups = gather(cfg, opts["weeks"])
    if getattr(args, "json", False):
        path = output.place(
            cfg, f"metrics_{dt.date.today().isoformat()}.json",
            getattr(args, "out", None))
        payload = as_json(groups, opts["weeks"])
        payload["audience"] = who
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, default=str)
        print(f"\nDone. Metrics written to: {path}")
        return
    today = dt.date.today()
    if who == "leadership":
        text = render_headline(
            groups, opts["weeks"], year_end=opts["year_end"], today=today)
    else:
        text = render(groups, opts["weeks"], year_end=opts["year_end"], today=today)
    path = output.place(
        cfg, f"metrics_{dt.date.today().isoformat()}.md",
        getattr(args, "out", None))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    terminal.show(text, args)
    print(f"\nDone. Metrics written to: {path}")
