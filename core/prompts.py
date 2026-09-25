"""Named prompts. Defaults live here; config holds overrides only.

`core.prompts` imports nothing from `core` or `commands`, so any module can
import it. A rendered default is byte-identical to the prompt the code sent
before this registry existed.
"""

import os
import re
import sys


_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")

RUNTIME_DEFAULTS = {
    "audience": "stakeholders",
    "product": "Product",
}


REPORT_SECTION = """\
Write a weekly status note for {audience}.

Use ONLY the CHANGE SUMMARY and the Material. Do not invent people, dates, \
status, or work.

Output exactly these seven headings, in this order, and nothing else:
{headings}

Rules:
1. Each section is 2 to 4 short bullets, or this exact sentence: \
{empty_section}
2. If CHANGE SUMMARY says this is the first run, the first section is \
exactly: {first_run_line}
3. After a fact, cite its tag like [APS-10] or [D1]. Use only tags that \
appear in the Material.
4. Do not add a title, a workstream heading, or a reference list.
5. A dated line under an item is a comment from this window. Use it for \
what changed, decisions, blockers, and risks, and cite that item's tag. \
A comment is not a status change.

Example of one filled section:
### {heading_progress}
- Status endpoint is in review. [APS-10]
- Certificate rotation cadence is decided. [D1]
"""

REPORT_SECTION_TAIL = "Write the seven sections now."

BRIEF_DEBRIEF = """\
Extract decisions and actions from these meeting notes.

Return a JSON object with exactly two keys:
- "decisions": array of {"text": string, "owner": string or ""}
- "actions": array of {"title": string, "owner": string or "",
  "issuetype": {action_types}, "workstream": abbrev or ""}

Use ONLY workstream abbrevs from the list. Do not invent dates.
Extract decisions and actions. Do not write any text outside the JSON object.
"""

INBOX_FILE_NOTE = """\
Suggest how to file this note as a Jira Product Backlog item.

Return a JSON object with exactly these keys:
- "product": a product abbrev from the list, or ""
- "workstream": a workstream abbrev from the list, or ""
- "issuetype": {note_types}
- "title": a clear title
- "criteria": one or two Given/When/Then lines, or ""

Use ONLY abbrevs from the list. Do not invent people or dates.
file this note. Do not write any text outside the JSON object.
"""

REFINE_TITLES = """\
Draft a clearer title for each Jira item. Keep the meaning. Do not invent scope.

Return a JSON array. Each object has exactly two keys:
- "key": the issue key, copied exactly
- "title": the rewritten title

If you would not change a title, omit that item.

Draft a clearer title. Do not write any text outside the JSON array.
"""

REFINE_CRITERIA = """\
Draft testable acceptance criteria for each story that is missing them.

Return a JSON array. Each object has exactly two keys:
- "key": the issue key, copied exactly
- "criteria": 2 to 4 short Given/When/Then lines, separated by newlines

Draft acceptance criteria. Do not write any text outside the JSON array.
"""

REFINE_TAIL = "Return the JSON array now."

REVIEW_TITLES = """\
Flag only Jira titles a teammate cannot understand without opening the ticket.

A good title names the work. Flag a title if it is one or two vague words, \
or if it does not say what will change. Do not flag a title that is already \
clear.

Return a JSON array. Each object has exactly three keys:
- "key": the issue key, copied exactly
- "problem": one short sentence
- "suggestion": a clearer title

If nothing is unclear, return []

Example input:
1. APS-11: Fix stuff
2. APS-10: Publish exchange status endpoint

Example JSON array:
[{"key":"APS-11","problem":"Does not say what to fix.","suggestion":"Fix retry handling in the exchange client"}]

Do not add keys that are not in the list. Do not write any text outside the \
JSON array.
"""

REVIEW_CRITERIA = """\
Flag only stories whose acceptance criteria are missing, vague, or not \
testable. Good criteria state an observable outcome and cover the happy path \
plus one obvious error case. Do not flag a story whose criteria are already \
solid.

Return a JSON array. Each object has exactly three keys:
- "key": the issue key, copied exactly
- "problem": one short sentence
- "missing": the criteria you would add, as one short string

If every story is solid, return []

Example input:
1. APS-20: Rate limiting for public endpoints
   Acceptance criteria / description: (none provided)
2. APS-10: Publish exchange status endpoint
   Acceptance criteria / description: Acceptance criteria: returns current status.

Example JSON array:
[{"key":"APS-20","problem":"No acceptance criteria.","missing":"Given a tenant over the limit, requests are rejected with 429; under the limit, they succeed."}]

Do not add keys that are not in the list. Do not write any text outside the \
JSON array.
"""

RELEASE_NOTES_PROSE = """\
Draft short release notes from the issue list below.

Use only the issues in the list. Do not add, drop, or rename an issue.
Keep the product and workstream groupings. Write prose, not a new list
of keys. Do not invent dates, people, or outcomes that the list does not
state.
"""


def _entry(used_by, explain, text, runtime=(), values=None, headings=None,
           required=(), contract=(), append_at="", version=1):
    return {
        "used_by": used_by,
        "explain": explain,
        "text": text,
        "runtime": tuple(runtime),
        "values": dict(values or {}),
        "headings": tuple(headings or ()),
        "required": tuple(required),
        "contract": tuple(contract),
        "append_at": append_at,
        "version": version,
    }


PROMPTS = {
    "report.section": _entry(
        "pm report, pm warm --report (one call per workstream)",
        "Writes one workstream's section of the weekly report from its "
        "Material. Change the wording or add team rules; keep {headings} so "
        "the report keeps its seven sections.",
        REPORT_SECTION,
        runtime=("audience",),
        values={
            "empty_section": "No update this week.",
            "first_run_line": "First report — no prior week to compare against.",
        },
        headings=(
            ("changed", "What changed since last week"),
            ("progress", "Progress this sprint"),
            ("roadmap", "Roadmap status"),
            ("decisions", "Decisions since last report"),
            ("dependencies", "Open dependencies"),
            ("waiting", "Decisions we are waiting on"),
            ("risks", "Risks"),
        ),
        required=("headings", "empty_section", "first_run_line"),
        append_at="Example of one filled section:",
        version=2,
    ),
    "report.section_tail": _entry(
        "pm report, pm warm --report",
        "Last line of the user message for the weekly section.",
        REPORT_SECTION_TAIL,
    ),
    "brief.debrief": _entry(
        "pm brief --notes",
        "Pulls decisions and actions out of meeting notes. Keep the JSON "
        "keys; the code reads decisions and actions back.",
        BRIEF_DEBRIEF,
        values={"action_types": ["Story", "Task"]},
        contract=("JSON object", '"decisions"', '"actions"', '"title"',
                  '"owner"'),
    ),
    "inbox.file_note": _entry(
        "pm inbox",
        "Suggests where a captured note belongs. Keep the JSON keys.",
        INBOX_FILE_NOTE,
        values={"note_types": ["Story", "Task", "Bug"]},
        contract=("JSON object", '"product"', '"workstream"', '"issuetype"',
                  '"title"', '"criteria"'),
    ),
    "refine.titles": _entry(
        "pm refine",
        "Drafts clearer titles. The code reads key and title from each object.",
        REFINE_TITLES,
        contract=("JSON array", '"key"', '"title"'),
    ),
    "refine.criteria": _entry(
        "pm refine",
        "Drafts acceptance criteria. The code reads key and criteria.",
        REFINE_CRITERIA,
        contract=("JSON array", '"key"', '"criteria"'),
    ),
    "refine.tail": _entry(
        "pm refine",
        "Last line of the user message. The caller adds the blank line before it.",
        REFINE_TAIL,
    ),
    "review.titles": _entry(
        "pm review",
        "Says why a title is unclear and suggests one. The code reads key, "
        "problem and suggestion.",
        REVIEW_TITLES,
        contract=("JSON array", '"key"', '"problem"', '"suggestion"'),
    ),
    "review.criteria": _entry(
        "pm review",
        "Says what acceptance criteria are missing. The code reads key, "
        "problem and missing.",
        REVIEW_CRITERIA,
        contract=("JSON array", '"key"', '"problem"', '"missing"'),
    ),
    "review.titles_tail": _entry(
        "pm review",
        "Last line of the titles user message.",
        "Return the JSON array now.",
    ),
    "review.criteria_tail": _entry(
        "pm review",
        "Last line of the criteria user message.",
        "Return the JSON array now.",
    ),
    "release_notes.prose": _entry(
        "pm release-notes",
        "Turns the done list into prose.",
        RELEASE_NOTES_PROSE,
    ),
}


def render(template, values):
    """Replace {name} for names in `values`. Turn {{ into { and }} into }.

    Every other brace is left alone, so a JSON example in a prompt is safe.
    """
    protected = template.replace("{{", "\x00").replace("}}", "\x01")

    def repl(match):
        name = match.group(1)
        if name in values:
            return str(values[name])
        return match.group(0)

    out = _PLACEHOLDER.sub(repl, protected)
    return out.replace("\x00", "{").replace("\x01", "}")


def _fail(message):
    sys.exit(message)


def _known(entry):
    names = set(entry["runtime"]) | set(entry["values"])
    if entry["headings"]:
        names.add("headings")
        names.update(f"heading_{role}" for role, _text in entry["headings"])
    return names


def _oxford(items):
    parts = [str(item) for item in items]
    if len(parts) <= 1:
        return parts[0] if parts else ""
    if len(parts) == 2:
        return f"{parts[0]} or {parts[1]}"
    return ", ".join(parts[:-1]) + f", or {parts[-1]}"


def _format_value(name, value):
    if name == "action_types":
        return " or ".join(f'"{item}"' for item in value)
    if name == "note_types":
        return _oxford(value)
    if name == "kinds":
        return ", ".join(str(item) for item in value)
    return value


def _heading_pairs(entry, override):
    roles = [role for role, _text in entry["headings"]]
    texts = {role: text for role, text in entry["headings"]}
    if override:
        if not isinstance(override, dict):
            _fail(f"prompts: values.headings must be a mapping of role to text.")
        for role, text in override.items():
            if role not in texts:
                _fail(f"prompts: unknown heading role {role}. "
                      f"Known: {', '.join(roles)}.")
            if not isinstance(text, str) or not text.strip():
                _fail(f"prompts: heading {role} must be a non-empty string.")
            texts[role] = text
    return [(role, texts[role]) for role in roles]


def _render_values(entry, raw_values, pairs, runtime):
    merged = dict(entry["values"])
    merged.update(raw_values or {})
    values = {name: _format_value(name, value) for name, value in merged.items()}
    if pairs:
        values["headings"] = "\n".join(f"### {text}" for _role, text in pairs)
        for role, text in pairs:
            values[f"heading_{role}"] = text
    for name in entry["runtime"]:
        if name in (runtime or {}):
            values[name] = runtime[name]
    return values


def _check_template(prompt_id, entry, template):
    known = _known(entry)
    found = set(_PLACEHOLDER.findall(template))
    unknown = sorted(found - known)
    if unknown:
        _fail(f"prompts.{prompt_id}: unknown placeholder {{{unknown[0]}}}. "
              f"Known: {', '.join(sorted(known))}. "
              f"Write {{{{{unknown[0]}}}}} for a literal brace.")
    for name in entry["required"]:
        if name not in found:
            _fail(f"prompts.{prompt_id}: the text must keep {{{name}}} — "
                  f"{entry['explain']}")
    runtime = {name: RUNTIME_DEFAULTS.get(name, name) for name in entry["runtime"]}
    pairs = list(entry["headings"])
    rendered = render(template, _render_values(entry, {}, pairs, runtime))
    for token in entry["contract"]:
        if token not in rendered:
            _fail(f'prompts.{prompt_id}: the text must contain "{token}"; '
                  f"the code reads it back.")


def _insert_append(text, addition, marker):
    block = addition.strip("\n")
    lines = text.split("\n")
    if marker:
        for index, line in enumerate(lines):
            if line.startswith(marker):
                head = lines[:index]
                if head and head[-1] != "":
                    head.append("")
                return "\n".join(head + [block, ""] + lines[index:])
    body = text.rstrip("\n")
    return f"{body}\n\n{block}\n"


def _one_newline(text):
    return text.rstrip("\n") + "\n"


def _resolved(cfg):
    if cfg and isinstance(cfg.get("_prompts"), dict):
        return cfg["_prompts"]
    return None


def effective(cfg, prompt_id):
    """The stored record, or the built-in one when config has not resolved it."""
    resolved = _resolved(cfg)
    if resolved is not None and prompt_id in resolved:
        return resolved[prompt_id]
    entry = PROMPTS.get(prompt_id)
    if entry is None:
        _fail(f"prompts: unknown id {prompt_id}. "
              f"Known: {', '.join(sorted(PROMPTS))}.")
    return {
        "text": entry["text"],
        "values": dict(entry["values"]),
        "headings": list(entry["headings"]),
        "source": "built-in",
        "based_on": None,
        "parts": [],
    }


def get(cfg, prompt_id, **runtime):
    """The effective prompt text, rendered. cfg may be None (built-in)."""
    record = effective(cfg, prompt_id)
    entry = PROMPTS[prompt_id]
    pairs = record["headings"]
    values = _render_values(
        {**entry, "_id": prompt_id}, record["values"], pairs, runtime)
    return render(record["text"], values)


def headings(cfg, prompt_id="report.section"):
    """Tuple of heading texts in role order, after config overrides."""
    return tuple(text for _role, text in effective(cfg, prompt_id)["headings"])


def heading(cfg, prompt_id, role):
    """One heading's text by role."""
    for name, text in effective(cfg, prompt_id)["headings"]:
        if name == role:
            return text
    _fail(f"prompts.{prompt_id}: unknown heading role {role}.")


def values_of(cfg, prompt_id):
    """The effective `values` dict (defaults, then config)."""
    return dict(effective(cfg, prompt_id)["values"])


def source(cfg, prompt_id):
    """'built-in', 'config', or 'file <path>'."""
    return effective(cfg, prompt_id)["source"]


def _read_override(cfg, prompt_id, spec, entry):
    if not isinstance(spec, dict):
        _fail(f"prompts.{prompt_id}: must be a mapping.")
    allowed = {"text", "file", "append", "values", "based_on"}
    unknown = sorted(set(spec) - allowed)
    if unknown:
        _fail(f"prompts.{prompt_id}: unknown key {unknown[0]}. "
              f"Use text, file, append, values, based_on.")
    if spec.get("text") is not None and spec.get("file") is not None:
        _fail(f"prompts.{prompt_id}: set text or file, not both.")

    template = entry["text"]
    origin = "built-in"
    parts = []
    if spec.get("file"):
        path = spec["file"]
        if not isinstance(path, str) or not path.strip():
            _fail(f"prompts.{prompt_id}: file must be a path.")
        root = os.path.dirname(os.path.abspath(cfg.get("_config_path") or ""))
        full = path if os.path.isabs(path) else os.path.join(root, path)
        try:
            with open(full, encoding="utf-8") as fh:
                template = _one_newline(fh.read())
        except OSError:
            _fail(f"prompts.{prompt_id}: cannot read {path}.")
        origin = f"file {path}"
        parts.append("file")
    elif spec.get("text") is not None:
        if not isinstance(spec["text"], str):
            _fail(f"prompts.{prompt_id}: text must be a string.")
        template = _one_newline(spec["text"])
        origin = "config"
        parts.append("text")

    if spec.get("append") is not None:
        if not isinstance(spec["append"], str):
            _fail(f"prompts.{prompt_id}: append must be a string.")
        template = _insert_append(template, spec["append"], entry["append_at"])
        if origin == "built-in":
            origin = "config"
        parts.append("append")

    raw_values = {}
    pairs = list(entry["headings"])
    if spec.get("values") is not None:
        values = spec["values"]
        if not isinstance(values, dict):
            _fail(f"prompts.{prompt_id}: values must be a mapping.")
        heading_override = values.get("headings")
        for name, value in values.items():
            if name == "headings":
                continue
            if name not in entry["values"]:
                _fail(f"prompts.{prompt_id}: unknown value {name}. "
                      f"Known: {', '.join(sorted(entry['values'])) or '(none)'}.")
            raw_values[name] = value
        if heading_override is not None:
            pairs = _heading_pairs(entry, heading_override)
            parts.append("headings")
        if raw_values or heading_override is not None:
            if origin == "built-in":
                origin = "config"
            if raw_values:
                parts.append("values")

    based_on = spec.get("based_on")
    if based_on is not None and not isinstance(based_on, int):
        _fail(f"prompts.{prompt_id}: based_on must be a whole number.")

    merged_values = dict(entry["values"])
    merged_values.update(raw_values)
    _check_template(prompt_id, {**entry, "headings": pairs}, template)
    return {
        "text": template,
        "values": merged_values,
        "headings": pairs,
        "source": origin,
        "based_on": based_on,
        "parts": parts,
    }


def validate_config(cfg):
    """Resolve overrides and store them on cfg['_prompts']. Exit on the first problem."""
    block = cfg.get("prompts") or {}
    if not isinstance(block, dict):
        _fail("`prompts:` must be a mapping of prompt id to overrides.")
    resolved = {}
    for prompt_id, entry in PROMPTS.items():
        spec = block.get(prompt_id)
        if not spec:
            resolved[prompt_id] = {
                "text": entry["text"],
                "values": dict(entry["values"]),
                "headings": list(entry["headings"]),
                "source": "built-in",
                "based_on": None,
                "parts": [],
            }
            continue
        resolved[prompt_id] = _read_override(cfg, prompt_id, spec, entry)
    unknown = sorted(set(block) - set(PROMPTS))
    if unknown:
        _fail(f"prompts: unknown id {unknown[0]}. "
              f"Known: {', '.join(sorted(PROMPTS))}.")
    cfg["_prompts"] = resolved
