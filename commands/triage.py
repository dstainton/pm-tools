"""`pm triage` — the queue of things waiting on a decision from you.

Deterministic. No model. Grouped by product, each line with the action
that clears it. `--apply N` uses the same write path as `pm do`.
"""

import datetime as dt
import json
import os
import sys

from commands import today as today_cmd
from core import paths, products as product_core, sources, workstreams, writes


def settings(cfg):
    block = cfg.get("triage") if isinstance(cfg.get("triage"), dict) else {}
    return {
        "unassigned_in_sprint": block.get("unassigned_in_sprint", True),
        "blocked": block.get("blocked", True),
        "mentions_me_within_days": int(block.get("mentions_me_within_days", 3)
                                       or 0),
        "new_bugs_within_days": int(block.get("new_bugs_within_days", 1) or 0),
        "in_sprint_untouched_days": int(block.get("in_sprint_untouched_days", 3)
                                        or 0),
        "overdue": block.get("overdue", True),
        "state_file": os.path.expanduser(
            block.get("state_file") or
            os.path.join(paths.local_dir(cfg), "triage.json")),
    }


def _comment_text(comment):
    body = comment.get("body")
    if isinstance(body, str):
        return body
    texts = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "text":
                texts.append(node.get("text") or "")
            for child in node.get("content") or []:
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(body)
    return " ".join(texts)


def _mentioned(issue, me, within_days, jira_cfg):
    if not within_days or not me:
        return False
    updated = today_cmd._parse_datetime(issue.get("updated"))
    if updated:
        age = (dt.datetime.now(dt.timezone.utc) - updated).days
        if age > within_days:
            return False
    names = [n for n in (me.get("displayName"), me.get("emailAddress")) if n]
    try:
        comments = sources.fetch_comments(jira_cfg, issue["key"])
    except Exception:                              # noqa: BLE001
        return False
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=within_days)
    for comment in comments:
        created = today_cmd._parse_datetime(comment.get("created"))
        if created and created < cutoff:
            continue
        text = _comment_text(comment).lower()
        if any(name.lower() in text for name in names):
            return True
    return False


def _blocked_by_link(issue, jira_cfg):
    try:
        links = sources.fetch_issue_links(jira_cfg, issue["key"])
    except Exception:                              # noqa: BLE001
        return None
    for link in links:
        if "block" in (link.get("relation") or ""):
            return link
    return None


def _is_new_bug(issue, within_days):
    if not within_days:
        return False
    if (issue.get("issuetype") or "").lower() != "bug":
        return False
    created = today_cmd._parse_datetime(issue.get("created") or issue.get("updated"))
    if not created:
        return False
    return (dt.datetime.now(dt.timezone.utc) - created).days <= within_days


def classify(issue, opts, me, jira_cfg):
    """Highest-priority triage kind, or None."""
    if today_cmd._is_done(issue):
        return None
    if (issue.get("issuetype") or "").lower() == "epic":
        return None
    if opts["overdue"] and today_cmd._is_overdue(issue):
        return "overdue"
    if opts["blocked"] and (today_cmd._is_blocked(issue)
                            or _blocked_by_link(issue, jira_cfg)):
        return "blocked"
    if opts["unassigned_in_sprint"] and today_cmd._is_unassigned(issue):
        return "unassigned"
    if _mentioned(issue, me, opts["mentions_me_within_days"], jira_cfg):
        return "mention"
    if _is_new_bug(issue, opts["new_bugs_within_days"]):
        return "new-bug"
    if opts["in_sprint_untouched_days"] and today_cmd.classify_need(
            issue, opts["in_sprint_untouched_days"]) == "untouched":
        return "untouched"
    return None


KIND_RANK = {"overdue": 0, "blocked": 1, "mention": 2, "unassigned": 3,
             "new-bug": 4, "untouched": 5}


def describe(kind, issue):
    if kind == "mention":
        return "reply to the comment that named you"
    if kind == "new-bug":
        return "triage this bug (assign it or set a due date)"
    return today_cmd.describe_action(kind, issue)


def preview_for(kind, issue):
    if kind == "mention":
        return writes.action_comment(
            issue["key"], "Thanks — I'll take a look.",
            kind="mention-reply", summary=issue.get("summary"))
    if kind == "new-bug":
        return today_cmd.preview_payload("unassigned", issue)
    return today_cmd.preview_payload(kind, issue)


def gather(cfg):
    opts = settings(cfg)
    try:
        me = sources.fetch_myself(cfg["jira"])
    except Exception:                              # noqa: BLE001
        me = {}
    streams = cfg.get("_workstreams") or []
    items = []
    for product, group in product_core.group_workstreams(cfg, streams):
        for ws in group:
            jql = workstreams.scope_jql(cfg, ws, "lint")
            issues = (sources.fetch_jira_detailed(cfg["jira"], jql)
                      if jql else [])
            for issue in issues:
                tagged = today_cmd._tag_issue(issue, ws, product)
                kind = classify(tagged, opts, me, cfg["jira"])
                if not kind:
                    continue
                items.append((KIND_RANK[kind], tagged, kind))
    items.sort(key=lambda row: (row[0], row[1].get("key") or ""))
    actions = []
    for n, (_rank, issue, kind) in enumerate(items, start=1):
        actions.append({
            "n": n,
            "key": issue["key"],
            "summary": issue.get("summary") or "",
            "kind": kind,
            "product": issue.get("product"),
            "workstream": issue.get("workstream"),
            "url": issue.get("url"),
            "tags": today_cmd.need_tags(issue, kind if kind in
                                        today_cmd.KIND_RANK else "unassigned"),
            "description": describe(kind, issue),
            "preview": preview_for(kind, issue),
        })
    return actions, opts


def render(actions):
    lines = [f"TRIAGE ({len(actions)})", ""]
    if not actions:
        lines.append("Nothing waiting on you.")
        return "\n".join(lines)
    current = None
    for action in actions:
        loc = f"{action.get('product') or '-'}/{action.get('workstream') or '-'}"
        if loc != current:
            current = loc
            lines.append(loc)
        lines.append(
            f"  {action['n']:<2} {action['key']:<8} "
            f"{sources.short(action['summary'], 52)}")
        lines.append(f"     {action['tags']}")
        lines.append(f"     → pm triage --apply {action['n']}     "
                     f"{action['description']}")
    return "\n".join(lines)


def run(cfg, args):
    actions, opts = gather(cfg)
    today_cmd.save_actions(opts["state_file"], {
        "date": dt.date.today().isoformat(),
        "actions": actions,
    })
    apply_n = getattr(args, "apply", None)
    if apply_n is None:
        print(render(actions))
        print(f"\nActions saved to {opts['state_file']}.")
        return
    action = next((a for a in actions if a["n"] == apply_n), None)
    if action is None:
        stored = today_cmd.load_actions(opts["state_file"]) or {}
        action = next((a for a in stored.get("actions") or []
                       if a.get("n") == apply_n), None)
    if action is None:
        sys.exit(f"No triage action {apply_n}. Run `pm triage` first.")
    preview = dict(action.get("preview") or {})
    preview.setdefault("key", action.get("key"))
    preview.setdefault("summary", action.get("summary"))
    preview.setdefault("kind", action.get("kind"))
    writes.apply_action(cfg, args, preview)
