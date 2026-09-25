"""Configuration loading, shared by every command.

Reads the YAML config and expands ${ENV:VAR} placeholders found in VALUES
(not comments), so tokens can be kept in environment variables if you prefer.
A placeholder inside a block with `enabled: false` may be unset. It expands
to an empty string. Everywhere else, a missing variable stops the command.
"""

import os
import re
import sys

import yaml

from core import (
    conventions, filters, products as product_core, prompts, queries,
    workstreams as ws_core,
)
from core.paths import HOME


# Filled in memory when a block or key is absent. This does not write the file.
SECTION_DEFAULTS = {
    "model": {
        "endpoint": "http://127.0.0.1:11434/v1/chat/completions",
        "name": "qwen3:4b",
        "api_key": "",
        "temperature": 0.4,
        "json_temperature": 0.2,
        "top_p": 0.8,
        "top_k": 20,
        "presence_penalty": 1.5,
        "max_tokens": 2048,
        "timeout": 600,
        "total_timeout": 3600,
        "enable_thinking": False,
    },
    "output": {
        "directory": HOME + "/out",
        "file": "weekly_report_{date}.md",
        "audience": "stakeholders",
        "state_file": "report_state.json",
    },
    "lint": {
        "stale_days": 14,
        "required_fields": ["parent"],
        "min_title_words": 3,
        "vague_title_alone": ["refactor", "test"],
        "story_types": ["story", "bug"],
        "estimate_types": ["story"],
        "require_acceptance_criteria": True,
        "require_estimate": True,
    },
    "review": {"batch_size": 8},
    "ready": {
        "blocking_criteria": [
            "clear-title", "has-acceptance-criteria", "has-estimate",
            "linked-to-parent", "sane-dates",
        ],
        "max_points": 8,
    },
    "daily": {"lookback_days": 1},
    "cache": {
        "enabled": True,
        "path": HOME + "/cache",
        "ttl_seconds": 300,
        "model_ttl_seconds": 604800,
    },
    "blocked": {
        "statuses": ["Blocked"],
        "labels": ["blocked"],
    },
    "today": {
        "state_file": HOME + "/today.json",
        "max_needs_you": 5,
        "max_moved": 8,
        "max_aging": 3,
        "untouched_days": 3,
    },
    "triage": {
        "unassigned_in_sprint": True,
        "blocked": True,
        "mentions_me_within_days": 3,
        "new_bugs_within_days": 1,
        "in_sprint_untouched_days": 3,
        "overdue": True,
    },
    "metrics": {"weeks": 8},
    "comments": {
        "enabled": True,
        "max_per_issue": 3,
        "max_issues": 25,
        "excerpt_chars": 240,
        "report_days": 7,
        "section_chars": 6000,
    },
}


def apply_defaults(cfg):
    """Fill missing sections in memory and reject a section of the wrong type."""
    version = cfg.get("config_version")
    if version is not None and not isinstance(version, int):
        sys.exit("`config_version:` must be a whole number.")
    for key, defaults in SECTION_DEFAULTS.items():
        block = cfg.get(key)
        if block is None:
            cfg[key] = {k: (list(v) if isinstance(v, list) else v)
                        for k, v in defaults.items()}
            continue
        if not isinstance(block, dict):
            sys.exit(f"`{key}:` must be a mapping.")
        for name, value in defaults.items():
            block.setdefault(name, list(value) if isinstance(value, list) else value)
    return cfg


def load_config(path):
    """Read the YAML config and expand any ${ENV:VAR} placeholders."""
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    def walk(node, optional=False):
        if isinstance(node, dict):
            # A switched-off feature (Teams, SharePoint) can name a secret
            # it does not need yet. `pm products` must not demand it.
            here = optional or node.get("enabled") is False
            return {k: walk(v, here) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v, optional) for v in node]
        if isinstance(node, str):
            def sub(match):
                var = match.group(1)
                value = os.environ.get(var)
                if value is None:
                    if optional:
                        return ""
                    sys.exit(f"Config refers to ${{ENV:{var}}} but that "
                             f"environment variable is not set.")
                return value
            return re.sub(r"\$\{ENV:([A-Za-z0-9_]+)\}", sub, node)
        return node

    data = walk(data)
    if not isinstance(data, dict):
        sys.exit("Config must be a YAML mapping.")
    data["_config_path"] = os.path.abspath(path)
    apply_defaults(data)
    validate(data)
    return data


def _validate_conventions(cfg):
    block = cfg.get("conventions")
    if block is None:
        return
    if not isinstance(block, dict):
        sys.exit("`conventions:` must be a mapping.")
    for key, value in block.items():
        if key not in conventions.DEFAULTS:
            sys.exit(f"Unknown conventions key `{key}`. "
                     f"Valid: {', '.join(sorted(conventions.DEFAULTS))}.")
        default = conventions.DEFAULTS[key]
        if isinstance(default, list):
            items = [value] if isinstance(value, str) else value
            if not isinstance(items, list) or not items or not all(
                    isinstance(item, str) and item.strip() for item in items):
                sys.exit(f"`conventions.{key}` must be a non-empty list of names.")
        elif not isinstance(value, str) or not str(value).strip():
            sys.exit(f"`conventions.{key}` must be a non-empty string.")


def _apply_convention_prompts(cfg):
    """Prompt lists follow conventions unless the prompt override set them."""
    resolved = cfg.get("_prompts") or {}
    mapping = {
        "brief.debrief": ("action_types", "action_issuetypes"),
        "inbox.file_note": ("note_types", "note_issuetypes"),
    }
    for prompt_id, (value_name, convention_key) in mapping.items():
        record = resolved.get(prompt_id)
        if not record or "values" in (record.get("parts") or []):
            continue
        value = conventions.get(cfg, convention_key)
        if isinstance(value, str):
            value = [value]
        record["values"][value_name] = list(value)


def _validate_page_id(label, value):
    if value is None:
        return
    if isinstance(value, int):
        return
    if isinstance(value, str) and value.isdigit():
        return
    sys.exit(f"{label} must be a page id.")


def _validate_confluence_ref(label, entry):
    page = entry.get("confluence_page")
    if page is not None and page is not False and not isinstance(page, str):
        sys.exit(f"{label}: `confluence_page` must be a page title, or false.")
    space = entry.get("confluence_space")
    if space is not None and not isinstance(space, str):
        sys.exit(f"{label}: `confluence_space` must be text.")
    if "confluence_page_id" in entry:
        _validate_page_id(f"{label}: `confluence_page_id`", entry.get("confluence_page_id"))


def _validate_registers(cfg):
    raw = cfg.get("registers")
    if raw is None:
        return
    if not isinstance(raw, list):
        sys.exit("`registers:` must be a list.")
    products = {p.get("abbrev") for p in (cfg.get("products") or []) if isinstance(p, dict)}
    streams = {w.get("abbrev") for w in (cfg.get("workstreams") or []) if isinstance(w, dict)}
    team_space = ((cfg.get("confluence") or {}).get("space")
                  if isinstance(cfg.get("confluence"), dict) else "")
    for reg in raw:
        if not isinstance(reg, dict):
            sys.exit("`registers:` entries must be mappings.")
        name = reg.get("name") or "register"
        if reg.get("type") not in ("decision", "risk", "adr"):
            sys.exit(f'Register "{name}": type must be decision, risk, or adr.')
        if not reg.get("name"):
            sys.exit("Each register needs a name.")
        space = reg.get("space") or team_space
        if not reg.get("page_id") and not (space and reg.get("title")):
            sys.exit(f'Register "{name}": set page_id, or both space and title. '
                     f"space may be omitted when confluence.space is set.")
        if reg.get("product") and reg.get("workstream"):
            sys.exit(f'Register "{name}": set product or workstream, not both.')
        if reg.get("product") and reg["product"] not in products:
            sys.exit(f'Register "{name}": unknown product {reg["product"]}.')
        if reg.get("workstream") and reg["workstream"] not in streams:
            sys.exit(f'Register "{name}": unknown workstream {reg["workstream"]}.')
        if reg.get("type") == "risk" and reg.get("partner_visible"):
            sys.exit(f'Register "{name}": a risk register cannot be partner_visible.')
        if reg.get("depth") not in (None, "descendants", "children"):
            sys.exit(f'Register "{name}": depth must be descendants or children.')
        if reg.get("split") not in (None, "label"):
            sys.exit(f'Register "{name}": split must be label.')
        if reg.get("split") == "label" and reg.get("workstream"):
            sys.exit(f'Register "{name}": split: label replaces a fixed workstream. '
                     f"Set product, or leave both off.")
        if reg.get("under") is not None and not isinstance(reg.get("under"), str):
            sys.exit(f'Register "{name}": under must be a page title.')
        if "under_id" in reg:
            _validate_page_id(f'Register "{name}": under_id', reg.get("under_id"))
        highlight = reg.get("highlight")
        if highlight is not None:
            if not isinstance(highlight, dict) or not isinstance(highlight.get("field"), str):
                sys.exit(f'Register "{name}": highlight needs a field and a list of values.')
            if not isinstance(highlight.get("values"), list):
                sys.exit(f'Register "{name}": highlight values must be a list.')


def _validate_audiences(cfg):
    block = cfg.get("audiences")
    if block is None:
        return
    if not isinstance(block, dict):
        sys.exit("`audiences:` must be a mapping.")
    if "default" in block and block["default"] not in ("pm", "leadership", "partner"):
        sys.exit("`audiences.default` must be pm, leadership, or partner.")
    for key in ("pm", "leadership", "partner"):
        section = block.get(key)
        if section is None:
            continue
        if not isinstance(section, dict):
            sys.exit(f"`audiences.{key}` must be a mapping.")
    if "warm" in block and not isinstance(block["warm"], list):
        sys.exit("`audiences.warm` must be a list.")


def _validate_confluence_tree(cfg):
    block = cfg.get("confluence")
    if not isinstance(block, dict):
        return
    for key in ("space", "team_page", "root_title"):
        if block.get(key) is not None and not isinstance(block.get(key), str):
            sys.exit(f"`confluence.{key}` must be text.")
    for key in ("team_page_id", "root_page_id"):
        if key in block:
            _validate_page_id(f"`confluence.{key}`", block.get(key))
    skip = block.get("skip")
    if skip is not None and not (
            isinstance(skip, list) and all(isinstance(item, (str, int)) for item in skip)):
        sys.exit("`confluence.skip` must be a list of page titles or page ids.")


def validate(cfg):
    """Check the whole config before a single Jira call is made.

    Everything a typo can break — products, workstream definitions, scope
    options, membership settings — is caught here, with a message that names
    the fix.
    """
    _validate_products(cfg)
    _validate_workstreams(cfg)
    _validate_membership(cfg)
    _validate_ready(cfg)
    _validate_blocked(cfg)
    _validate_model_budget(cfg)
    _validate_definition_of_done("Config", cfg.get("definition_of_done"))
    _validate_audiences(cfg)
    _validate_confluence_tree(cfg)
    _validate_registers(cfg)
    queries.validate_config(cfg)
    filters.validate_config_scopes(cfg)
    prompts.validate_config(cfg)
    _validate_conventions(cfg)
    _apply_convention_prompts(cfg)


def _validate_products(cfg):
    """Product abbreviations must be unique; `UNASSIGNED` is reserved."""
    entries = cfg.get("products")
    if entries is None:
        return
    if not isinstance(entries, list):
        sys.exit("`products:` must be a YAML list of products.")

    seen = {}
    for product in entries:
        if not isinstance(product, dict):
            sys.exit("Each product must be a mapping with `name` and `abbrev`.")
        label = product.get("abbrev") or product.get("name") or "(unnamed)"
        if not product.get("abbrev"):
            sys.exit(f"Product {label} needs an `abbrev` "
                     f"(the short name you pass to --product).")
        key = product["abbrev"].lower()
        if key == product_core.UNASSIGNED_ABBREV.lower():
            sys.exit(f"Product abbrev {product['abbrev']} is reserved for "
                     f"workstreams that do not name a product.")
        if key in seen:
            sys.exit(f"Two products share the abbrev {product['abbrev']}. "
                     f"Abbreviations must be unique.")
        seen[key] = True
        if not product.get("name"):
            sys.exit(f"Product {label} needs a `name`.")
        _validate_confluence_ref(f"Product {label}", product)
        goal = product.get("product_goal")
        if goal is not None and not isinstance(goal, str):
            sys.exit(f"Product {label}: `product_goal:` must be text.")
        _validate_definition_of_done(
            f"Product {label}", product.get("definition_of_done"))
        scopes = product.get("scopes")
        if scopes is not None and not isinstance(scopes, dict):
            sys.exit(f"Product {label}: `scopes:` must be a mapping of "
                     f"scope name to options.")


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

        product = (ws.get("product") or "").strip()
        if product:
            if product.lower() == product_core.UNASSIGNED_ABBREV.lower():
                sys.exit(f"Workstream {name}: `product: {product}` is reserved. "
                         f"Leave `product:` off to land in Unassigned.")
            if product_core.resolve_product(cfg, product) is None:
                available = ", ".join(p["abbrev"] for p in
                                      product_core.listed_products(cfg))
                if not available:
                    sys.exit(f"Workstream {name} names product {product}, but "
                             f"no products: are configured. Add it with:  "
                             f"pm products add --name ... --abbrev ...")
                sys.exit(f"Workstream {name} names unknown product {product}. "
                         f"Available: {available}.")

        mode = (cfg.get("membership") or {}).get("by") or "component"
        anchor_key = {"label": "labels", "field": "field_values"}.get(mode, "components")
        has_anchor = bool(ws_core.anchor_values(cfg, ws))
        has_legacy_jql = any(ws.get(f) for fields in
                             ws_core.LEGACY_FIELDS.values() for f in fields)

        if has_anchor and not ws_core.project_of(cfg, ws):
            sys.exit(f"Workstream {name} lists {anchor_key} but no project. "
                     f"Set `project:` on the workstream, or `jira.project` "
                     f"once for all of them.")
        if not has_anchor and not has_legacy_jql:
            sys.exit(f"Workstream {name} has no `{anchor_key}:` and no legacy "
                     f"JQL, so pm cannot tell which issues belong to it.")
        _validate_confluence_ref(f"Workstream {name}", ws)


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
    by = str(block.get("by") or "component").strip().lower()
    if by not in ("component", "label", "field"):
        sys.exit("`membership.by` must be component, label, or field.")
    if by == "field" and not str(block.get("field") or "").strip():
        sys.exit("`membership.field` is required when `membership.by` is field.")
    if by == "label" and block.get("child_component_wins"):
        sys.exit("`membership.child_component_wins` cannot be used with "
                 "`membership.by: label`. A child always carries other labels, "
                 "so \"has none of its own\" cannot be expressed.")


def _validate_ready(cfg):
    block = cfg.get("ready")
    if block is None:
        return
    points = block.get("max_points", 8)
    if isinstance(points, bool) or not isinstance(points, (int, float)):
        sys.exit("`ready.max_points` must be a number (default 8).")
    if points <= 0:
        sys.exit("`ready.max_points` must be greater than zero.")
    criteria = block.get("blocking_criteria")
    if criteria is not None and not isinstance(criteria, list):
        sys.exit("`ready.blocking_criteria` must be a list.")


def _name_list(block, key):
    value = block.get(key)
    if value is None:
        return
    if isinstance(value, str):
        return
    if not isinstance(value, list) or not all(
            isinstance(item, str) and item.strip() for item in value):
        sys.exit(f"`blocked.{key}` must be a list of names.")


def _validate_blocked(cfg):
    block = cfg.get("blocked")
    if block is None:
        return
    if not isinstance(block, dict):
        sys.exit("`blocked:` must be a mapping of statuses and labels.")
    _name_list(block, "statuses")
    _name_list(block, "labels")


def _validate_model_budget(cfg):
    block = cfg.get("model") or {}
    total = block.get("total_timeout")
    if total is None:
        return
    if isinstance(total, bool) or not isinstance(total, (int, float)) or total < 0:
        sys.exit("`model.total_timeout` must be a number of seconds, 0 or more.")
    ttl = (cfg.get("cache") or {}).get("model_ttl_seconds")
    if ttl is None:
        return
    if isinstance(ttl, bool) or not isinstance(ttl, (int, float)) or ttl < 0:
        sys.exit("`cache.model_ttl_seconds` must be a number of seconds, 0 or more.")


def _validate_definition_of_done(label, raw):
    """A printed checklist: text, or text plus an optional Jira label."""
    if raw is None:
        return
    if not isinstance(raw, list):
        sys.exit(f"{label}: `definition_of_done:` must be a list.")
    for item in raw:
        if isinstance(item, str) and item.strip():
            continue
        if isinstance(item, dict) and str(item.get("text") or "").strip():
            mark = item.get("label")
            if mark is not None and not isinstance(mark, str):
                sys.exit(f"{label}: Definition of Done `label:` must be text.")
            continue
        sys.exit(f"{label}: Definition of Done lines are text, or "
                 f"`text:` plus an optional `label:`.")


def filter_workstreams(cfg, selector):
    """Narrow cfg['workstreams'] to those named in `selector`.

    `selector` is a comma-separated string of abbreviations or full names
    (case-insensitive), e.g. "SDX" or "Secure Data Exchange". Returns the
    filtered list. Exits with a helpful message if a name doesn't match any
    workstream, so a typo fails loudly rather than silently doing nothing.
    """
    if not selector:
        return cfg["workstreams"]

    wanted = [s.strip().lower() for s in selector.split(",") if s.strip()]
    by_abbrev = {}
    by_name = {}
    for ws in cfg["workstreams"]:
        by_abbrev[ws["abbrev"].lower()] = ws
        if ws.get("name"):
            by_name.setdefault(ws["name"].lower(), ws)

    resolved, unknown = [], []
    for wanted_name in wanted:
        if wanted_name in by_abbrev:
            resolved.append(by_abbrev[wanted_name])
        elif wanted_name in by_name:
            resolved.append(by_name[wanted_name])
        else:
            unknown.append(wanted_name)
    if unknown:
        available = ", ".join(ws["abbrev"] for ws in cfg["workstreams"])
        sys.exit(f"Unknown workstream(s): {', '.join(unknown)}. "
                 f"Available: {available}.")

    return resolved
