"""Named JQL and CQL fragments. Defaults live here; config holds overrides.

`core.queries` imports nothing from `core`. `filters` imports this module.
"""

import datetime as dt
import re
import sys


_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
_ISSUE_KEY = re.compile(r"^[A-Z][A-Z0-9_]*-\d+$")

# name -> (kind). Vocabulary names are filled from vocabulary().
_KINDS = {
    "project": "string", "space": "string", "version": "string",
    "label": "string", "field_name": "string",
    "values": "list", "components": "list", "labels": "list",
    "epic_types": "list", "types": "list",
    "keys": "keys", "epic_keys": "keys", "tagged_keys": "keys",
    "sprint_id": "int", "days": "int",
    "page_id": "page",
    "since": "date",
    "field": "field",
    "base": "clause", "anchor": "clause", "cql": "clause", "window": "clause",
    "status_open": "vocab", "status_done": "vocab", "sprint_open": "vocab",
}

_VOCAB_OPTION = {
    "status_open": ("status", "open"),
    "status_done": ("status", "done"),
    "sprint_open": ("sprint", "open"),
}


def quote(value):
    """Quote a JQL string literal safely enough for config-provided names."""
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def _entry(lang, used_by, explain, text, required=()):
    return {
        "lang": lang,
        "used_by": used_by,
        "explain": explain,
        "text": text,
        "required": tuple(required),
    }


# Fragments with no placeholders are the vocabulary. `any` is not overridable.
QUERIES = {
    "status.open": _entry("jql", "scopes (status: open), pm coverage, pm doctor, pm today",
                          "What 'open' means: not in the Done status category.",
                          "statusCategory != Done"),
    "status.done": _entry("jql", "scopes (status: done), pm release-notes",
                          "What 'done' means: the Done status category.",
                          "statusCategory = Done"),
    "status.in-progress": _entry("jql", "scopes (status: in-progress)",
                                 "The In Progress status category.",
                                 'statusCategory = "In Progress"'),
    "status.todo": _entry("jql", "scopes (status: todo)",
                          "The To Do status category.",
                          'statusCategory = "To Do"'),
    "sprint.open": _entry("jql", "scopes (sprint: open), pm today",
                          "Issues in a Sprint that is open.",
                          "sprint in openSprints()"),
    "sprint.future": _entry("jql", "scopes (sprint: future)",
                            "Issues in a Sprint that has not started.",
                            "sprint in futureSprints()"),
    "sprint.none": _entry("jql", "scopes (sprint: none)",
                          "Issues in no Sprint.",
                          "sprint IS EMPTY"),
    "sprint.by_id": _entry("jql", "scopes when sprint is a number",
                           "Issues in one Sprint, by its id.",
                           "sprint = {sprint_id}", ("sprint_id",)),
    "assignee.me": _entry("jql", "scopes (assignee: me)",
                          "Issues assigned to the authenticated user.",
                          "assignee = currentUser()"),
    "assignee.unassigned": _entry("jql", "scopes (assignee: unassigned)",
                                  "Issues with no assignee.",
                                  "assignee IS EMPTY"),
    "assignee.assigned": _entry("jql", "scopes (assignee: assigned)",
                                "Issues that have an assignee.",
                                "assignee IS NOT EMPTY"),
    "membership.anchor.component": _entry(
        "jql", "workstream membership when membership.by is component",
        "The workstream's own Components.",
        "component IN ({values})", ("values",)),
    "membership.anchor.label": _entry(
        "jql", "workstream membership when membership.by is label",
        "The workstream's own labels.",
        "labels IN ({values})", ("values",)),
    "membership.anchor.field": _entry(
        "jql", "workstream membership when membership.by is field",
        "A custom field naming the workstream.",
        "{field} IN ({values})", ("field", "values")),
    "membership.epics": _entry(
        "jql", "which Epics anchor a workstream",
        "Epics that carry the workstream's anchor.",
        "project = {project} AND issuetype IN ({epic_types}) AND {anchor}",
        ("project", "epic_types", "anchor")),
    "membership.tagged": _entry(
        "jql", "non-Epic issues that carry the anchor themselves",
        "Issues other than Epics that carry the workstream's anchor.",
        "project = {project} AND issuetype NOT IN ({epic_types}) AND {anchor}",
        ("project", "epic_types", "anchor")),
    "membership.inherit.epic": _entry(
        "jql", "how a child finds its Epic",
        "Children of the workstream's Epics. A company-managed project on the "
        "old Epic Link may use \"Epic Link\" IN ({epic_keys}).",
        "parentEpic IN ({epic_keys})", ("epic_keys",)),
    "membership.inherit.parent": _entry(
        "jql", "how a Sub-task inherits from a tagged parent",
        "Sub-tasks of issues that carry the anchor themselves.",
        "parent IN ({tagged_keys})", ("tagged_keys",)),
    "membership.own_empty.component": _entry(
        "jql", "child_component_wins in component mode",
        "A child with no Component of its own.",
        "component IS EMPTY"),
    "membership.own_empty.field": _entry(
        "jql", "child_component_wins in field mode",
        "A child with no value in the membership field.",
        "{field} IS EMPTY", ("field",)),
    "coverage.open_in_project": _entry(
        "jql", "pm coverage, pm doctor (unclaimed work)",
        "Open work in a project, before workstreams are applied.",
        "project = {project} AND {status_open}", ("project",)),
    "doctor.membership_open": _entry(
        "jql", "pm doctor",
        "The workstream's membership, limited to open issues.",
        "({base}) AND ({status_open})", ("base",)),
    "release_notes.done": _entry(
        "jql", "pm release-notes",
        "Done work in a project inside the release window.",
        "project = {project} AND {status_done} AND ({window})",
        ("project", "window")),
    "release_notes.since": _entry(
        "jql", "pm release-notes --since",
        "Issues resolved on or after a date.",
        'resolved >= "{since}"', ("since",)),
    "release_notes.version": _entry(
        "jql", "pm release-notes --version",
        "Issues in one fixVersion.",
        "fixVersion = {version}", ("version",)),
    "today.in_sprint_open": _entry(
        "jql", "pm today",
        "Open issues in the open Sprint of a project.",
        "project = {project} AND {sprint_open} AND {status_open}",
        ("project",)),
    "confluence.space": _entry(
        "cql", "every Confluence read",
        "Pages in one space.",
        "space = {space}", ("space",)),
    "confluence.labels": _entry(
        "cql", "labelled Confluence reads",
        "Pages carrying one of these labels.",
        "label IN ({labels})", ("labels",)),
    "confluence.window": _entry(
        "cql", "every Confluence read",
        "Only pages modified on or after a date.",
        "({cql}) AND lastmodified >= '{since}'", ("cql", "since")),
    "epics.children": _entry(
        "jql", "pm report epic progress",
        "Direct children of these Epics.",
        "parent IN ({keys})", ("keys",)),
    "epics.resolved": _entry(
        "jql", "pm report epics finished in the window",
        "Epics in the workstream that were resolved inside the window.",
        '({base}) AND {status_done} AND resolved >= "{since}"', ("base", "since")),
    "brief.risk_pages": _entry(
        "cql", "pm brief",
        "Pages the workstream labelled as risks.",
        "space = {space} AND label = {label}", ("space", "label")),
}

VOCAB = {
    "status": ("status.open", "status.done", "status.in-progress", "status.todo"),
    "sprint": ("sprint.open", "sprint.future", "sprint.none"),
    "assignee": ("assignee.me", "assignee.unassigned", "assignee.assigned"),
}


def _fail(message):
    sys.exit(message)


def _templates(cfg):
    if cfg and isinstance(cfg.get("_queries"), dict):
        return cfg["_queries"]
    return {qid: entry["text"] for qid, entry in QUERIES.items()}


def template(cfg, query_id):
    texts = _templates(cfg)
    if query_id not in texts:
        if query_id not in QUERIES and not _is_added_vocab(query_id):
            _fail(f"queries: unknown id {query_id}.")
        # An added vocabulary value is stored only when config resolved it.
        if query_id not in texts:
            _fail(f"queries: unknown id {query_id}.")
    return texts[query_id]


def _is_added_vocab(query_id):
    option, _, value = _split_vocab(query_id)
    return option is not None and value not in ("any",)


def _split_vocab(query_id):
    if "." not in query_id:
        return None, None, None
    option, value = query_id.split(".", 1)
    if option not in VOCAB and option not in ("status", "sprint", "assignee"):
        return None, None, None
    return option, query_id, value


def source(cfg, query_id):
    if cfg and isinstance(cfg.get("_query_sources"), dict):
        return cfg["_query_sources"].get(query_id, "built-in")
    return "built-in"


def vocabulary(cfg, option):
    """{value: fragment} for status, sprint or assignee. 'any' is always None."""
    table = {"any": None}
    if option not in VOCAB:
        raise ValueError(f"unknown vocabulary {option}")
    for qid in VOCAB[option]:
        value = qid.split(".", 1)[1]
        table[value] = template(cfg, qid)
    texts = _templates(cfg)
    prefix = option + "."
    for qid, text in texts.items():
        if qid.startswith(prefix) and qid not in VOCAB[option]:
            table[qid.split(".", 1)[1]] = text
    return table


def _render_placeholder(name, value, cfg):
    kind = _KINDS.get(name)
    if kind is None:
        raise ValueError(f"unknown placeholder {{{name}}}")
    if kind == "string":
        if value is None or str(value) == "":
            raise ValueError(f"{name} must be a non-empty string")
        return quote(value)
    if kind == "list":
        if isinstance(value, str):
            value = [value]
        if not value:
            raise ValueError(f"{name} must be a non-empty list")
        return ", ".join(quote(item) for item in value)
    if kind == "keys":
        keys = list(value or [])
        if not keys:
            raise ValueError(f"{name} must be a non-empty list of issue keys")
        for key in keys:
            if not _ISSUE_KEY.match(str(key)):
                raise ValueError(f"{name}: {key!r} is not an issue key")
        return ", ".join(str(key) for key in keys)
    if kind == "int":
        return str(int(value))
    if kind == "page":
        if not re.fullmatch(r"\d+", str(value)):
            raise ValueError(f"{name} must be digits")
        return str(value)
    if kind == "date":
        dt.date.fromisoformat(str(value))
        return str(value)
    if kind == "field":
        text = str(value)
        if re.fullmatch(r"cf\[\d+\]", text):
            return text
        return quote(text)
    if kind == "clause":
        return str(value)
    if kind == "vocab":
        option, key = _VOCAB_OPTION[name]
        return vocabulary(cfg, option)[key]
    raise ValueError(f"cannot render {{{name}}}")


def render(cfg, query_id, **values):
    """Effective template, rendered by placeholder type. cfg may be None."""
    text = template(cfg, query_id)
    entry = QUERIES.get(query_id)
    known = set(_PLACEHOLDER.findall(QUERIES[query_id]["text"])) if entry else set(_PLACEHOLDER.findall(text))

    def repl(match):
        name = match.group(1)
        if entry and name not in known and name not in values:
            raise ValueError(f"queries.{query_id}: unknown placeholder {{{name}}}")
        if name not in values and _KINDS.get(name) != "vocab":
            raise ValueError(f"queries.{query_id}: missing {{{name}}}")
        try:
            if _KINDS.get(name) == "vocab":
                return _render_placeholder(name, None, cfg)
            return _render_placeholder(name, values.get(name), cfg)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"queries.{query_id}: {{{name}}}: {exc}") from exc

    return _PLACEHOLDER.sub(repl, text)


def validate_config(cfg):
    """Unknown ids, bad placeholders, and vocabulary cycles. Stores cfg['_queries']."""
    block = cfg.get("queries") or {}
    if not isinstance(block, dict):
        _fail("`queries:` must be a mapping of query id to a template.")
    texts = {qid: entry["text"] for qid, entry in QUERIES.items()}
    sources = {qid: "built-in" for qid in QUERIES}
    for qid, spec in block.items():
        text = spec.get("text") if isinstance(spec, dict) else spec
        if not isinstance(text, str) or not text.strip():
            _fail(f"queries.{qid}: set `text:` to the JQL or CQL fragment.")
        option, _full, value = _split_vocab(qid)
        if qid not in QUERIES and option is None:
            _fail(f"queries: unknown id {qid}. "
                  f"Add a {qid.split('.')[0]} value as `{qid}:` under queries, "
                  f"or use one of: {', '.join(sorted(QUERIES))}.")
        if value == "any":
            _fail(f"queries.{qid}: 'any' means no filter and cannot be overridden.")
        default = QUERIES[qid]["text"] if qid in QUERIES else ""
        known = set(_PLACEHOLDER.findall(default)) if qid in QUERIES else set()
        found = set(_PLACEHOLDER.findall(text))
        if qid in QUERIES:
            extra = sorted(found - known)
            if extra:
                _fail(f"queries.{qid}: unknown placeholder {{{extra[0]}}}. "
                      f"Known: {', '.join(sorted(known)) or '(none)'}.")
            missing = [name for name in QUERIES[qid]["required"] if name not in found and name not in _VOCAB_OPTION]
            # required names must still be present when the default uses them
            for name in QUERIES[qid]["required"]:
                if name not in found and _KINDS.get(name) != "vocab":
                    _fail(f"queries.{qid}: the text must keep {{{name}}}.")
        if option is not None:
            for name in found:
                if name in _VOCAB_OPTION or name.startswith("status_") or name.startswith("sprint_"):
                    _fail(f"queries.{qid}: a vocabulary entry cannot use {{{name}}} "
                          f"(that would cycle).")
        texts[qid] = text.strip()
        sources[qid] = "config"
    cfg["_queries"] = texts
    cfg["_query_sources"] = sources
