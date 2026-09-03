"""Working out which Jira issues belong to a workstream.

A workstream is described in config with nothing but a project and one or more
Components:

    - name: "Secure Data Exchange"
      abbrev: "SDX"
      components: ["Secure Data Exchange"]

Membership is then resolved from Jira, following the way real backlogs are
tagged:

1. **Its own Component.** Any issue carrying one of the workstream's Components
   belongs to it, whatever its type.
2. **Inherited from its parent.** Epics carry the Component; their Stories,
   Tasks, Bugs and Sub-tasks usually do not. Anything beneath a workstream Epic
   therefore belongs to the workstream too, and so do the Sub-tasks of a
   directly tagged Story or Task.

Set `membership.child_component_wins: true` if a child's own Component should
override the one it would inherit; by default membership is a union, so work is
never silently dropped from every workstream at once.

Each command then narrows that membership with a scope — plain options such as
`status: open`, compiled to JQL by `core.filters`. Legacy configs that wrote
their own `*_jql` strings still work: those strings are applied as an extra
filter inside the resolved membership (or, for a workstream with no Components,
used verbatim as before).
"""

from core import filters, sources


#  scope name -> the workstream `*_jql` field(s) an older config may have used,
#  in fallback order. Kept so upgrading does not change anyone's scope.
LEGACY_FIELDS = {
    "report": ["jira_jql"],
    "roadmap": ["roadmap_jql"],
    "lint": ["lint_jql"],
    "review": ["review_jql", "lint_jql"],
    "ready": ["ready_jql", "jira_jql"],
    "standup_moved": ["standup_moved_jql", "lint_jql"],
    "standup_wip": ["standup_wip_jql", "jira_jql"],
}

DEFAULT_MEMBERSHIP = {
    "epic_types": ["Epic"],
    "inherit_from_parent": True,
    "child_component_wins": False,
    "max_parent_keys": 500,
}


# ---------------------------------------------------------------------------
#  Reading the workstream definition
# ---------------------------------------------------------------------------

def project_of(cfg, ws):
    """The Jira project holding this workstream's work."""
    return (ws.get("project") or ws.get("jira_project")
            or (cfg.get("jira") or {}).get("project"))


def components_of(ws):
    """The Component name(s) that identify this workstream."""
    value = ws.get("components")
    if value is None:
        value = ws.get("epic_components")
    if not value:
        return []
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return [str(v) for v in value if str(v).strip()]


def uses_component_scope(cfg, ws):
    """True when membership comes from Components rather than hand-written JQL."""
    return bool(project_of(cfg, ws) and components_of(ws))


def membership_settings(cfg):
    """The `membership:` config block, with defaults filled in."""
    settings = dict(DEFAULT_MEMBERSHIP)
    settings.update(cfg.get("membership") or {})
    types = settings.get("epic_types") or ["Epic"]
    if isinstance(types, str):
        types = [t.strip() for t in types.split(",") if t.strip()]
    settings["epic_types"] = types
    return settings


# ---------------------------------------------------------------------------
#  Discovery: which epics (and which directly tagged issues) are in scope
# ---------------------------------------------------------------------------

def _component_clause(components):
    values = ", ".join(filters.quote(c) for c in components)
    return f"component IN ({values})"


def epic_selector_jql(cfg, ws):
    """JQL that finds the workstream's Epics — the ones carrying the Component."""
    project = project_of(cfg, ws)
    components = components_of(ws)
    if not project or not components:
        return None
    epic_types = membership_settings(cfg)["epic_types"]
    types = ", ".join(filters.quote(t) for t in epic_types)
    return (f"project = {filters.quote(project)} "
            f"AND issuetype IN ({types}) "
            f"AND {_component_clause(components)}")


def tagged_issue_selector_jql(cfg, ws):
    """JQL that finds non-Epic issues carrying the Component themselves.

    Their Sub-tasks inherit membership from them, the same way a Story inherits
    from its Epic.
    """
    project = project_of(cfg, ws)
    components = components_of(ws)
    if not project or not components:
        return None
    epic_types = membership_settings(cfg)["epic_types"]
    types = ", ".join(filters.quote(t) for t in epic_types)
    return (f"project = {filters.quote(project)} "
            f"AND issuetype NOT IN ({types}) "
            f"AND {_component_clause(components)}")


def _cached_keys(cfg, ws, cache_key, jql):
    """Resolve issue keys once per command run, cached on the workstream dict."""
    if cache_key not in ws:
        ws[cache_key] = sources.fetch_jira_keys(cfg["jira"], jql)
    return ws[cache_key]


def get_epic_keys(cfg, ws):
    """The workstream's Epic keys (cached for the duration of a command)."""
    if not uses_component_scope(cfg, ws):
        return []
    return _cached_keys(cfg, ws, "_resolved_epic_keys",
                        epic_selector_jql(cfg, ws))


def get_tagged_issue_keys(cfg, ws):
    """Keys of non-Epic issues that carry the Component themselves."""
    if not uses_component_scope(cfg, ws):
        return []
    if not membership_settings(cfg)["inherit_from_parent"]:
        return []
    return _cached_keys(cfg, ws, "_resolved_tagged_keys",
                        tagged_issue_selector_jql(cfg, ws))


# ---------------------------------------------------------------------------
#  Membership -> JQL
# ---------------------------------------------------------------------------

def membership_jql(cfg, ws, include):
    """Build the JQL describing this workstream's membership.

    `include` is one of "children", "epics", "everything" (see
    `filters.SCOPE_INCLUDES`). Returns None when the workstream currently has
    nothing to look at.
    """
    project = project_of(cfg, ws)
    components = components_of(ws)
    if not project or not components:
        return None

    settings = membership_settings(cfg)
    epic_keys = get_epic_keys(cfg, ws)
    project_clause = f"project = {filters.quote(project)}"
    epic_types = ", ".join(filters.quote(t) for t in settings["epic_types"])

    if include == "epics":
        if not epic_keys:
            return None
        return f"{project_clause} AND key IN ({', '.join(epic_keys)})"

    # Its own Component always counts.
    parts = [_component_clause(components)]

    if settings["inherit_from_parent"]:
        # `parentEpic` reaches Stories, Tasks, Bugs and their nested Sub-tasks.
        inherited = []
        if epic_keys:
            inherited.append(f"parentEpic IN ({', '.join(epic_keys)})")
        tagged = get_tagged_issue_keys(cfg, ws)
        cap = settings["max_parent_keys"]
        if tagged and cap and len(tagged) > cap:
            print(f"  (note: {len(tagged)} directly tagged issues in "
                  f"{ws.get('abbrev', '?')} — not expanding their sub-tasks; "
                  f"raise membership.max_parent_keys to include them)")
        elif tagged:
            inherited.append(f"parent IN ({', '.join(tagged)})")
        if inherited:
            clause = " OR ".join(inherited)
            if settings["child_component_wins"]:
                # A child that names its own Component is judged on that alone.
                clause = f"({clause}) AND component IS EMPTY"
            parts.append(f"({clause})")

    membership = " OR ".join(parts)

    if include == "children":
        return (f"{project_clause} AND ({membership}) "
                f"AND issuetype NOT IN ({epic_types})")
    if include == "everything":
        if epic_keys:
            membership = f"key IN ({', '.join(epic_keys)}) OR {membership}"
        return f"{project_clause} AND ({membership})"
    raise ValueError(f"Unknown scope include: {include}")


# ---------------------------------------------------------------------------
#  The one call commands make
# ---------------------------------------------------------------------------

def _legacy_filter(ws, scope_name, substitutions):
    """The `*_jql` string an older config may have written for this scope."""
    for field in LEGACY_FIELDS.get(scope_name, []):
        value = ws.get(field)
        if value:
            return value.format(**substitutions) if substitutions else value
    return None


def scope_jql(cfg, ws, scope_name, overrides=None, days=None):
    """Return the executable JQL for one workstream and one command scope.

    `overrides` are run-time scope options (for example a different status);
    `days` is the shorthand for the standup window, which also feeds the
    `{days}` placeholder legacy configs use.

    Returns None when this workstream has nothing in scope, which every command
    reports as a skip rather than treating as an error.
    """
    substitutions = {"days": days} if days is not None else None
    if days is not None:
        overrides = dict(overrides or {})
        overrides.setdefault("updated_within_days", days)

    legacy = _legacy_filter(ws, scope_name, substitutions)

    if not uses_component_scope(cfg, ws):
        # No Components: the workstream is defined by its own JQL, as before.
        return legacy

    include = filters.SCOPE_INCLUDES[scope_name]
    base = membership_jql(cfg, ws, include)
    if not base:
        return None

    options = filters.scope_options(cfg, ws, scope_name, overrides)
    narrowing = [c for c in (filters.compile_scope(options), legacy) if c]
    if not narrowing:
        return base
    return f"({base}) AND " + " AND ".join(f"({c})" for c in narrowing)


def confluence_cql(ws):
    """The Confluence query for this workstream, built from space + labels."""
    return filters.build_cql(ws)
