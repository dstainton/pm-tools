"""Week-to-week memory: what did we see last time, and what changed.

A tiny JSON file maps each workstream to a snapshot of the items we saw, keyed
by each item's STABLE uid (Jira key, Confluence page id, SharePoint file id) so
matching survives re-ordering between runs.
"""

import json
import os


def load_state(path):
    """Read last week's snapshot, or return an empty one on the first run."""
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (ValueError, OSError):
            print(f"  (could not read state file {path}; treating as first run)")
    return {}


def save_state(path, state):
    """Write this week's snapshot for next week to compare against."""
    if not path:
        return
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)


def snapshot_items(items):
    """Reduce this week's items to the bare facts we compare next week."""
    return {it["uid"]: {"title": it["title"], "watch": it["watch"]}
            for it in items}


def compute_changes(prev_snapshot, items):
    """Compare last week's snapshot to this week's items.

    Returns three lists:
      new     - items whose uid was not present last week
      changed - items whose watched value (e.g. Jira status) moved
      dropped - uids present last week but absent this week (done / moved out)
    """
    current = {it["uid"]: it for it in items}
    new, changed = [], []
    for uid, it in current.items():
        if uid not in prev_snapshot:
            new.append(it)
        elif prev_snapshot[uid].get("watch") != it["watch"]:
            changed.append((it, prev_snapshot[uid].get("watch")))
    dropped = [(uid, snap) for uid, snap in prev_snapshot.items()
               if uid not in current]
    return new, changed, dropped


def build_change_block(new, changed, dropped, first_run):
    """Turn the diff into a short, taggable block for the model to summarise."""
    if first_run:
        return "(First run for this workstream — no previous week to compare.)"

    lines = []
    if new:
        lines.append("New this week:")
        for it in new:
            lines.append(f"  - [{it['ref']}] {it['title']}")
    if changed:
        lines.append("Status changed this week:")
        for it, old in changed:
            lines.append(f"  - [{it['ref']}] {it['title']} "
                         f"(was: {old or 'n/a'}; now: {it['watch'] or 'n/a'})")
    if dropped:
        lines.append("Dropped out of scope this week (likely done or moved on):")
        for _uid, snap in dropped:
            lines.append(f"  - {snap.get('title', '(unknown item)')}")

    return "\n".join(lines) if lines else "No changes detected since last week."
