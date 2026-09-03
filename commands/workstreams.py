"""`pm workstreams` — see, change and verify the workstream setup.

A workstream is four lines of YAML: a name, an abbreviation, the Jira
Component(s) that identify it, and optionally where its documents live. This
command means you never have to hand-edit that list to add or drop one, and
never have to guess whether Jira agrees with what you typed.

  pm workstreams                      List what is configured.
  pm workstreams add --name "Billing Platform" --abbrev BIL \
                     --components "Billing Platform"
  pm workstreams remove BIL           Take one out again.
  pm workstreams check                Ask Jira whether the setup resolves.
  pm workstreams check --show-jql     Also print the queries pm generates.

`add` and `remove` edit your config file in place, leaving every comment and
every other setting exactly where it was, and refuse to write a file that would
not load.
"""

import difflib
import sys

import yaml

from core import config as config_core
from core import config_edit
from core import products as product_core
from core import sources
from core import workstreams as ws_core


SCOPE_LABELS = {
    "report": "report (sprint work)",
    "roadmap": "roadmap (the epics)",
    "lint": "lint / review",
    "ready": "ready",
    "standup_wip": "standup (in progress)",
}


# ---------------------------------------------------------------------------
#  Listing
# ---------------------------------------------------------------------------

def _components_text(ws):
    components = ws_core.components_of(ws)
    return ", ".join(components) if components else "(legacy JQL)"


def _list(cfg):
    print(f"Config: {cfg.get('_config_path', '(unknown)')}\n")
    rows = [("Abbrev", "Name", "Product", "Project", "Components")]
    streams = cfg.get("_workstreams") or cfg["workstreams"]
    for ws in streams:
        rows.append((ws.get("abbrev", "?"), ws.get("name", ""),
                     product_core.product_abbrev_of(ws),
                     ws_core.project_of(cfg, ws) or "-", _components_text(ws)))

    widths = [max(len(r[i]) for r in rows) for i in range(5)]
    for n, row in enumerate(rows):
        print("  " + "  ".join(cell.ljust(widths[i])
                               for i, cell in enumerate(row)).rstrip())
        if n == 0:
            print("  " + "  ".join("-" * w for w in widths))

    settings = ws_core.membership_settings(cfg)
    print(f"\nMembership: own component always counts; "
          f"inherit from parent = {settings['inherit_from_parent']}; "
          f"child component wins = {settings['child_component_wins']}.")
    print("Add one with:  pm workstreams add --name ... --abbrev ... "
          "--components ...")


# ---------------------------------------------------------------------------
#  Editing the config file in place, comments and all
# ---------------------------------------------------------------------------

def _entry_lines(entry, indent="  "):
    """Render one workstream as YAML, in the same shape as the template."""
    def quoted(value):
        return '"' + str(value).replace('"', '\\"') + '"'

    body = [f'{indent}- name: {quoted(entry["name"])}',
            f'{indent}  abbrev: {quoted(entry["abbrev"])}']
    if entry.get("product"):
        body.append(f'{indent}  product: {quoted(entry["product"])}')
    if entry.get("project"):
        body.append(f'{indent}  project: {quoted(entry["project"])}')
    components = ", ".join(quoted(c) for c in entry["components"])
    body.append(f'{indent}  components: [{components}]')
    if entry.get("confluence_space"):
        body.append(f'{indent}  confluence_space: '
                    f'{quoted(entry["confluence_space"])}')
    if entry.get("confluence_labels"):
        labels = ", ".join(quoted(l) for l in entry["confluence_labels"])
        body.append(f'{indent}  confluence_labels: [{labels}]')
    if entry.get("sharepoint_query"):
        body.append(f'{indent}  sharepoint_query: '
                    f'{quoted(entry["sharepoint_query"])}')
    return body


def add_entry_to_text(text, entry):
    """Return `text` with one workstream appended to its workstreams list."""
    return config_edit.add_list_entry(text, "workstreams", entry, _entry_lines)


def remove_entry_from_text(text, abbrev):
    """Return `text` with the named workstream removed from the list."""
    return config_edit.remove_list_entry(text, "workstreams", abbrev)


def _write_checked(path, text):
    """Validate the edited config before it replaces the file on disk."""
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as err:
        sys.exit(f"Refusing to write: the edit would not parse as YAML ({err}).")
    if not isinstance(parsed, dict) or not parsed.get("workstreams"):
        sys.exit("Refusing to write: the edit would leave no workstreams. "
                 "Add another one before removing the last.")
    config_core.validate(parsed)

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _add(cfg, args):
    if not (args.name and args.abbrev and args.components):
        sys.exit("`pm workstreams add` needs --name, --abbrev and --components, "
                 "e.g.\n  pm workstreams add --name \"Billing Platform\" "
                 "--abbrev BIL --components \"Billing Platform\"")

    product = getattr(args, "product", None)
    if product:
        if product_core.resolve_product(cfg, product) is None:
            available = ", ".join(p["abbrev"] for p in
                                  product_core.listed_products(cfg)) or "(none)"
            sys.exit(f"Unknown product {product}. Available: {available}. "
                     f"Add it first with:  pm products add --name ... "
                     f"--abbrev ...")

    entry = {
        "name": args.name,
        "abbrev": args.abbrev,
        "product": product,
        "project": args.project,
        "components": [c.strip() for c in args.components.split(",")
                       if c.strip()],
        "confluence_space": args.confluence_space,
        "confluence_labels": [l.strip() for l in
                              (args.confluence_labels or "").split(",")
                              if l.strip()],
        "sharepoint_query": args.sharepoint_query,
    }

    path = cfg["_config_path"]
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    try:
        updated = add_entry_to_text(text, entry)
    except ValueError as err:
        sys.exit(f"Could not add the workstream: {err}.")
    _write_checked(path, updated)

    print(f"Added {entry['abbrev']} ({entry['name']}) to {path}:\n")
    print("\n".join(_entry_lines(entry)))
    print(f"\nCheck it against Jira with:  "
          f"pm workstreams check -w {entry['abbrev']}")


def _remove(cfg, args):
    abbrev = args.target or args.abbrev
    if not abbrev:
        sys.exit("Which one? e.g.  pm workstreams remove SDX")

    path = cfg["_config_path"]
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    try:
        updated = remove_entry_from_text(text, abbrev)
    except ValueError as err:
        sys.exit(f"Could not remove the workstream: {err}.")
    _write_checked(path, updated)
    print(f"Removed {abbrev} from {path}.")


# ---------------------------------------------------------------------------
#  Checking the setup against Jira
# ---------------------------------------------------------------------------

def _check_components(cfg, ws, available):
    """Compare configured Component names with the ones the project defines."""
    problems = []
    for name in ws_core.components_of(ws):
        if name in available:
            continue
        close = difflib.get_close_matches(name, available, n=2, cutoff=0.6)
        hint = f" Did you mean: {', '.join(close)}?" if close else ""
        problems.append(f"Component {name!r} does not exist in the project."
                        f"{hint}")
    return problems


def check_one(cfg, ws, args, indent="  "):
    """Verify one workstream against Jira. Returns the number of problems."""
    jira_cfg = cfg["jira"]
    problems = 0
    pad = indent

    if not ws_core.uses_component_scope(cfg, ws):
        print(f"{pad}legacy JQL workstream — no component membership to check.")
        return 0

    project = ws_core.project_of(cfg, ws)
    print(f"{pad}project: {project}")
    print(f"{pad}components: {', '.join(ws_core.components_of(ws))}")

    try:
        available = sources.fetch_project_components(jira_cfg, project)
    except Exception as err:                       # noqa: BLE001
        print(f"{pad}⚠ could not list components for {project}: {err}")
        available = []
        problems += 1

    if available:
        for problem in _check_components(cfg, ws, available):
            print(f"{pad}⚠ {problem}")
            problems += 1

    epics = ws_core.get_epic_keys(cfg, ws)
    tagged = ws_core.get_tagged_issue_keys(cfg, ws)
    print(f"{pad}epics carrying the component: {len(epics)}")
    print(f"{pad}issues tagged directly: {len(tagged)}")
    if not epics and not tagged:
        print(f"{pad}⚠ nothing in Jira carries these components yet.")
        problems += 1

    for scope, scope_label in SCOPE_LABELS.items():
        jql = ws_core.scope_jql(cfg, ws, scope)
        if not jql:
            print(f"{pad}{scope_label}: nothing in scope")
            continue
        try:
            count = sources.approximate_count(jira_cfg, jql)
            print(f"{pad}{scope_label}: ~{count} issue(s)")
        except Exception as err:                   # noqa: BLE001
            print(f"{pad}{scope_label}: ⚠ query failed ({err})")
            problems += 1
        if getattr(args, "show_jql", False):
            print(f"{pad}    {jql}")
    return problems


def connect_jira(cfg):
    """Reach Jira once and print who we connected as. Exits on failure."""
    jira_cfg = cfg["jira"]
    try:
        me = sources.fetch_myself(jira_cfg)
        print(f"Jira: connected to {jira_cfg['base_url']} as "
              f"{me.get('displayName') or me.get('emailAddress')}\n")
        return me
    except Exception as err:                       # noqa: BLE001 — report, don't crash
        sys.exit(f"Could not reach Jira at {jira_cfg.get('base_url')}: {err}\n"
                 f"Check jira.base_url, jira.email and jira.api_token.")


def _check(cfg, args):
    connect_jira(cfg)
    problems = 0
    for ws in cfg["_workstreams"]:
        print(f"{ws.get('name')} ({ws.get('abbrev')})")
        problems += check_one(cfg, ws, args)
        print("")

    if problems:
        print(f"{problems} problem(s) found. Fix the config, or the Component "
              f"names in Jira, and run this again.")
        sys.exit(1)
    print("Setup looks good.")


# ---------------------------------------------------------------------------
#  Entry point
# ---------------------------------------------------------------------------

def run(cfg, args):
    action = getattr(args, "action", "list") or "list"
    if action == "list":
        _list(cfg)
    elif action == "add":
        _add(cfg, args)
    elif action == "remove":
        _remove(cfg, args)
    elif action == "check":
        _check(cfg, args)
    else:                                          # argparse should prevent this
        sys.exit(f"Unknown action {action}. "
                 f"Try: list, add, remove, check.")
