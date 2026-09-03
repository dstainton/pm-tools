"""`pm today` — one bounded daily screen, and `pm do N` to act on it.

`pm today` is the habit command: a short list of things that need you, what
moved, what is aging, and the refinement gaps, grouped by product. Numbered
actions are written to `today.state_file` (default `~/.pm/today.json`) so
`pm do 3` still means what it meant when you walked away.

`pm do N` previews the payload, asks once (or honours `--yes` / `--dry-run`),
writes to Jira, and appends a line to the write log.
"""

import datetime as dt
import json
import os
import sys

from commands import lint, ready
from core import products as product_core
from core import sources, workstreams, writes


DEFAULT_STATE = "~/.pm/today.json"
DEFAULT_MAX_NEEDS = 5
DEFAULT_MAX_MOVED = 8
DEFAULT_MAX_AGING = 3
DEFAULT_UNTOUCHED = 3


# ---------------------------------------------------------------------------
#  Config + state
# ---------------------------------------------------------------------------

def settings(cfg):
    block = cfg.get("today") if isinstance(cfg.get("today"), dict) else {}
    return {
        "state_file": os.path.expanduser(block.get("state_file") or DEFAULT_STATE),
        "max_needs_you": int(block.get("max_needs_you", DEFAULT_MAX_NEEDS) or DEFAULT_MAX_NEEDS),
        "max_moved": int(block.get("max_moved", DEFAULT_MAX_MOVED) or DEFAULT_MAX_MOVED),
        "max_aging": int(block.get("max_aging", DEFAULT_MAX_AGING) or DEFAULT_MAX_AGING),
        "untouched_days": int(block.get("untouched_days", DEFAULT_UNTOUCHED)
                              or DEFAULT_UNTOUCHED),
    }


def load_actions(path):
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (ValueError, OSError):
        return None


def save_actions(path, payload):
    if not path:
        return
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)


# ---------------------------------------------------------------------------
#  Classification
# ---------------------------------------------------------------------------

def _parse_date(value):
    return lint.parse_date(value)


def _parse_datetime(value):
    return lint.parse_datetime(value)


def _age_days(issue):
    updated = _parse_datetime(issue.get("updated"))
    if not updated:
        return None
    return (dt.datetime.now(dt.timezone.utc) - updated).days


def _is_done(issue):
    return (issue.get("status_category") or "").lower() == "done"


def _is_in_progress(issue):
    return (issue.get("status_category") or "").lower() == "indeterminate"


def _is_unassigned(issue):
    name = (issue.get("assignee") or "").strip()
    return (not name) or name.lower() == "unassigned"


def _is_blocked(issue):
    status = (issue.get("status") or "").lower()
    if "blocked" in status:
        return True
    labels = [str(l).lower() for l in (issue.get("labels") or [])]
    return "blocked" in labels


def _is_overdue(issue, today=None):
    today = today or dt.date.today()
    due = _parse_date(issue.get("due_date"))
    return bool(due and due < today and not _is_done(issue))


def classify_need(issue, untouched_days, today=None):
    """Return the highest-priority need kind, or None.

    Priority: overdue, blocked, unassigned, untouched. Only open items
    qualify. `untouched` and `unassigned` apply to anything still open;
    the sprint filter is applied by the ready/today fetch scope.
    """
    if _is_done(issue):
        return None
    # Epics are containers, not a daily action. The child work is what needs you.
    if (issue.get("issuetype") or "").lower() == "epic":
        return None
    if _is_overdue(issue, today=today):
        return "overdue"
    if _is_blocked(issue):
        return "blocked"
    if _is_unassigned(issue):
        return "unassigned"
    age = _age_days(issue)
    if age is not None and age >= untouched_days:
        return "untouched"
    return None


def suggested_due(today=None):
    today = today or dt.date.today()
    return today + dt.timedelta(days=14)


def describe_action(kind, issue, today=None):
    """Human-facing `pm do N` line for one need kind."""
    if kind == "overdue":
        when = suggested_due(today)
        return f"set a realistic due date (suggests {when.day} {when.strftime('%b')})"
    if kind == "blocked":
        who = issue.get("assignee")
        if who and who != "Unassigned":
            return f"ask {who} for an ETA"
        return "ask whoever is closest to the work for an ETA"
    if kind == "unassigned":
        return "assign to yourself"
    if kind == "untouched":
        who = issue.get("assignee")
        if who and who != "Unassigned":
            return f"check in with {who}"
        return "check in on this item"
    return "review this item"


def preview_payload(kind, issue, today=None):
    """The Jira write `pm do` will send after one confirmation."""
    key = issue["key"]
    path = f"/rest/api/3/issue/{key}"
    if kind == "overdue":
        return {
            "method": "PUT",
            "path": path,
            "body": {"fields": {"duedate": suggested_due(today).isoformat()}},
        }
    if kind == "unassigned":
        return {
            "method": "PUT",
            "path": path,
            "body": {"fields": {"assignee": {"accountId": "(current user)"}}},
        }
    if kind == "blocked":
        return writes.action_comment(
            key, "Checking in — can we get an ETA on the blocker?",
            kind="blocked-nudge", summary=issue.get("summary") or key)
    if kind == "untouched":
        return writes.action_comment(
            key, "Checking in — still the plan for this Sprint?",
            kind="untouched-nudge", summary=issue.get("summary") or key)
    return {"method": "GET", "path": path, "body": None}


def need_tags(issue, kind):
    bits = [issue.get("issuetype") or "item"]
    if kind == "unassigned" or _is_unassigned(issue):
        bits.append("unassigned")
    if kind == "overdue" or _is_overdue(issue):
        due = _parse_date(issue.get("due_date"))
        if due:
            days = (dt.date.today() - due).days
            bits.append(f"due {days} day{'s' if days != 1 else ''} ago")
        else:
            bits.append("overdue")
    if kind == "blocked" or _is_blocked(issue):
        bits.append("blocked")
    if kind == "untouched":
        age = _age_days(issue)
        if age is not None:
            bits.append(f"untouched {age} days")
    return ", ".join(bits)


KIND_RANK = {"overdue": 0, "blocked": 1, "unassigned": 2, "untouched": 3}


# ---------------------------------------------------------------------------
#  Gathering
# ---------------------------------------------------------------------------

def _tag_issue(issue, ws, product):
    issue = dict(issue)
    issue["workstream"] = ws.get("abbrev")
    issue["workstream_name"] = ws.get("name")
    issue["product"] = product.get("abbrev")
    issue["product_name"] = product.get("name")
    return issue


def gather(cfg):
    """Fetch the facts `pm today` needs. Deterministic; no model."""
    opts = settings(cfg)
    lint_cfg = cfg.get("lint", {})
    ready_cfg = cfg.get("ready", {})
    blocking = set(ready_cfg.get("blocking_criteria",
                                 list(ready.CRITERION_RULES.keys())))
    stale_days = int(lint_cfg.get("stale_days", 14) or 14)
    days = int((cfg.get("standup") or {}).get("lookback_days", 1) or 1)

    streams = cfg.get("_workstreams") or cfg.get("workstreams") or []
    groups = product_core.group_workstreams(cfg, streams)

    open_items = []
    moved = []
    ready_gaps = []
    projects = []
    seen_projects = set()

    for product, group in groups:
        product_ready = {"ready": 0, "total": 0, "streams": []}
        for ws in group:
            project = workstreams.project_of(cfg, ws)
            if project and project not in seen_projects:
                seen_projects.add(project)
                projects.append(project)

            lint_jql = workstreams.scope_jql(cfg, ws, "lint")
            issues = (sources.fetch_jira_detailed(cfg["jira"], lint_jql)
                      if lint_jql else [])
            inherited = workstreams.uses_component_scope(cfg, ws)
            not_ready = 0
            for issue in issues:
                tagged = _tag_issue(issue, ws, product)
                open_items.append(tagged)
                verdict = ready.evaluate_issue(
                    issue, lint_cfg, blocking, None, inherited)
                if not verdict["ready"]:
                    not_ready += 1
            product_ready["ready"] += len(issues) - not_ready
            product_ready["total"] += len(issues)
            product_ready["streams"].append({
                "abbrev": ws.get("abbrev"),
                "name": ws.get("name"),
                "not_ready": not_ready,
                "total": len(issues),
            })

            moved_jql = workstreams.scope_jql(cfg, ws, "standup_moved", days=days)
            for card in (sources.fetch_jira_changelog(cfg["jira"], moved_jql, days)
                         if moved_jql else []):
                moved.append(_tag_issue(card, ws, product))

        ready_gaps.append((product, product_ready))

    sprints = []
    for project in projects:
        sprints.extend(sources.fetch_active_sprints(cfg["jira"], project))

    return {
        "open_items": open_items,
        "moved": moved,
        "ready_gaps": ready_gaps,
        "sprints": sprints,
        "stale_days": stale_days,
        "days": days,
        "opts": opts,
        "products": len(groups),
        "streams": len(streams),
    }


def build_needs(open_items, opts, today=None):
    """Rank and cap the NEEDS YOU list; attach numbered actions."""
    candidates = []
    for issue in open_items:
        kind = classify_need(issue, opts["untouched_days"], today=today)
        if not kind:
            continue
        age = _age_days(issue) or 0
        candidates.append((KIND_RANK[kind], -age, issue, kind))
    candidates.sort(key=lambda row: (row[0], row[1], row[2].get("key") or ""))

    actions = []
    for n, (_rank, _age, issue, kind) in enumerate(
            candidates[: opts["max_needs_you"]], start=1):
        actions.append({
            "n": n,
            "key": issue["key"],
            "summary": issue.get("summary") or "",
            "kind": kind,
            "product": issue.get("product"),
            "workstream": issue.get("workstream"),
            "url": issue.get("url"),
            "tags": need_tags(issue, kind),
            "description": describe_action(kind, issue, today=today),
            "preview": preview_payload(kind, issue, today=today),
        })
    return actions, len(candidates)


def build_aging(open_items, stale_days, limit):
    aging = []
    for issue in open_items:
        if not _is_in_progress(issue):
            continue
        age = _age_days(issue)
        if age is None or age <= stale_days:
            continue
        aging.append((age, issue))
    aging.sort(key=lambda row: (-row[0], row[1].get("key") or ""))
    return [{"age": age, "issue": issue} for age, issue in aging[:limit]], len(aging)


# ---------------------------------------------------------------------------
#  Rendering
# ---------------------------------------------------------------------------

def _heading_date(today=None):
    today = today or dt.date.today()
    return today.strftime(f"%A {today.day} %B")


def _short(text, limit=52):
    return sources.short(text or "", limit)


def render_screen(bundle, actions, aging, today=None):
    today = today or dt.date.today()
    open_n = len(bundle["open_items"])
    lines = [
        f"{_heading_date(today)} · {bundle['products']} product"
        f"{'' if bundle['products'] == 1 else 's'} · {open_n} open item"
        f"{'' if open_n == 1 else 's'}",
        "",
    ]

    goals = [s for s in bundle["sprints"] if s.get("goal")]
    if goals:
        lines.append("SPRINT GOAL")
        for sprint in goals:
            goal = sprint["goal"]
            label = sprint.get("name") or "Sprint"
            project = sprint.get("project") or ""
            prefix = f"{project} / {label}" if project else label
            lines.append(f"  {prefix}: {goal}")
        lines.append("")

    shown, total = len(actions), bundle.get("needs_total", len(actions))
    extra = f" of {total}" if total > shown else ""
    lines.append(f"NEEDS YOU ({shown}{extra})")
    if not actions:
        lines.append("  Nothing waiting on you. Clear the refinement gaps or take a walk.")
    for action in actions:
        loc = ""
        if action.get("product") or action.get("workstream"):
            loc = f"  {action.get('product') or '-'}/{action.get('workstream') or '-'}"
        lines.append(
            f"  {action['n']:<2} {action['key']:<8} {_short(action['summary'])}{loc}")
        lines.append(f"     {action['tags']}")
        lines.append(f"     → pm do {action['n']}     {action['description']}")
    lines.append("")

    moved = bundle["moved"][: bundle["opts"]["max_moved"]]
    lines.append(f"MOVED SINCE YESTERDAY ({len(moved)}"
                 f"{'' if len(bundle['moved']) <= len(moved) else ' of ' + str(len(bundle['moved']))})")
    if not moved:
        lines.append("  No status changes.")
    for card in moved:
        last = (card.get("transitions") or [{}])[-1]
        arrow = f"{last.get('from', '?')} → {last.get('to', '?')}"
        who = f" by {last['who']}" if last.get("who") else ""
        when = last.get("when")
        stamp = ""
        if when:
            local = when.astimezone() if getattr(when, "tzinfo", None) else when
            try:
                stamp = f" ({local:%H:%M})"
            except (TypeError, ValueError):
                stamp = ""
        lines.append(
            f"  {card['key']:<8} {arrow}{who}{stamp}  {_short(card.get('summary'), 40)}")
    lines.append("")

    aging_rows, aging_total = aging
    extra = f" of {aging_total}" if aging_total > len(aging_rows) else ""
    lines.append(f"AGING ({len(aging_rows)}{extra})")
    if not aging_rows:
        lines.append("  Nothing in progress past the stale threshold.")
    for row in aging_rows:
        issue = row["issue"]
        loc = issue.get("product_name") or issue.get("workstream") or ""
        lines.append(
            f"  {issue['key']:<8} {issue.get('status')} {row['age']} days, "
            f"untouched {row['age']} — {_short(issue.get('summary'), 36)}"
            f"{('  (' + loc + ')') if loc else ''}")
    lines.append("")

    lines.append("REFINEMENT GAPS")
    any_gaps = False
    for product, stats in bundle["ready_gaps"]:
        if not stats["total"]:
            continue
        for stream in stats["streams"]:
            if not stream["not_ready"]:
                continue
            any_gaps = True
            lines.append(
                f"  {stream['abbrev']:<6} {stream['not_ready']} of "
                f"{stream['total']} items still fail the team's ready "
                f"agreement     pm refine -w {stream['abbrev']}")
    if not any_gaps:
        lines.append("  Every in-scope item meets the team's ready agreement.")
    lines.append("")
    lines.append("`pm do N` previews, then writes after one confirmation.")
    return "\n".join(lines)


def run_today(cfg, args):
    print("Gathering today's picture ...")
    bundle = gather(cfg)
    actions, needs_total = build_needs(bundle["open_items"], bundle["opts"])
    bundle["needs_total"] = needs_total
    aging = build_aging(bundle["open_items"], bundle["stale_days"],
                        bundle["opts"]["max_aging"])

    payload = {
        "date": dt.date.today().isoformat(),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "actions": actions,
    }
    save_actions(bundle["opts"]["state_file"], payload)
    print(render_screen(bundle, actions, aging))
    print(f"\nActions saved to {bundle['opts']['state_file']}.")


def run_do(cfg, args):
    opts = settings(cfg)
    n = getattr(args, "number", None)
    if n is None:
        sys.exit("Which action? e.g.  pm do 1")
    stored = load_actions(opts["state_file"])
    if not stored or not stored.get("actions"):
        sys.exit(f"No numbered list at {opts['state_file']}. "
                 f"Run `pm today` first.")

    action = next((a for a in stored["actions"] if a.get("n") == n), None)
    if action is None:
        available = ", ".join(str(a["n"]) for a in stored["actions"])
        sys.exit(f"No action {n}. Available: {available}. "
                 f"(List from {stored.get('date') or 'the last pm today'}.)")

    preview = dict(action.get("preview") or {})
    preview.setdefault("key", action.get("key"))
    preview.setdefault("summary", action.get("summary"))
    preview.setdefault("description", action.get("description"))
    preview.setdefault("kind", action.get("kind"))
    body = preview.get("body")
    if isinstance(body, dict):
        assignee = (body.get("fields") or {}).get("assignee") or {}
        if assignee.get("accountId") == "(current user)":
            me = sources.fetch_myself(cfg["jira"])
            account = me.get("accountId")
            if not account:
                sys.exit("Could not resolve your Jira account id.")
            body = dict(body)
            fields = dict(body.get("fields") or {})
            fields["assignee"] = {"accountId": account}
            body["fields"] = fields
            preview["body"] = body
    writes.apply_action(cfg, args, preview)


def run(cfg, args):
    if getattr(args, "do_number", None) is not None or \
            getattr(args, "command", "") == "do":
        run_do(cfg, args)
        return
    run_today(cfg, args)
