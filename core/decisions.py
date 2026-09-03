"""Findings that remember the decision you already made.

A finding is identified by issue key plus lint rule (or `*` for every rule
on that key). Three verbs:

  snooze   hidden until a date (`--until`)
  accept   hidden until you `--all` (you decided this is fine)
  assign   hidden from the default lint; it lives in that person's
           `pm refine` queue. Deliberately a person, not a role.

The file lives in `state.shared_path` when that is set, otherwise `~/.pm`,
so the PM and the BA see the same memory.
"""

import datetime as dt
import json
import os
import re

from core import paths


def empty_store():
    return {"decisions": []}


def load(cfg):
    path = paths.decisions_path(cfg)
    if not os.path.exists(path):
        return empty_store()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (ValueError, OSError):
        return empty_store()
    if not isinstance(data, dict) or "decisions" not in data:
        return empty_store()
    return data


def save(cfg, store):
    path = paths.decisions_path(cfg)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(store, fh, indent=2)


def parse_until(value, today=None, sprint_end=None):
    """Turn `--until` into an ISO date.

    Accepts YYYY-MM-DD, `Nd` / `Nw`, `next-sprint` (sprint end, else +14 days).
    """
    today = today or dt.date.today()
    if not value:
        return None
    text = str(value).strip().lower()
    if text in ("next-sprint", "next_sprint", "next sprint"):
        if sprint_end:
            return str(sprint_end)
        return (today + dt.timedelta(days=14)).isoformat()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    match = re.fullmatch(r"(\d+)\s*([dw])", text)
    if match:
        n, unit = int(match.group(1)), match.group(2)
        days = n * 7 if unit == "w" else n
        return (today + dt.timedelta(days=days)).isoformat()
    raise ValueError(
        f"Cannot parse --until {value!r}. "
        f"Try 2026-09-17, 14d, 2w, or next-sprint.")


def record(cfg, verb, key, why, until=None, rule="*", to=None, today=None):
    """Add or replace a decision. Returns the stored record."""
    if verb not in ("snooze", "accept", "assign"):
        raise ValueError(f"Unknown decision verb {verb}")
    if verb == "snooze" and not until:
        raise ValueError("--snooze needs --until (a date, 14d, or next-sprint).")
    if verb == "assign" and not to:
        raise ValueError("--assign needs --to <person>.")
    store = load(cfg)
    record = {
        "key": key,
        "rule": rule or "*",
        "verb": verb,
        "why": why or "",
        "until": until,
        "to": to,
        "at": (today or dt.date.today()).isoformat(),
    }
    kept = [d for d in store["decisions"]
            if not (d.get("key") == key
                    and (d.get("rule") or "*") == (rule or "*")
                    and d.get("verb") == verb)]
    kept.append(record)
    store["decisions"] = kept
    save(cfg, store)
    return record


def _active(decision, today=None):
    today = today or dt.date.today()
    verb = decision.get("verb")
    if verb == "accept":
        return True
    if verb == "assign":
        return True
    if verb == "snooze":
        until = decision.get("until")
        if not until:
            return True
        try:
            return dt.date.fromisoformat(str(until)[:10]) >= today
        except ValueError:
            return True
    return False


def matching(store, key, rule=None, today=None):
    """Active decisions that apply to this key (and optional rule)."""
    out = []
    for decision in store.get("decisions") or []:
        if decision.get("key") != key:
            continue
        if not _active(decision, today=today):
            continue
        stored_rule = decision.get("rule") or "*"
        if rule and stored_rule not in ("*", rule):
            continue
        out.append(decision)
    return out


def is_hidden(store, finding, today=None, assignee=None):
    """True when a lint-style finding should be omitted from the default view.

    `assignee` is the current user's display name. An `assign` to someone
    else hides the finding from lint; an assign to you does not hide it
    from `pm refine`, but lint still hides it (it has been handed on).
    """
    key = finding.get("key")
    rule = finding.get("rule")
    hits = matching(store, key, rule=rule, today=today)
    if not hits:
        return False
    verbs = {d["verb"] for d in hits}
    if "accept" in verbs or "snooze" in verbs:
        return True
    if "assign" in verbs:
        return True
    return False


def summarise(store, hidden, today=None):
    """Counts for the '11 hidden (3 snoozed, …)' line."""
    today = today or dt.date.today()
    snoozed = accepted = assigned = 0
    seen = set()
    for finding in hidden:
        key = (finding.get("key"), finding.get("rule"))
        if key in seen:
            continue
        seen.add(key)
        hits = matching(store, finding.get("key"), finding.get("rule"), today)
        verbs = {d["verb"] for d in hits}
        if "accept" in verbs:
            accepted += 1
        elif "snooze" in verbs:
            snoozed += 1
        elif "assign" in verbs:
            assigned += 1
    return {"hidden": len(hidden), "snoozed": snoozed,
            "accepted": accepted, "assigned": assigned}


def assigned_to(store, key, today=None):
    hits = [d for d in matching(store, key, today=today) if d.get("verb") == "assign"]
    if not hits:
        return None
    return hits[-1].get("to")
