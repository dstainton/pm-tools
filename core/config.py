"""Configuration loading, shared by every command.

Reads the YAML config and expands ${ENV:VAR} placeholders found in VALUES
(not comments), so tokens can be kept in environment variables if you prefer.
"""

import os
import re
import sys

import yaml

from core import filters, products as product_core, workstreams as ws_core


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

    Everything a typo can break — products, workstream definitions, scope
    options, membership settings — is caught here, with a message that names
    the fix.
    """
    _validate_products(cfg)
    _validate_workstreams(cfg)
    _validate_membership(cfg)
    filters.validate_config_scopes(cfg)


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
