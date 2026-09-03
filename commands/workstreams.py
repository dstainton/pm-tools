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
import re
import sys

import yaml

from core import config as config_core
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
    rows = [("Abbrev", "Name", "Project", "Components")]
    for ws in cfg["workstreams"]:
        rows.append((ws.get("abbrev", "?"), ws.get("name", ""),
                     ws_core.project_of(cfg, ws) or "-", _components_text(ws)))

    widths = [max(len(r[i]) for r in rows) for i in range(4)]
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

TOP_LEVEL = re.compile(r"^[A-Za-z_][\w-]*:")


def _read_lines(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read().splitlines()


def _find_block(lines):
    """Locate the `workstreams:` list: (header index, end index exclusive)."""
    start = None
    for n, line in enumerate(lines):
        if re.match(r"^workstreams:\s*(#.*)?$", line):
            start = n
            break
    if start is None:
        return None, None

    end = len(lines)
    for n in range(start + 1, len(lines)):
        if TOP_LEVEL.match(lines[n]):
            end = n
            break
    return start, end


def _items(lines, start, end):
    """Split the list body into (abbrev, first line, last line) per entry."""
    item_re = re.compile(r"^(\s*)-\s")
    found, current, indent = [], None, None
    for n in range(start + 1, end):
        match = item_re.match(lines[n])
        if match:
            if current is not None:
                found.append((current[0], current[1], n - 1))
            current, indent = [None, n], match.group(1)
        elif current is not None and lines[n].strip() and \
                not lines[n].startswith((indent or "") + " "):
            # Dedented back out of the list (a stray comment, say).
            found.append((current[0], current[1], n - 1))
            current = None
        if current is not None:
            abbrev = re.search(r"""abbrev:\s*["']?([\w-]+)""", lines[n])
            if abbrev:
                current[0] = abbrev.group(1)
    if current is not None:
        found.append((current[0], current[1], end - 1))
    return found


def _entry_lines(entry, indent="  "):
    """Render one workstream as YAML, in the same shape as the template."""
    def quoted(value):
        return '"' + str(value).replace('"', '\\"') + '"'

    body = [f'{indent}- name: {quoted(entry["name"])}',
            f'{indent}  abbrev: {quoted(entry["abbrev"])}']
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
    lines = text.splitlines()
    start, end = _find_block(lines)
    if start is None:
        raise ValueError("no top-level `workstreams:` list found in the config")

    existing = _items(lines, start, end)
    for abbrev, _first, _last in existing:
        if abbrev and abbrev.lower() == entry["abbrev"].lower():
            raise ValueError(f"a workstream with abbrev {abbrev} already exists")

    indent = "  "
    if existing:
        indent = re.match(r"^(\s*)-", lines[existing[0][1]]).group(1)

    # Insert after the last real line of the list, so the comment banner that
    # introduces the next section stays where the author put it.
    insert_at = end
    while insert_at - 1 > start and (not lines[insert_at - 1].strip()
                                     or lines[insert_at - 1].lstrip()
                                     .startswith("#")):
        insert_at -= 1

    block = [""] + _entry_lines(entry, indent) if existing else \
        _entry_lines(entry, indent)
    return "\n".join(lines[:insert_at] + block + lines[insert_at:]) + "\n"


def remove_entry_from_text(text, abbrev):
    """Return `text` with the named workstream removed from the list."""
    lines = text.splitlines()
    start, end = _find_block(lines)
    if start is None:
        raise ValueError("no top-level `workstreams:` list found in the config")

    for found, first, last in _items(lines, start, end):
        if found and found.lower() == abbrev.lower():
            # Swallow one trailing blank line so entries stay evenly spaced.
            cut_to = last + 1
            if cut_to < end and not lines[cut_to].strip():
                cut_to += 1
            return "\n".join(lines[:first] + lines[cut_to:]) + "\n"

    raise ValueError(f"no workstream with abbrev {abbrev} in the config")


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

    entry = {
        "name": args.name,
        "abbrev": args.abbrev,
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


def _check(cfg, args):
    jira_cfg = cfg["jira"]
    try:
        me = sources.fetch_myself(jira_cfg)
        print(f"Jira: connected to {jira_cfg['base_url']} as "
              f"{me.get('displayName') or me.get('emailAddress')}\n")
    except Exception as err:                       # noqa: BLE001 — report, don't crash
        sys.exit(f"Could not reach Jira at {jira_cfg.get('base_url')}: {err}\n"
                 f"Check jira.base_url, jira.email and jira.api_token.")

    problems = 0
    for ws in cfg["_workstreams"]:
        label = f"{ws.get('name')} ({ws.get('abbrev')})"
        project = ws_core.project_of(cfg, ws)
        print(f"{label}")

        if not ws_core.uses_component_scope(cfg, ws):
            print("  legacy JQL workstream — no component membership to check.\n")
            continue

        print(f"  project: {project}")
        print(f"  components: {', '.join(ws_core.components_of(ws))}")

        try:
            available = sources.fetch_project_components(jira_cfg, project)
        except Exception as err:                   # noqa: BLE001
            print(f"  ⚠ could not list components for {project}: {err}")
            available = []
            problems += 1

        if available:
            for problem in _check_components(cfg, ws, available):
                print(f"  ⚠ {problem}")
                problems += 1

        epics = ws_core.get_epic_keys(cfg, ws)
        tagged = ws_core.get_tagged_issue_keys(cfg, ws)
        print(f"  epics carrying the component: {len(epics)}")
        print(f"  issues tagged directly: {len(tagged)}")
        if not epics and not tagged:
            print("  ⚠ nothing in Jira carries these components yet.")
            problems += 1

        for scope, scope_label in SCOPE_LABELS.items():
            jql = ws_core.scope_jql(cfg, ws, scope)
            if not jql:
                print(f"  {scope_label}: nothing in scope")
                continue
            try:
                count = sources.approximate_count(jira_cfg, jql)
                print(f"  {scope_label}: ~{count} issue(s)")
            except Exception as err:               # noqa: BLE001
                print(f"  {scope_label}: ⚠ query failed ({err})")
                problems += 1
            if getattr(args, "show_jql", False):
                print(f"      {jql}")
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
