"""`pm products` — see, change and verify the portfolio layer.

A product is a name, an abbreviation, and optional per-product defaults
(Jira project, scopes). Workstreams stay a flat list and point at a product
with `product: <abbrev>`. A workstream with no product lands in Unassigned.

  pm products
  pm products add --name "Billing Platform" --abbrev BILL --project BILL
  pm products remove BILL
  pm products check
  pm products check --show-jql

`add` and `remove` edit the config in place and refuse to write a file that
would not load. Removing a product that workstreams still name is refused.
"""

import sys

import yaml

from commands import workstreams as ws_cmd
from core import config as config_core
from core import config_edit
from core import products as product_core
from core import sources


def _entry_lines(entry, indent="  "):
    def quoted(value):
        return '"' + str(value).replace('"', '\\"') + '"'

    body = [f'{indent}- name: {quoted(entry["name"])}',
            f'{indent}  abbrev: {quoted(entry["abbrev"])}']
    if entry.get("project"):
        body.append(f'{indent}  project: {quoted(entry["project"])}')
    return body


def add_entry_to_text(text, entry):
    return config_edit.add_list_entry(
        text, "products", entry, _entry_lines, before_key="workstreams",
        create=True)


def remove_entry_from_text(text, abbrev):
    return config_edit.remove_list_entry(text, "products", abbrev)


def _write_checked(path, text):
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as err:
        sys.exit(f"Refusing to write: the edit would not parse as YAML ({err}).")
    if not isinstance(parsed, dict):
        sys.exit("Refusing to write: the edit would not be a config mapping.")
    config_core.validate(parsed)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _list(cfg):
    print(f"Config: {cfg.get('_config_path', '(unknown)')}\n")
    streams = cfg.get("_workstreams") or cfg.get("workstreams") or []
    rows = [("Abbrev", "Name", "Project", "Workstreams")]
    seen = set()
    for product, group in product_core.group_workstreams(cfg, streams):
        abbrevs = ", ".join(ws.get("abbrev", "?") for ws in group) or "-"
        rows.append((product.get("abbrev", "?"), product.get("name", ""),
                     product.get("project") or "-",
                     f"{len(group)} ({abbrevs})" if group else "0"))
        seen.add(product["abbrev"].lower())

    # Configured products that the current filter left empty still show up
    # when we are listing the whole portfolio.
    if not getattr(cfg, "_product_filter", None):
        for product in product_core.listed_products(cfg):
            if product["abbrev"].lower() in seen:
                continue
            rows.append((product.get("abbrev", "?"), product.get("name", ""),
                         product.get("project") or "-", "0"))

    widths = [max(len(r[i]) for r in rows) for i in range(4)]
    for n, row in enumerate(rows):
        print("  " + "  ".join(cell.ljust(widths[i])
                               for i, cell in enumerate(row)).rstrip())
        if n == 0:
            print("  " + "  ".join("-" * w for w in widths))

    print("\nA workstream with no `product:` lands in Unassigned.")
    print("Add one with:  pm products add --name ... --abbrev ... "
          "[--project ...]")


def _add(cfg, args):
    if not (args.name and args.abbrev):
        sys.exit("`pm products add` needs --name and --abbrev, e.g.\n"
                 "  pm products add --name \"Billing Platform\" "
                 "--abbrev BILL --project BILL")

    entry = {
        "name": args.name,
        "abbrev": args.abbrev,
        "project": args.project,
    }

    path = cfg["_config_path"]
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    try:
        updated = add_entry_to_text(text, entry)
    except ValueError as err:
        sys.exit(f"Could not add the product: {err}.")
    _write_checked(path, updated)

    print(f"Added {entry['abbrev']} ({entry['name']}) to {path}:\n")
    print("\n".join(_entry_lines(entry)))
    print(f"\nTag a workstream with:  pm workstreams add ... "
          f"--product {entry['abbrev']}")
    print(f"Check it against Jira with:  "
          f"pm products check --product {entry['abbrev']}")


def _remove(cfg, args):
    abbrev = args.target or args.abbrev
    if not abbrev:
        sys.exit("Which one? e.g.  pm products remove BILL")
    if abbrev.lower() == product_core.UNASSIGNED_ABBREV.lower():
        sys.exit("Unassigned is implicit — there is nothing to remove. "
                 "Tag those workstreams with a product instead.")

    still = product_core.workstreams_of(cfg, abbrev)
    if still:
        names = ", ".join(ws.get("abbrev", "?") for ws in still)
        sys.exit(f"Cannot remove {abbrev}: {len(still)} workstream(s) still "
                 f"name it ({names}). Retag or remove them first.")

    path = cfg["_config_path"]
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    try:
        updated = remove_entry_from_text(text, abbrev)
    except ValueError as err:
        sys.exit(f"Could not remove the product: {err}.")
    _write_checked(path, updated)
    print(f"Removed {abbrev} from {path}.")


def _check(cfg, args):
    ws_cmd.connect_jira(cfg)
    jira_cfg = cfg["jira"]
    problems = 0
    streams = cfg.get("_workstreams") or cfg.get("workstreams") or []

    for product, group in product_core.group_workstreams(cfg, streams):
        label = f"{product.get('name')} ({product.get('abbrev')})"
        print(label)
        project = product.get("project")
        if project:
            print(f"  project: {project}")
            try:
                sources.fetch_project(jira_cfg, project)
            except Exception as err:               # noqa: BLE001
                print(f"  ⚠ could not open project {project}: {err}")
                problems += 1
        elif product["abbrev"] != product_core.UNASSIGNED_ABBREV:
            print("  project: (inherits jira.project)")

        print(f"  workstreams: {len(group)}")
        for ws in group:
            print(f"  {ws.get('name')} ({ws.get('abbrev')})")
            problems += ws_cmd.check_one(cfg, ws, args, indent="    ")
        print("")

    if problems:
        print(f"{problems} problem(s) found. Fix the config, or the Component "
              f"names in Jira, and run this again.")
        sys.exit(1)
    print("Setup looks good.")


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
    else:
        sys.exit(f"Unknown action {action}. Try: list, add, remove, check.")
