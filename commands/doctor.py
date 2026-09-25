"""`pm doctor` — verify the setup, and name the fix when something is wrong.

  pm doctor
  pm doctor --discover-fields

Checks, in order: the config, Jira credentials, every product/workstream
project, the custom-field IDs lint depends on, membership (including
unclaimed work), the project's status list, the local model, and both
caches (Jira fetches and model replies).

`--discover-fields` lists fields whose names look like story points, start
date, acceptance criteria or Epic Link, and prints a YAML snippet.
`--discover-fields --yes` writes a blank field ID. It does not replace one
that is already set.
"""

import os
import re
import sys

from core import cache as cache_core
from core import model_cache
from core import statuses as status_core
from core import config_edit
from core import filters
from core import queries
from core import migrations
from core import model as model_core
from core import products as product_core
from core import sources
from core import workstreams as ws_core


def _status_line(label, detail, status):
    """Keep the status word in column 66. A long path wraps underneath."""
    detail = " ".join(str(detail or "").split())
    if len(detail) <= 48:
        print(f"  {label:<16}{detail:<48} {status}")
        return
    print(f"  {label:<16}{'':<48} {status}")
    print(f"  {'':<16}{detail}")


def _ok(label, detail):
    _status_line(label, detail, "ok")
    return 0


def _warn(label, detail):
    _status_line(label, detail, "warn")
    return 0


def _fail(label, detail):
    _status_line(label, detail, "FAIL")
    return 1


def _projects_in_play(cfg):
    """Unique Jira project keys the current workstreams will query."""
    keys = []
    seen = set()
    for ws in cfg.get("_workstreams") or cfg.get("workstreams") or []:
        project = ws_core.project_of(cfg, ws)
        if project and project not in seen:
            seen.add(project)
            keys.append(project)
    for product in product_core.listed_products(cfg):
        project = product.get("project")
        if project and project not in seen:
            seen.add(project)
            keys.append(project)
    default = (cfg.get("jira") or {}).get("project")
    if default and default not in seen:
        keys.append(default)
    return keys


def _field_by_id(fields, field_id):
    if not field_id:
        return None
    for field in fields:
        if field.get("id") == field_id:
            return field
    return None


def _check_version(cfg):
    try:
        installed = migrations.template_version()
    except OSError:
        return _warn("config version", "bundled template is missing")
    have = cfg.get("config_version")
    if not isinstance(have, int):
        have = 0
    if have < installed:
        return _fail("config version",
                     f"{have} is behind {installed} — run pm update")
    return _ok("config version", str(have))


def _check_config(cfg):
    path = cfg.get("_config_path") or "(unknown)"
    n_products = len(product_core.listed_products(cfg))
    n_streams = len(cfg.get("workstreams") or [])
    detail = f"{path} — {n_products} product(s), {n_streams} workstream(s)"
    return _ok("config", detail)


def _check_jira(cfg):
    try:
        me = sources.fetch_myself(cfg["jira"])
    except Exception as err:                       # noqa: BLE001
        return _fail("jira", f"cannot connect ({err})"), None
    name = me.get("displayName") or me.get("emailAddress") or "connected"
    return _ok("jira", f"connected as {name}"), me


def _check_projects(cfg):
    problems = 0
    bits = []
    for project in _projects_in_play(cfg):
        try:
            sources.fetch_project(cfg["jira"], project)
            bits.append(f"{project} ok")
        except Exception as err:                   # noqa: BLE001
            bits.append(f"{project} MISSING")
            problems += 1
            _ = err
    detail = " · ".join(bits) if bits else "(no project configured)"
    if problems:
        return _fail("projects", detail)
    return _ok("projects", detail)


def _check_custom_fields(cfg, fields):
    jira = cfg.get("jira") or {}
    problems = 0
    first = True
    pairs = [
        ("story points", jira.get("story_points_field"), True),
        ("start date", jira.get("start_date_field"), False),
        ("acceptance criteria", jira.get("acceptance_criteria_field"), False),
        ("epic / parent", jira.get("epic_link_field") or "parent", False),
    ]

    def emit(fn, detail):
        nonlocal first, problems
        label = "custom fields" if first else ""
        first = False
        problems += fn(label, detail)

    for name, field_id, required in pairs:
        if not field_id:
            emit(_fail if required else _warn, f"{name} (not configured)")
            continue
        if field_id == "parent" or _field_by_id(fields, field_id):
            emit(_ok, f"{name} {field_id}")
            continue
        emit(_fail if required else _warn, f"{name} {field_id}  MISSING")
    return problems


def _membership_jql(cfg, ws):
    if not ws_core.uses_component_scope(cfg, ws):
        return ws_core.scope_jql(cfg, ws, "lint")
    base = ws_core.membership_jql(cfg, ws, "everything")
    if not base:
        return None
    return queries.render(cfg, "doctor.membership_open", base=base)


def _check_membership(cfg):
    streams = cfg.get("_workstreams") or cfg.get("workstreams") or []
    bits = []
    claimed = set()
    problems = 0
    for product, group in product_core.group_workstreams(cfg, streams):
        total = 0
        for ws in group:
            jql = _membership_jql(cfg, ws)
            if not jql:
                continue
            try:
                keys = sources.fetch_jira_keys(cfg["jira"], jql)
            except Exception as err:               # noqa: BLE001
                bits.append(f"{ws.get('abbrev')} ERR")
                problems += 1
                _ = err
                continue
            claimed.update(keys)
            total += len(keys)
        bits.append(f"{product.get('abbrev')} {total}")

    unclaimed = 0
    for project in _projects_in_play(cfg):
        jql = queries.render(cfg, "coverage.open_in_project", project=project)
        try:
            keys = set(sources.fetch_jira_keys(cfg["jira"], jql))
        except Exception:
            continue
        unclaimed += len(keys - claimed)

    if unclaimed:
        bits.append(f"unclaimed {unclaimed}")
        _warn("membership", " · ".join(bits))
        return problems
    if problems:
        return _fail("membership", " · ".join(bits) or "could not count")
    return _ok("membership", " · ".join(bits) or "no workstreams")


def _check_model(cfg):
    model_cfg = cfg.get("model") or {}
    if not model_cfg.get("endpoint"):
        return _warn("model", "no model.endpoint configured")
    ok, detail = model_core.ping(model_cfg)
    name = model_cfg.get("name") or "model"
    text = f"{name} {detail}"
    return _ok("model", text) if ok else _warn("model", text)


def _check_cache(cfg):
    path, count, state = cache_core.status_line(cfg)
    detail = f"{path}, {count} entries, {state}"
    model_path, model_count, model_state = model_cache.status_line(
        cfg.get("model") or {})
    if model_path:
        detail += f"; model {model_count} {model_state}"
    if state == "disabled":
        return _warn("cache", detail)
    return _ok("cache", detail)


def _check_statuses(cfg):
    """How many statuses resolved to a category, and where we fell back."""
    projects = _projects_in_play(cfg)
    if not projects:
        return _ok("statuses", "no projects")
    bits = []
    fallback = 0
    for project in projects:
        _index, detail = status_core.load_index(cfg["jira"], project)
        if detail.startswith("unavailable"):
            fallback += 1
            bits.append(f"{project} name fallback")
        else:
            bits.append(f"{project} {detail}")
    text = " · ".join(bits)
    if fallback:
        return _warn("statuses", text)
    return _ok("statuses", text)


FIELD_HINTS = (
    ("story_points_field", re.compile(r"story\s*point", re.I)),
    ("start_date_field", re.compile(r"start\s*date", re.I)),
    ("acceptance_criteria_field", re.compile(r"acceptance\s*criteria", re.I)),
    ("epic_link_field", re.compile(r"epic\s*link", re.I)),
)


def _discover_fields(cfg, fields, write):
    print("\nField discovery:\n")
    suggested = {}
    for key, pattern in FIELD_HINTS:
        if key == "epic_link_field":
            continue
        matches = [f for f in fields if pattern.search(f.get("name") or "")]
        print(f"  {key}:")
        if not matches:
            print("    (none whose name looks like it)")
            continue
        for field in matches[:8]:
            print(f"    {field.get('id')}    {field.get('name')}")
        suggested[key] = matches[0].get("id")
    if suggested:
        print("\n  Suggested snippet:")
        for key, value in suggested.items():
            print(f'    {key}: "{value}"')
    print("\n  Current Jira Cloud hierarchy uses parent, not Epic Link.")
    print('  Leave epic_link_field: "parent" unless you still need the legacy field.')
    if not suggested:
        return
    path = cfg.get("_config_path")
    if not path or not os.path.exists(path):
        print("\n  No config file to update.")
        return
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    preview = text
    notes = []
    for key, value in suggested.items():
        preview, status = config_edit.set_jira_field_if_blank(preview, key, value)
        if status == "written":
            notes.append(f"{key} -> {value}")
        elif status == "kept":
            notes.append(f"{key} already set; left unchanged")
    for note in notes:
        print(f"  {note}")
    if not write:
        print("\n  Nothing was written. Re-run with --yes to fill blank IDs.")
        return
    if preview == text:
        print("\n  No blank field IDs to write.")
        return
    folder = os.path.dirname(path) or "."
    tmp = os.path.join(folder, f".{os.path.basename(path)}.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(preview)
    os.replace(tmp, path)
    print(f"\n  Wrote blank field IDs in {path}.")


def _prompt_report(cfg, only=None):
    """Print prompt sources. Returns 1 when an id is unknown."""
    from core import prompts
    if only and only != "all":
        if only not in prompts.PROMPTS:
            print(f"Unknown prompt {only}. Known: {', '.join(sorted(prompts.PROMPTS))}",
                  file=sys.stderr)
            return 1
        entry = prompts.PROMPTS[only]
        record = prompts.effective(cfg, only)
        print(record["text"], end="" if record["text"].endswith("\n") else "\n")
        print(f"source: {prompts.source(cfg, only)}", file=sys.stderr)
        print(entry["explain"], file=sys.stderr)
        names = prompts._known(entry)
        print("placeholders: " + ", ".join(sorted(names)), file=sys.stderr)
        if record["source"] != "built-in":
            print("Built-in:", file=sys.stderr)
            print(entry["text"], file=sys.stderr)
        return 0
    print("Prompts (built-in unless marked)")
    for prompt_id, entry in prompts.PROMPTS.items():
        record = prompts.effective(cfg, prompt_id)
        mark = record["source"]
        if record["parts"]:
            mark = f"{record['source']} ({', '.join(record['parts'])})"
        print(f"  {prompt_id:<22} {mark:<28} {entry['used_by']}")
        based = record.get("based_on")
        replaced = "text" in record["parts"] or "file" in record["parts"]
        if replaced and (based is None or based < entry["version"]):
            shown = "unset" if based is None else based
            print(f"                        ! the built-in prompt changed "
                  f"(version {entry['version']}) since this override "
                  f"(based_on {shown}). Compare: pm doctor --prompts {prompt_id}")
    return 0


def _query_report(cfg, only=None):
    from core import queries, workstreams
    if only and only != "all":
        if only not in queries.QUERIES and only not in (cfg.get("_queries") or {}):
            print(f"Unknown query {only}.", file=sys.stderr)
            return 1
        print(queries.template(cfg, only))
        return 0
    print("Queries (built-in unless marked)")
    texts = cfg.get("_queries") or {}
    for qid in sorted(texts):
        origin = queries.source(cfg, qid)
        print(f"  {qid:<28} {origin:<10} {texts[qid]}")
    for ws in cfg.get("_workstreams") or []:
        print(ws.get("abbrev") or ws.get("name"))
        from core import filters
        for scope_name in sorted(filters.SCOPE_INCLUDES):
            try:
                jql = workstreams.scope_jql(cfg, ws, scope_name)
                count = sources.approximate_count(cfg["jira"], jql) if jql else 0
                print(f"  {scope_name} scope          ok   {count} issues")
            except Exception as err:  # noqa: BLE001
                print(f"  {scope_name} scope          FAIL  {err}")
    return 0


def _check_confluence(cfg):
    import datetime as dt
    from core import filters, pages
    for ws in cfg.get("workstreams") or []:
        abbrev = ws.get("abbrev") or "?"
        space = ws.get("confluence_space")
        if not space:
            print(f"  confluence      {abbrev} has no confluence_space          warn")
            continue
        try:
            opts = pages.page_settings(cfg)
            types = list(opts["content_types"]) + list(opts["title_only_types"])
            since = (dt.date.today() - dt.timedelta(days=7)).isoformat()
            accepted = []
            for content_type in types:
                one = filters.build_cql(ws, cfg, scope="space", types=[content_type])
                try:
                    sources.fetch_confluence_results(cfg, one, since=since, limit=1)
                    accepted.append(content_type)
                except Exception as err:  # noqa: BLE001
                    if "400" in str(err):
                        print(f"  confluence      {abbrev} type {content_type} was rejected — "
                              f"edit confluence.content_types          warn")
                    else:
                        print(f"  confluence      {abbrev} type {content_type}: {err}          warn")
            cql = filters.build_cql(ws, cfg, scope="space", types=accepted or types)
            found = sources.fetch_confluence_results(cfg, cql, since=since, limit=5) if cql else []
            print(f"  confluence      {abbrev} {space}: {len(found)} page(s) in 7 days  ok")
        except Exception as err:  # noqa: BLE001
            print(f"  confluence      {abbrev} {err}                              warn")


def _check_registers(cfg):
    from core import registers
    raw = cfg.get("registers") or []
    if not raw:
        print("  registers       none configured                              warn")
        return
    for reg in registers.settings(cfg):
        root = registers.resolve_root(cfg, reg)
        name = reg.get("name") or reg.get("type")
        if root is None:
            print(f"  registers       {name}: summary page not found — set page_id  warn")
            continue
        try:
            listed = registers.list_entries(cfg, reg, root["page_id"])
        except Exception as err:  # noqa: BLE001
            print(f"  registers       {name}: {root.get('title')} ({err})          warn")
            continue
        field = reg.get("status_field") or "Status"
        with_status = 0
        cql = registers._entry_cql(reg, root["page_id"])
        for raw in sources.fetch_confluence_results(cfg, cql, since="1970-01-01", limit=200):
            storage = ((raw.get("body") or {}).get("storage") or {}).get("value") or ""
            if registers.properties(storage, [field]).get(field):
                with_status += 1
        print(f"  registers       {name}: {root.get('title')} — {len(listed)} entries, "
              f"{with_status} with {field}          ok")


def run(cfg, args):
    prompt_id = getattr(args, "prompts", None)
    if prompt_id is not None:
        sys.exit(_prompt_report(cfg, prompt_id))
    print("pm doctor\n")
    problems = 0
    problems += _check_version(cfg)
    problems += _check_config(cfg)
    from core import prompts as prompt_core
    overridden = sum(1 for pid in prompt_core.PROMPTS
                     if prompt_core.source(cfg, pid) != "built-in")
    query_over = sum(1 for origin in (cfg.get("_query_sources") or {}).values()
                     if origin != "built-in")
    print(f"Prompts: {len(prompt_core.PROMPTS) - overridden} built-in, "
          f"{overridden} overridden · Queries: {query_over} overridden")

    if getattr(args, "queries", None) is not None:
        status, _me = _check_jira(cfg)
        if status:
            print("\nStopped here — fix Jira credentials and run again.")
            sys.exit(1)
        sys.exit(_query_report(cfg, args.queries))

    status, _me = _check_jira(cfg)
    problems += status
    if status:
        print("\nStopped here — fix Jira credentials and run again.")
        sys.exit(1)

    problems += _check_projects(cfg)

    try:
        fields = sources.fetch_fields(cfg["jira"])
    except Exception as err:                       # noqa: BLE001
        problems += _fail("custom fields", f"could not list fields ({err})")
        fields = []
    else:
        problems += _check_custom_fields(cfg, fields)

    problems += _check_membership(cfg)
    problems += _check_statuses(cfg)
    problems += _check_model(cfg)
    problems += _check_cache(cfg)
    _check_confluence(cfg)
    _check_registers(cfg)

    if getattr(args, "discover_fields", False):
        if fields:
            _discover_fields(cfg, fields, getattr(args, "yes", False))
        else:
            print("\nCannot discover fields — the field list did not load.")

    print("")
    if problems:
        print(f"{problems} check(s) failed. The FAIL lines name the fix.")
        sys.exit(1)
    print("Setup looks good.")
