"""`pm metrics` — portfolio health from the changelog.

Deterministic. No model. Per product and workstream: throughput, cycle time,
aging work in progress, sprint scope change, forecast accuracy, and a plain
landing date at the current rate.
"""

import datetime as dt
import json

from core import metrics as core
from core import products as product_core
from core import sources, workstreams


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
    for product, group in groups:
        product_rows = []
        for ws in group:
            project = workstreams.project_of(cfg, ws)
            if project and project not in seen_projects:
                seen_projects[project] = sources.fetch_active_sprints(
                    cfg["jira"], project)
            jql = workstreams.scope_jql(
                cfg, ws, "lint", overrides={"status": "any", "sprint": "any"})
            issues = (sources.fetch_jira_history(cfg["jira"], jql)
                      if jql else [])
            bundle = core.summarise_stream(
                issues, weeks, sprints=seen_projects.get(project) or [],
                today=today)
            bundle["workstream"] = ws.get("abbrev")
            bundle["workstream_name"] = ws.get("name")
            product_rows.append(bundle)
        out.append((product, product_rows))
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


def as_json(groups, weeks):
    payload = {"weeks": weeks, "products": []}
    for product, rows in groups:
        payload["products"].append({
            "abbrev": product.get("abbrev"),
            "name": product.get("name"),
            "workstreams": rows,
        })
    return payload


def run(cfg, args):
    opts = settings(cfg, args)
    print(f"Measuring the last {opts['weeks']} weeks ...")
    groups = gather(cfg, opts["weeks"])
    if getattr(args, "json", False):
        path = f"metrics_{dt.date.today().isoformat()}.json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(as_json(groups, opts["weeks"]), fh, indent=2, default=str)
        print(f"\nDone. Metrics written to: {path}")
        return
    text = render(groups, opts["weeks"])
    path = f"metrics_{dt.date.today().isoformat()}.md"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text)
    print(f"\nDone. Metrics written to: {path}")
