"""`pm standup` — a quick daily movement snapshot.

Answers the two questions a standup actually needs, per workstream:

  * What MOVED since yesterday?  (status transitions from the Jira changelog:
    "To Do -> In Progress", "In Review -> Done", and so on)
  * What is IN PROGRESS right now, and who owns it?

No model needed — this is all facts straight from Jira, so it is fast and
trustworthy. Run it a few minutes before standup.

  pm standup                    Yesterday's movement + today's WIP.
  pm standup --days 3           Widen the "moved" window (e.g. after a weekend).
  pm standup --by workstream    Group WIP by workstream instead of by owner.
  pm standup --print            Also echo the snapshot to the terminal.

Scope it like any command:  pm standup --workstream SDX

What counts as "moved" and "in progress" comes from the `standup_moved` and
`standup_wip` scopes in config — plain options, no JQL. --days overrides the
movement window for one run.
"""

import datetime as dt

from core import sources, workstreams


def _fmt_when(when):
    """A friendly 'today 09:12' / 'Mon 14:03' style stamp."""
    now = dt.datetime.now(dt.timezone.utc)
    local = when.astimezone()
    if when.date() == now.date():
        return f"today {local:%H:%M}"
    if (now.date() - when.date()).days == 1:
        return f"yesterday {local:%H:%M}"
    return f"{local:%a %H:%M}"


def _moved_jql(cfg, ws, days):
    """Resolve the workstream scope for recent movement."""
    return workstreams.scope_jql(cfg, ws, "standup_moved", days=days)


def build_markdown(cfg, results, days, group_by):
    today = dt.date.today().isoformat()
    window = "since yesterday" if days == 1 else f"in the last {days} days"
    lines = [
        "# Daily Standup",
        f"_Movement {window}, and work in progress now. "
        f"Generated {today} — facts from Jira, no model._",
        "",
    ]

    # Summary line across workstreams.
    lines.append("## Summary")
    lines.append("")
    lines.append("| Workstream | Moved | In progress |")
    lines.append("|-----------|------:|------------:|")
    tot_moved = tot_wip = 0
    for ws, moved, wip in results:
        lines.append(f"| {ws['abbrev']} | {len(moved)} | {len(wip)} |")
        tot_moved += len(moved)
        tot_wip += len(wip)
    lines.append(f"| **Total** | **{tot_moved}** | **{tot_wip}** |")
    lines.append("")

    for ws, moved, wip in results:
        lines.append(f"## {ws['name']} ({ws['abbrev']})")
        lines.append("")

        # --- What moved ---------------------------------------------------
        lines.append(f"### Moved {window}")
        lines.append("")
        if not moved:
            lines.append("_No status changes._")
        else:
            for m in moved:
                last = m["transitions"][-1]
                # If several hops happened, show first-from -> last-to.
                first_from = m["transitions"][0]["from"]
                to = last["to"]
                arrow = f"{first_from} → {to}"
                who = f" by {last['who']}" if last["who"] else ""
                when = _fmt_when(last["when"])
                lines.append(
                    f"- **[{m['key']}]({m['url']})** {sources.short(m['summary'], 80)} "
                    f"— {arrow}{who} ({when})")
        lines.append("")

        # --- In progress now ----------------------------------------------
        lines.append("### In progress now")
        lines.append("")
        if not wip:
            lines.append("_Nothing in progress._")
            lines.append("")
            continue

        if group_by == "workstream":
            for c in wip:
                lines.append(
                    f"- **[{c['key']}]({c['url']})** "
                    f"{sources.short(c['summary'], 80)} — {c['assignee']}")
        else:  # group by assignee (default)
            by_person = {}
            for c in wip:
                by_person.setdefault(c["assignee"], []).append(c)
            for person in sorted(by_person):
                lines.append(f"**{person}**")
                for c in by_person[person]:
                    lines.append(
                        f"- [{c['key']}]({c['url']}) "
                        f"{sources.short(c['summary'], 80)}")
                lines.append("")
        lines.append("")

    return "\n".join(lines)


def run(cfg, args):
    days = getattr(args, "days", 1)
    group_by = getattr(args, "by", "assignee")

    results = []
    for ws in cfg["_workstreams"]:
        print(f"Standup: {ws['name']} ({ws['abbrev']}) ...")

        moved_jql = _moved_jql(cfg, ws, days)
        wip_jql = workstreams.scope_jql(cfg, ws, "standup_wip")

        moved = sources.fetch_jira_changelog(cfg["jira"], moved_jql, days) \
            if moved_jql else []
        wip = sources.fetch_jira_cards(cfg["jira"], wip_jql) if wip_jql else []

        print(f"  {len(moved)} moved, {len(wip)} in progress.")
        results.append((ws, moved, wip))

    report = build_markdown(cfg, results, days, group_by)
    out_path = f"standup_{dt.date.today().isoformat()}.md"
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"\nDone. Standup written to: {out_path}")

    if getattr(args, "print", False):
        print("\n" + "=" * 60 + "\n")
        print(report)
