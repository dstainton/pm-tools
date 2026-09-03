"""Configuration loading, shared by every command.

Reads the YAML config and expands ${ENV:VAR} placeholders found in VALUES
(not comments), so tokens can be kept in environment variables if you prefer.
"""

import os
import re
import sys

import yaml

from core import filters, workstreams as ws_core


def load_config(path):
    """Read the YAML config and expand any ${ENV:VAR} placeholders."""
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    def sub(match):
        var = match.group(1)
        value = os.environ.get(var)
        if value is None:
            sys.exit(f"Config refers to ${{ENV:{var}}} but that "
                     f"environment variable is not set.")
        return value

    def walk(node):
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, str):
            return re.sub(r"\$\{ENV:([A-Za-z0-9_]+)\}", sub, node)
        return node

    data = walk(data)
    validate(data)
    return data


def validate(cfg):
    """Check the whole config before a single Jira call is made.

    Everything a typo can break — workstream definitions, scope options,
    membership settings — is caught here, with a message that names the fix.
    """
    _validate_workstreams(cfg)
    _validate_membership(cfg)
    filters.validate_config_scopes(cfg)


def _label(ws):
    return ws.get("abbrev") or ws.get("name") or "(unnamed)"


def _validate_workstreams(cfg):
    """Every workstream needs a name, an abbreviation and a way to be found."""
    entries = cfg.get("workstreams") or []
    if not entries:
        sys.exit("No workstreams configured. Add one with:\n"
                 "  pm workstreams add --name \"My Stream\" --abbrev MS "
                 "--components \"My Component\"")

    seen = {}
    for ws in entries:
        name = _label(ws)
        if not ws.get("abbrev"):
            sys.exit(f"Workstream {name} needs an `abbrev` "
                     f"(the short name you pass to --workstream).")
        key = ws["abbrev"].lower()
        if key in seen:
            sys.exit(f"Two workstreams share the abbrev {ws['abbrev']}. "
                     f"Abbreviations must be unique.")
        seen[key] = True

        components = ws.get("components", ws.get("epic_components"))
        if components is not None and not isinstance(components, (list, str)):
            sys.exit(f"Workstream {name}: `components` must be a YAML list of "
                     f"Component names.")

        has_components = bool(ws_core.components_of(ws))
        has_legacy_jql = any(ws.get(f) for fields in
                             ws_core.LEGACY_FIELDS.values() for f in fields)

        if has_components and not ws_core.project_of(cfg, ws):
            sys.exit(f"Workstream {name} lists components but no project. "
                     f"Set `project:` on the workstream, or `jira.project` "
                     f"once for all of them.")
        if not has_components and not has_legacy_jql:
            sys.exit(f"Workstream {name} has no `components:` and no legacy "
                     f"JQL, so pm cannot tell which issues belong to it.")


def _validate_membership(cfg):
    block = cfg.get("membership")
    if block is None:
        return
    if not isinstance(block, dict):
        sys.exit("`membership:` must be a mapping of settings.")
    unknown = sorted(set(block) - set(ws_core.DEFAULT_MEMBERSHIP))
    if unknown:
        sys.exit(f"Unknown membership setting(s): {', '.join(unknown)}. "
                 f"Valid: {', '.join(sorted(ws_core.DEFAULT_MEMBERSHIP))}.")


def filter_workstreams(cfg, selector):
    """Narrow cfg['workstreams'] to those named in `selector`.

    `selector` is a comma-separated string of abbreviations (case-insensitive),
    e.g. "SDX" or "sdx,itk". Returns the filtered list. Exits with a helpful
    message if a name doesn't match any workstream, so a typo fails loudly
    rather than silently doing nothing.
    """
    if not selector:
        return cfg["workstreams"]

    wanted = [s.strip().lower() for s in selector.split(",") if s.strip()]
    by_abbrev = {ws["abbrev"].lower(): ws for ws in cfg["workstreams"]}

    unknown = [w for w in wanted if w not in by_abbrev]
    if unknown:
        available = ", ".join(ws["abbrev"] for ws in cfg["workstreams"])
        sys.exit(f"Unknown workstream(s): {', '.join(unknown)}. "
                 f"Available: {available}.")

    # Preserve the order given on the command line.
    return [by_abbrev[w] for w in wanted]
