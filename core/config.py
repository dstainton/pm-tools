"""Configuration loading, shared by every command.

Reads the YAML config and expands ${ENV:VAR} placeholders found in VALUES
(not comments), so tokens can be kept in environment variables if you prefer.
"""

import os
import re
import sys

import yaml


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
    _validate_workstreams(data)
    return data


def _validate_workstreams(cfg):
    """Catch partial inherited-workstream configuration before Jira is called."""
    for ws in cfg.get("workstreams", []) or []:
        has_project = bool(ws.get("jira_project"))
        has_components = bool(ws.get("epic_components"))
        if has_project != has_components:
            name = ws.get("abbrev") or ws.get("name") or "(unnamed)"
            sys.exit(
                f"Workstream {name} must set both jira_project and "
                f"epic_components, or neither (legacy direct-JQL mode)."
            )
        if has_components and not isinstance(ws.get("epic_components"), list):
            name = ws.get("abbrev") or ws.get("name") or "(unnamed)"
            sys.exit(f"Workstream {name}: epic_components must be a YAML list.")


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
