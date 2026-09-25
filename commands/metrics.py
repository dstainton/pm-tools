"""`pm metrics` — portfolio health from the changelog.

Deterministic. No model. Per product and workstream: throughput, cycle time,
aging work in progress, sprint scope change, forecast accuracy, and a plain
landing date at the current rate.
"""

import datetime as dt
import json
import sys

from core import metrics as core
from core import output
from core import products as product_core
from core import progress, sources, statuses, workstreams


def _history(cfg, project, jql):
    issues = sources.fetch_jira_history(cfg["jira"], jql) if jql else []
    index, _detail = statuses.load_index(cfg["jira"], project)
    return statuses.annotate(issues, index)


def settings(cfg, args):
    block = cfg.get("metrics") if isinstance(cfg.get("metrics"), dict) else {}
    weeks = getattr(args, "weeks", None)
    if weeks is None:
        weeks = block.get("weeks", 8)
    return {"weeks": max(1, int(weeks or 8))}


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


def _fmt_date(value):
    if not value:
        return "—"
    if isinstance(value, dt.datetime):
        value = value.date()
    if not isinstance(value, dt.date):
        try:
            value = dt.date.fromisoformat(str(value)[:10])
        except ValueError:
            return str(value)
    if value.year != dt.date.today().year:
        return value.strftime(f"{value.day} %b %Y")
    return value.strftime(f"{value.day} %b")


def render(groups, weeks):
    lines = [
        f"# Delivery metrics",
        f"_Last {weeks} week{'s' if weeks != 1 else ''}. Facts from the "
        f"changelog — no model._",
        "",
    ]
    for product, rows in groups:
        lines.append(f"## {product.get('name')} ({product.get('abbrev')})")
        lines.append("")
        lines.append("| Workstream | Done / week | Cycle (med / p85) | "
                     "Open | Landing | Scope added | Forecast pts |")
        lines.append("|-----------|------------:|------------------:|----:|"
                     "--------:|------------:|-------------:|")
        for row in rows:
            cycle = row["cycle"]
            cycle_txt = ("—" if not cycle["n"]
                         else f"{cycle['median']} / {cycle['p85']} d")
            rate = f"{row['weekly_rate']:.1f}"
            landing = _fmt_date(row.get("landing"))
            added = row["scope_change"]["added"]
            acc = row["accuracy"]
            forecast = f"{acc['done']:.0f} / {acc['forecast']:.0f}"
            lines.append(
                f"| {row['workstream']} | {rate} | {cycle_txt} | "
                f"{row['open']} | {landing} | {added} | {forecast} |")
        lines.append("")
        for row in rows:
            if not row["aging"]:
                continue
            lines.append(f"Aging in {row['workstream']} "
                         f"({len(row['aging'])} of {row['aging_total']})")
            for item in row["aging"]:
                lines.append(
                    f"  {item['key']:<8} {item['status']} {item['age']} days  "
                    f"{item['summary']}")
            lines.append("")
        weeks_row = rows[0]["throughput"] if rows else []
        if weeks_row:
            lines.append("Throughput by week")
            header = "| Week | " + " | ".join(r["workstream"] for r in rows) + " |"
            lines.append(header)
            lines.append("|------|" + "|".join(["------:"] * len(rows)) + "|")
            for i, bucket in enumerate(weeks_row):
                cells = [bucket["week"]]
                for row in rows:
                    cells.append(str(row["throughput"][i]["done"]))
                lines.append("| " + " | ".join(cells) + " |")
            lines.append("")
    return "\n".join(lines)


def render_headline(groups, weeks):
    """Leadership delivery table: rate, cycle, open, and landing."""
    lines = ["## Delivery", ""]
    for product, rows in groups:
        lines.append(f"### {product.get('name')} ({product.get('abbrev')})")
        lines.append("")
        lines.append("| Workstream | Done / week | Cycle (median) | Open | Landing |")
        lines.append("|------------|------------:|---------------:|-----:|---------|")
        for row in rows:
            cycle = row["cycle"]
            cycle_txt = "—" if not cycle["n"] else f"{cycle['median']} d"
            landing = _fmt_date(row.get("landing"))
            lines.append(
                f"| {row['workstream']} | {row['weekly_rate']:.1f} | {cycle_txt} | "
                f"{row['open']} | {landing} |")
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
            snap["workstream"] = ws.get("abbrev")
            rows.append(snap)
        out.append((product, rows))
    return sprint_name, out


def render_sprint(sprint_name, groups):
    title = sprint_name or "Open sprint"
    lines = [
        f"# {title}",
        "_Open sprint. Forecast at the start, points done, points added "
        "after the start, and items carried in. Facts from the changelog._",
        "",
    ]
    any_sprint = False
    for product, rows in groups:
        lines.append(f"## {product.get('name')} ({product.get('abbrev')})")
        lines.append("")
        lines.append("| Workstream | Forecast at start | Points done | "
                     "Points added | Carried in |")
        lines.append("|-----------|------------------:|------------:|"
                     "-------------:|-----------:|")
        for row in rows:
            if row.get("forecast") is None:
                lines.append(f"| {row['workstream']} | — | — | — | — |")
                continue
            any_sprint = True
            lines.append(
                f"| {row['workstream']} | {row['forecast']:.0f} | "
                f"{row['done']:.0f} | {row['added_points']:.0f} | "
                f"{row['carried']} |")
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
    text = render_sprint(sprint_name, groups)
    path = output.place(
        cfg, f"sprint_metrics_{dt.date.today().isoformat()}.md",
        getattr(args, "out", None))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text)
    print(f"\nDone. Sprint metrics written to: {path}")


def run(cfg, args):
    from core import audience
    who = audience.level(cfg, args)
    if who == "partner":
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
    text = render_headline(groups, opts["weeks"]) if who == "leadership" else render(groups, opts["weeks"])
    path = output.place(
        cfg, f"metrics_{dt.date.today().isoformat()}.md",
        getattr(args, "out", None))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text)
    print(f"\nDone. Metrics written to: {path}")
