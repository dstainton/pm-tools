"""`pm triage` — the queue of things waiting on a decision from you.

Deterministic. No model. Grouped by product, each line with the action
that clears it. `--apply N` uses the same write path as `pm do`.
"""

import datetime as dt
import json
import os
import re
import sys

from commands import today as today_cmd
from core import (
    comments as comment_core, paths, products as product_core, sources,
    workstreams, writes,
)


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
    return comment_core.comment_text(comment)


def _mention_ids(comment):
    """accountIds on ADF mention nodes. Plain text has none."""
    return comment_core.mention_ids(comment)


def _name_mentioned(text, name):
    """Whole-word match, so Sam does not match sample."""
    if not name:
        return False
    return re.search(r"\b" + re.escape(name) + r"\b", text, re.IGNORECASE) is not None


def _mentioned(issue, me, within_days, jira_cfg, cfg=None):
    if not within_days or not me:
        return False
    updated = today_cmd._parse_datetime(issue.get("updated"))
    if updated:
        age = (dt.datetime.now(dt.timezone.utc) - updated).days
        if age > within_days:
            return False
    account = str(me.get("accountId") or "")
    names = [n for n in (me.get("displayName"), me.get("emailAddress")) if n]
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=within_days)
    try:
        thread = sources.fetch_comments(jira_cfg, issue["key"], cutoff=cutoff)
    except Exception:                              # noqa: BLE001
        return False
    matched = None
    for comment in thread:
        created = today_cmd._parse_datetime(comment.get("created"))
        if created and created < cutoff:
            continue
        named = account and account in _mention_ids(comment)
        text = _comment_text(comment)
        if named or any(_name_mentioned(text, name) for name in names):
            matched = comment
    if matched is None:
        return False
    excerpt = comment_core.settings(cfg or {})["excerpt_chars"]
    issue["mention_comment"] = comment_core.format_line(matched, excerpt)
    return True


def _is_blocked_by(link):
    """This issue is blocked by the other one.

    Jira's Blocks link says `blocks` outward and `is blocked by` inward.
    Matching the substring `block` treated both directions as the same problem.
    """
    relation = (link.get("relation") or "").strip().lower()
    if relation in ("is blocked by", "blocked by"):
        return True
    return link.get("direction") == "inward" and relation == "blocks"


def _blocked_by_link(issue, jira_cfg):
    try:
        links = sources.fetch_issue_links(jira_cfg, issue["key"])
    except Exception:                              # noqa: BLE001
        return None
    for link in links:
        if _is_blocked_by(link):
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


def classify(issue, opts, me, jira_cfg, cfg=None):
    """Highest-priority triage kind, or None."""
    if today_cmd._is_done(issue):
        return None
    if (issue.get("issuetype") or "").lower() == "epic":
        return None
    if opts["overdue"] and today_cmd._is_overdue(issue):
        return "overdue"
    if opts["blocked"] and (today_cmd._is_blocked(issue, cfg)
                            or _blocked_by_link(issue, jira_cfg)):
        return "blocked"
    if opts["unassigned_in_sprint"] and today_cmd._is_unassigned(issue):
        return "unassigned"
    if _mentioned(issue, me, opts["mentions_me_within_days"], jira_cfg, cfg):
        return "mention"
    if _is_new_bug(issue, opts["new_bugs_within_days"]):
        return "new-bug"
    if opts["in_sprint_untouched_days"] and today_cmd.classify_need(
            issue, opts["in_sprint_untouched_days"], cfg=cfg) == "untouched":
        return "untouched"
    return None


KIND_RANK = {"overdue": 0, "blocked": 1, "mention": 2, "unassigned": 3,
             "new-bug": 4, "untouched": 5}


def describe(kind, issue):
    if kind == "mention":
        quoted = issue.get("mention_comment")
        if quoted:
            return f"reply to the comment that named you — {quoted}"
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
                kind = classify(tagged, opts, me, cfg["jira"], cfg=cfg)
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
            "tags": today_cmd.need_tags(
                issue, kind if kind in today_cmd.KIND_RANK else "unassigned",
                cfg=cfg),
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
