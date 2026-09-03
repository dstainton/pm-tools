"""Products sit above workstreams.

A product is a name, an abbreviation, and optional per-product defaults
(Jira project, scopes). Each workstream may name the product it belongs to
with `product: <abbrev>`. A workstream with no `product:` lands in an
implicit Unassigned product, so a config written before this layer existed
keeps working.

The workstream list stays flat: `pm workstreams add` / `remove` do not
change, and `--workstream` still works. `--product` is the new filter, and
the two compose — a typo in either name fails loudly.
"""

import sys


UNASSIGNED_ABBREV = "UNASSIGNED"
UNASSIGNED_NAME = "Unassigned"


def unassigned_product():
    return {"name": UNASSIGNED_NAME, "abbrev": UNASSIGNED_ABBREV}


def listed_products(cfg):
    """The `products:` block, or an empty list when none are configured."""
    entries = cfg.get("products") or []
    return list(entries) if isinstance(entries, list) else []


def product_abbrev_of(ws):
    """The product abbreviation a workstream belongs to (Unassigned if none)."""
    value = (ws.get("product") or "").strip()
    return value or UNASSIGNED_ABBREV


def resolve_product(cfg, abbrev):
    """Look up a product by abbreviation. Unassigned is always resolvable."""
    if not abbrev or abbrev.lower() == UNASSIGNED_ABBREV.lower():
        return unassigned_product()
    key = abbrev.lower()
    for product in listed_products(cfg):
        if (product.get("abbrev") or "").lower() == key:
            return product
    return None


def product_project(cfg, product_or_abbrev):
    """The Jira project a product names, or None."""
    if isinstance(product_or_abbrev, dict):
        product = product_or_abbrev
    else:
        product = resolve_product(cfg, product_or_abbrev)
    if not product:
        return None
    return product.get("project") or None


def products_in_use(cfg, workstreams=None):
    """Configured products, plus Unassigned when any selected stream is untagged.

    Configured products keep their file order. Unassigned is last, and only
    present when at least one of `workstreams` has no `product:`.
    """
    streams = (workstreams if workstreams is not None
               else (cfg.get("workstreams") or []))
    used = {product_abbrev_of(ws).lower() for ws in streams}
    out = list(listed_products(cfg))
    if UNASSIGNED_ABBREV.lower() in used:
        out.append(unassigned_product())
    return out


def group_workstreams(cfg, workstreams):
    """[(product, [workstream, ...]), ...] in product then workstream order.

    Products that have no workstreams in the given list are omitted, so a
    `--product` / `--workstream` filter does not print empty sections.
    """
    groups = []
    index = {}
    for product in products_in_use(cfg, workstreams):
        key = product["abbrev"].lower()
        index[key] = []
        groups.append((product, index[key]))

    for ws in workstreams:
        key = product_abbrev_of(ws).lower()
        if key not in index:
            product = resolve_product(cfg, key) or unassigned_product()
            index[key] = []
            groups.append((product, index[key]))
        index[key].append(ws)

    return [(product, streams) for product, streams in groups if streams]


def filter_by_product(cfg, workstreams, selector):
    """Narrow a workstream list to those in the named product(s).

    `selector` is a comma-separated string of product abbreviations
    (case-insensitive). Unknown names fail with the list of valid ones.
    """
    if not selector:
        return list(workstreams)

    wanted = [s.strip().lower() for s in selector.split(",") if s.strip()]
    available = {}
    for product in listed_products(cfg):
        if product.get("abbrev"):
            available[product["abbrev"].lower()] = product
    available[UNASSIGNED_ABBREV.lower()] = unassigned_product()

    unknown = [name for name in wanted if name not in available]
    if unknown:
        names = ", ".join(p["abbrev"] for p in listed_products(cfg))
        if UNASSIGNED_ABBREV.lower() in {
                product_abbrev_of(ws).lower()
                for ws in (cfg.get("workstreams") or [])}:
            names = (names + ", " + UNASSIGNED_ABBREV) if names \
                else UNASSIGNED_ABBREV
        if not names:
            names = UNASSIGNED_ABBREV
        sys.exit(f"Unknown product(s): {', '.join(unknown)}. "
                 f"Available: {names}.")

    wanted_set = set(wanted)
    picked = [ws for ws in workstreams
              if product_abbrev_of(ws).lower() in wanted_set]
    if not picked:
        labels = ", ".join(selector.split(","))
        sys.exit(f"No workstreams belong to product(s): {labels}.")
    return picked


def workstreams_of(cfg, product_abbrev, workstreams=None):
    """Workstreams tagged with `product_abbrev` (case-insensitive)."""
    streams = workstreams if workstreams is not None else (cfg.get("workstreams") or [])
    key = (product_abbrev or UNASSIGNED_ABBREV).lower()
    return [ws for ws in streams if product_abbrev_of(ws).lower() == key]
