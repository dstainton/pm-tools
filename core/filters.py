"""Plain-English scope filters, compiled to JQL.

The user never writes JQL. A scope is a small YAML mapping of options —

    lint:
      status: open
      types: [Story, Task, Bug]

— and this module turns it into the JQL fragment that goes inside a
workstream's membership scope. Every option is validated up front, so a typo in
config fails with the list of valid choices instead of a confusing Jira error.

`extra_jql` stays available as a deliberate escape hatch for the rare filter
this vocabulary cannot express, but nothing in the shipped config needs it.
"""

import sys


# ---------------------------------------------------------------------------
#  The vocabulary
# ---------------------------------------------------------------------------

#  option -> {accepted value: JQL fragment}. None means "no filter at all".
STATUS_VALUES = {
    "any": None,
    "open": "statusCategory != Done",
    "done": "statusCategory = Done",
    "in-progress": 'statusCategory = "In Progress"',
    "todo": 'statusCategory = "To Do"',
}

SPRINT_VALUES = {
    "any": None,
    "open": "sprint in openSprints()",
    "future": "sprint in futureSprints()",
    "none": "sprint IS EMPTY",
}

ASSIGNEE_VALUES = {
    "any": None,
    "me": "assignee = currentUser()",
    "unassigned": "assignee IS EMPTY",
    "assigned": "assignee IS NOT EMPTY",
}

#  Which scopes exist, and which part of the workstream each one looks at:
#    children   - work beneath the workstream's epics (Stories/Tasks/Sub-tasks)
#    epics      - the workstream epics themselves
#    everything - the epics plus everything beneath them
SCOPE_INCLUDES = {
    "report": "children",
    "roadmap": "epics",
    "lint": "everything",
    "review": "everything",
    "ready": "children",
    "standup_moved": "children",
    "standup_wip": "children",
}

#  Sensible defaults, so a workstream only has to name its components. Any of
#  these can be overridden globally under `scopes:` or per workstream.
DEFAULT_SCOPES = {
    "report": {"sprint": "open"},
    "roadmap": {"status": "open"},
    "lint": {"status": "open"},
    "review": {"status": "open"},
    "ready": {"sprint": "open", "status": "open"},
    "standup_moved": {"updated_within_days": 1},
    "standup_wip": {"status": "in-progress"},
}

VALID_OPTIONS = (
    "status", "sprint", "assignee", "types", "exclude_types",
    "labels_any", "labels_none", "updated_within_days",
    "created_within_days", "due_within_days", "extra_jql",
)


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def quote(value):
    """Quote a JQL string literal safely enough for config-provided names."""
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def _value_list(option, value):
    """Accept either a YAML list or a single value for list-ish options."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items = list(value)
    elif isinstance(value, str):
        items = [v.strip() for v in value.split(",")]
    else:
        _fail(f"`{option}` must be a list of values (got {value!r}).")
    return [i for i in items if str(i).strip()]


def _choice(option, value, table):
    key = str(value).strip().lower()
    if key not in table:
        _fail(f"`{option}: {value}` is not a valid choice. "
              f"Valid: {', '.join(sorted(table))}.")
    return table[key]


def _positive_int(option, value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        _fail(f"`{option}` must be a whole number of days (got {value!r}).")
    if number < 0:
        _fail(f"`{option}` must not be negative (got {value!r}).")
    return number


def _fail(message):
    sys.exit(f"Config problem: {message}")


# ---------------------------------------------------------------------------
#  Compiling one scope
# ---------------------------------------------------------------------------

def compile_scope(options):
    """Turn a scope mapping into a JQL fragment (or "" when it filters nothing)."""
    if not options:
        return ""

    clauses = []
    for option, value in options.items():
        if option not in VALID_OPTIONS:
            _fail(f"unknown scope option `{option}`. "
                  f"Valid options: {', '.join(VALID_OPTIONS)}.")
        if value is None:
            continue

        if option == "status":
            clause = _choice(option, value, STATUS_VALUES)
        elif option == "sprint":
            clause = _choice(option, value, SPRINT_VALUES)
        elif option == "assignee":
            clause = _choice(option, value, ASSIGNEE_VALUES)
        elif option == "types":
            names = _value_list(option, value)
            clause = (f"issuetype IN ({', '.join(quote(n) for n in names)})"
                      if names else None)
        elif option == "exclude_types":
            names = _value_list(option, value)
            clause = (f"issuetype NOT IN ({', '.join(quote(n) for n in names)})"
                      if names else None)
        elif option == "labels_any":
            names = _value_list(option, value)
            clause = (f"labels IN ({', '.join(quote(n) for n in names)})"
                      if names else None)
        elif option == "labels_none":
            names = _value_list(option, value)
            clause = (f"(labels IS EMPTY OR labels NOT IN "
                      f"({', '.join(quote(n) for n in names)}))"
                      if names else None)
        elif option == "updated_within_days":
            clause = f"updated >= -{_positive_int(option, value)}d"
        elif option == "created_within_days":
            clause = f"created >= -{_positive_int(option, value)}d"
        elif option == "due_within_days":
            clause = f"duedate <= {_positive_int(option, value)}d"
        else:  # extra_jql — the escape hatch, used verbatim
            clause = str(value).strip() or None

        if clause:
            clauses.append(clause)

    return " AND ".join(clauses)


def scope_options(cfg, ws, scope_name, overrides=None):
    """Merge the scope options that apply to one workstream and one command.

    Precedence, lowest first: built-in defaults, the global `scopes:` block,
    the workstream's own `scopes:` block, then run-time overrides (for example
    `pm standup --days 3`).
    """
    if scope_name not in SCOPE_INCLUDES:
        _fail(f"unknown scope `{scope_name}`. "
              f"Valid scopes: {', '.join(sorted(SCOPE_INCLUDES))}.")

    merged = dict(DEFAULT_SCOPES.get(scope_name, {}))
    for layer in ((cfg.get("scopes") or {}), (ws.get("scopes") or {})):
        if not isinstance(layer, dict):
            _fail("`scopes:` must be a mapping of scope name to options.")
        block = layer.get(scope_name)
        if block is None:
            continue
        if not isinstance(block, dict):
            _fail(f"`scopes: {scope_name}:` must be a mapping of options, "
                  f"e.g. `{scope_name}: {{status: open}}`.")
        merged.update(block)
    if overrides:
        merged.update(overrides)
    return merged


def validate_config_scopes(cfg):
    """Compile every configured scope once at load time so typos fail early."""
    layers = [("scopes", cfg.get("scopes") or {})]
    for ws in cfg.get("workstreams") or []:
        label = ws.get("abbrev") or ws.get("name") or "(unnamed)"
        layers.append((f"workstream {label} scopes", ws.get("scopes") or {}))

    for where, layer in layers:
        if not isinstance(layer, dict):
            _fail(f"`{where}` must be a mapping of scope name to options.")
        for scope_name, options in layer.items():
            if scope_name not in SCOPE_INCLUDES:
                _fail(f"`{where}` names an unknown scope `{scope_name}`. "
                      f"Valid scopes: {', '.join(sorted(SCOPE_INCLUDES))}.")
            if options is None:
                continue
            if not isinstance(options, dict):
                _fail(f"`{where} > {scope_name}` must be a mapping of options.")
            compile_scope(options)


# ---------------------------------------------------------------------------
#  Confluence — the same idea, one level simpler
# ---------------------------------------------------------------------------

def build_cql(ws):
    """Build Confluence CQL from `confluence_space` / `confluence_labels`.

    A hand-written `confluence_cql` still wins if one is present, so existing
    configs keep working.
    """
    if ws.get("confluence_cql"):
        return ws["confluence_cql"]

    space = ws.get("confluence_space")
    if not space:
        return None

    clauses = [f"space = {quote(space)}"]
    labels = _value_list("confluence_labels", ws.get("confluence_labels"))
    if labels:
        clauses.append(f"label IN ({', '.join(quote(l) for l in labels)})")
    return " AND ".join(clauses)
