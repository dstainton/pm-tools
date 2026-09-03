"""The one path that writes to Jira.

Contract, settled 2026-09-03:

* Preview the payload.
* Confirm once (`--yes` skips the prompt; `--dry-run` stops after preview).
* Send.
* Append a line to `~/.pm/write-log.jsonl`.
* Nothing on this path runs on a schedule.

Non-interactive runs (tests, scripts) must pass `--yes` or `--dry-run`.
A missing TTY without `--yes` is a refused write, not a hang.
"""

import datetime as dt
import json
import os
import sys

import requests

from core import paths, sources


def adf_doc(text):
    """Jira Cloud comment / description body."""
    return {"type": "doc", "version": 1,
            "content": [{"type": "paragraph",
                         "content": [{"type": "text", "text": str(text)}]}]}


def preview(action):
    """Print exactly what would be sent."""
    method = action.get("method") or "PUT"
    path = action.get("path") or ""
    print(f"Would {method} {path}")
    if action.get("key") or action.get("summary"):
        bits = [b for b in (action.get("key"), action.get("summary")) if b]
        print("  " + " — ".join(bits))
    if action.get("description"):
        print(f"  {action['description']}")
    if action.get("body") is not None:
        print("  " + json.dumps(action["body"], indent=2).replace("\n", "\n  "))


def should_write(args):
    """True when the user confirmed; False on --dry-run; exits if unsafe."""
    if getattr(args, "dry_run", False):
        print("\n--dry-run: nothing was sent.")
        return False
    if getattr(args, "yes", False):
        return True
    if not sys.stdin.isatty():
        sys.exit("Refusing to write: stdin is not a terminal. "
                 "Re-run with --yes to confirm, or --dry-run to preview.")
    reply = input("\nSend this to Jira? [y/N] ").strip().lower()
    if reply in ("y", "yes"):
        return True
    print("Cancelled. Nothing was sent.")
    return False


def execute(cfg, action):
    """Send one action and return the response JSON (or {})."""
    jira = cfg["jira"]
    if action.get("url"):
        url = action["url"]
    else:
        url = jira["base_url"].rstrip("/") + action["path"]
    method = (action.get("method") or "PUT").upper()
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if action.get("auth") == "none":
        auth = None
    else:
        auth = (jira["email"], jira["api_token"])
    timeout = 60
    if method == "PUT":
        resp = requests.put(url, json=action.get("body") or {},
                            auth=auth, headers=headers, timeout=timeout)
    elif method == "POST":
        resp = requests.post(url, json=action.get("body") or {},
                             auth=auth, headers=headers, timeout=timeout)
    else:
        sys.exit(f"Unsupported write method {method}.")
    resp.raise_for_status()
    if not resp.content:
        return {}
    try:
        return resp.json()
    except ValueError:
        return {}


def log_write(cfg, action, result=None, error=None):
    path = paths.write_log_path(cfg)
    record = {
        "at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "method": action.get("method"),
        "path": action.get("path"),
        "key": action.get("key"),
        "kind": action.get("kind"),
        "ok": error is None,
    }
    if error:
        record["error"] = str(error)
    if result and isinstance(result, dict):
        if result.get("key"):
            record["created"] = result.get("key")
        if result.get("id") and action.get("kind", "").startswith("publish"):
            record["published"] = result.get("id")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def _fill_current_user(cfg, action):
    """Replace the `(current user)` assignee placeholder with a real accountId."""
    body = action.get("body")
    if not isinstance(body, dict):
        return action
    assignee = (body.get("fields") or {}).get("assignee") or {}
    if assignee.get("accountId") != "(current user)":
        return action
    me = sources.fetch_myself(cfg["jira"])
    account = me.get("accountId")
    if not account:
        sys.exit("Could not resolve your Jira account id.")
    action = dict(action)
    body = dict(body)
    fields = dict(body.get("fields") or {})
    fields["assignee"] = {"accountId": account}
    body["fields"] = fields
    action["body"] = body
    return action


def apply_action(cfg, args, action):
    """Preview, confirm, send, log. Returns the response or None."""
    action = _fill_current_user(cfg, action)
    preview(action)
    if not should_write(args):
        return None
    try:
        result = execute(cfg, action)
    except requests.RequestException as err:
        log_write(cfg, action, error=err)
        sys.exit(f"Write failed: {err}")
    log_write(cfg, action, result=result)
    created = (result or {}).get("key")
    if created:
        print(f"\nCreated {created}.")
    else:
        print("\nSent.")
    return result


def action_update_issue(key, fields, kind, summary="", description=""):
    return {
        "method": "PUT",
        "path": f"/rest/api/3/issue/{key}",
        "body": {"fields": fields},
        "key": key,
        "kind": kind,
        "summary": summary,
        "description": description,
    }


def action_comment(key, text, kind="comment", summary=""):
    return {
        "method": "POST",
        "path": f"/rest/api/3/issue/{key}/comment",
        "body": {"body": adf_doc(text)},
        "key": key,
        "kind": kind,
        "summary": summary,
        "description": "add a comment",
    }


def action_create_issue(fields, kind="create", summary=""):
    return {
        "method": "POST",
        "path": "/rest/api/3/issue",
        "body": {"fields": fields},
        "kind": kind,
        "summary": summary,
        "description": "create the issue",
    }
