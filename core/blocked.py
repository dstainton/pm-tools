"""What "blocked" means in this team's workflow.

The names are configuration, not a guess. A status counts when it equals a
configured name, so `Unblocked` does not match `Blocked`. Labels match the
same way.
"""

DEFAULT_STATUSES = ["Blocked"]
DEFAULT_LABELS = ["blocked"]


def _names(value, default):
    if value is None:
        value = default
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item).strip().lower() for item in value if str(item).strip()]


def names(cfg):
    """`(statuses, labels)`, both lower-cased. Defaults match a status
    named Blocked and a label named blocked.
    """
    block = (cfg or {}).get("blocked")
    if not isinstance(block, dict):
        block = {}
    return (_names(block.get("statuses"), DEFAULT_STATUSES),
            _names(block.get("labels"), DEFAULT_LABELS))


def is_blocked(issue, cfg=None):
    statuses, labels = names(cfg)
    status = (issue.get("status") or "").strip().lower()
    if status and status in statuses:
        return True
    present = {str(label).strip().lower()
               for label in (issue.get("labels") or [])}
    return any(label in present for label in labels)
