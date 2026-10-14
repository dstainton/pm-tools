"""Portable status disposition policy for whole-project backlog assessment.

Classification uses *project-available status IDs*, not guessed JQL status names.
The three resulting populations are mutually exclusive and exhaustive.
"""
from core import queries, sources

DEFAULT_EXCLUDED = (
    "Cancelled", "Canceled", "Rejected", "Duplicate", "Won't Do",
    "Wont Do", "Won't Fix", "Wont Fix", "Abandoned", "Obsolete",
)
KEYS = ("active", "completed", "excluded")


def _names(value, label):
    if value is None:
        return []
    if not isinstance(value, list) or any(
            not isinstance(v, str) or not v.strip() for v in value):
        raise ValueError("{} must be a list of nonblank status names".format(label))
    return [v.strip() for v in value]


def _policy(cfg, project):
    block = (cfg.get("assessment") or {}).get("dispositions") or {}
    if not isinstance(block, dict):
        raise ValueError("assessment.dispositions must be a mapping")
    if set(block) - set(KEYS) - {"projects"}:
        raise ValueError("unknown assessment.dispositions option")
    project_blocks = block.get("projects") or {}
    if not isinstance(project_blocks, dict):
        raise ValueError("assessment.dispositions.projects must be a mapping")
    override = project_blocks.get(project) or {}
    if not isinstance(override, dict) or set(override) - set(KEYS):
        raise ValueError("project disposition override must contain active, completed, or excluded")
    policy = {}
    for key in KEYS:
        # Explicit list replaces defaults at its own level; no implicit additions.
        default = list(DEFAULT_EXCLUDED) if key == "excluded" else []
        policy[key] = _names(override.get(key, block.get(key, default)),
                             "assessment.dispositions." + key)
    return policy


def validate(cfg):
    """Validate configuration shape without querying Jira."""
    assessment = cfg.get("assessment") or {}
    if not isinstance(assessment, dict) or set(assessment) - {"dispositions"}:
        raise ValueError("assessment must contain only dispositions")
    block = assessment.get("dispositions") or {}
    if not isinstance(block, dict) or set(block) - set(KEYS) - {"projects"}:
        raise ValueError("assessment.dispositions has unknown or invalid settings")
    for kind in KEYS:
        if kind in block:
            _names(block[kind], "assessment.dispositions." + kind)
    projects = block.get("projects") or {}
    if not isinstance(projects, dict):
        raise ValueError("assessment.dispositions.projects must be a mapping")
    for project, override in projects.items():
        if not isinstance(project, str) or not project.strip():
            raise ValueError("assessment.dispositions.projects keys must be project names")
        if not isinstance(override, dict) or set(override) - set(KEYS):
            raise ValueError("Invalid project disposition override for " + project)
        for kind, values in override.items():
            _names(values, "assessment.dispositions.projects." + project + "." + kind)


def resolve(cfg, project):
    """Discover project statuses and produce exact JQL for each disposition.

    Explicit excluded > completed > active; remaining statuses are assigned
    using statusCategory Done versus non-Done. Invalid explicit names fail.
    """
    policy = _policy(cfg, project)
    statuses = sources.fetch_project_statuses(cfg["jira"], project)
    if not statuses:
        raise ValueError("No statuses returned for project {}; cannot assess safely".format(project))
    known = {}
    for row in statuses:
        ident = str(row.get("id") or "")
        if not ident.isdigit() or not row.get("name"):
            raise ValueError("Malformed Jira project status for {}".format(project))
        known[ident] = row
    names = {str(row["name"]).casefold() for row in known.values()}
    for kind in KEYS:
        missing = sorted({name for name in policy[kind]
                          if name.casefold() not in names})
        # Missing built-in aliases are normal; custom values must exist.
        supplied = ((cfg.get("assessment") or {}).get("dispositions") or {})
        project_override = (supplied.get("projects") or {}).get(project) or {}
        if kind in project_override or kind in supplied:
            if missing:
                raise ValueError("Unknown {} status(es) for {}: {}".format(
                    kind, project, ", ".join(missing)))
    explicit = {kind: {x.casefold() for x in policy[kind]} for kind in KEYS}
    populations = {kind: [] for kind in KEYS}
    for ident, row in known.items():
        name = row["name"].casefold()
        category = str(row.get("category") or "").casefold()
        if name in explicit["excluded"]:
            kind = "excluded"
        elif name in explicit["completed"]:
            kind = "completed"
        elif name in explicit["active"]:
            kind = "active"
        elif category == "done":
            kind = "completed"
        elif category in ("new", "indeterminate", "to do", "in progress"):
            kind = "active"
        else:
            raise ValueError("Unknown Jira status category for {}: {}".format(
                row["name"], category))
        populations[kind].append(ident)
    base = "project = {}".format(queries.quote(project))
    jql = {}
    for kind in KEYS:
        ids = sorted(populations[kind], key=int)
        jql[kind] = base + (" AND status IN ({})".format(", ".join(ids))
                            if ids else " AND statusCategory = Done AND statusCategory != Done")
    return {"jql": jql, "policy": policy,
            "status_names": {kind: sorted({known[x]["name"] for x in ids})
                             for kind, ids in populations.items()}}
