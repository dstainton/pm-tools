"""`pm doctor` — verify the setup, and name the fix when something is wrong.

  pm doctor
  pm doctor --discover-fields

Checks, in order: the config, Jira credentials, every product/workstream
project, the custom-field IDs lint depends on, membership (including
unclaimed work), the local model, and the fetch cache.

`--discover-fields` lists fields whose names look like story points, start
date, acceptance criteria or Epic Link, and prints a YAML snippet to paste.
It does not write the config — that is still a human edit.
"""

import re
import sys

from core import cache as cache_core
from core import filters
from core import model as model_core
from core import products as product_core
from core import sources
from core import workstreams as ws_core


def _ok(label, detail):
    print(f"  {label:<16}{detail:<48} ok")
    return 0


def _warn(label, detail):
    print(f"  {label:<16}{detail:<48} warn")
    return 0


def _fail(label, detail):
    print(f"  {label:<16}{detail:<48} FAIL")
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
    return f"({base}) AND (statusCategory != Done)"


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
        jql = (f"project = {filters.quote(project)} "
               f"AND statusCategory != Done")
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
    if state == "disabled":
        return _warn("cache", detail)
    return _ok("cache", detail)


FIELD_HINTS = (
    ("story_points_field", re.compile(r"story\s*point", re.I)),
    ("start_date_field", re.compile(r"start\s*date", re.I)),
    ("acceptance_criteria_field", re.compile(r"acceptance\s*criteria", re.I)),
    ("epic_link_field", re.compile(r"epic\s*link", re.I)),
)


def _discover_fields(fields):
    print("\nField discovery (paste into the jira: block; nothing was written):\n")
    suggested = {}
    for key, pattern in FIELD_HINTS:
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


def run(cfg, args):
    print("pm doctor\n")
    problems = 0
    problems += _check_config(cfg)

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
    problems += _check_model(cfg)
    problems += _check_cache(cfg)

    if getattr(args, "discover_fields", False):
        if fields:
            _discover_fields(fields)
        else:
            print("\nCannot discover fields — the field list did not load.")

    print("")
    if problems:
        print(f"{problems} check(s) failed. The FAIL lines name the fix.")
        sys.exit(1)
    print("Setup looks good.")
