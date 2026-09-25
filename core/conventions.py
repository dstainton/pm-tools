"""Team names for issue types, links and labels. Defaults match this backlog."""

DEFAULTS = {
    "bug_types": ["Bug"],
    "blocked_by_links": ["is blocked by", "blocked by"],
    "blocks_links": ["blocks"],
    "note_issuetypes": ["Story", "Task", "Bug"],
    "note_issuetype": "Story",
    "action_issuetypes": ["Story", "Task"],
    "action_issuetype": "Task",
    "risk_label": "risk",
}


def get(cfg, key):
    """One convention, from config when set, otherwise the default."""
    block = (cfg or {}).get("conventions") or {}
    value = block.get(key)
    if value is None or value == "":
        value = DEFAULTS[key]
    return value


def names(cfg, key):
    """A convention that is a list of names, compared case-insensitively."""
    value = get(cfg, key)
    if isinstance(value, str):
        value = [value]
    return [str(item).strip().lower() for item in value if str(item).strip()]
