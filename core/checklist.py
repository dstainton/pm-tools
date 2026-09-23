"""Definition of Done as a printed checklist.

A line is a reminder. A line that also sets `label:` is still a reminder,
and `pm ready` can warn when a Done item lacks that label. Nothing here
decides that an item is Done.
"""


def definition_items(cfg, product=None):
    """The checklist for one product, or the shared list when the product
    does not set its own.

    Each item is ``{"text": str, "label": str or None}``.
    """
    raw = None
    if isinstance(product, dict) and product.get("definition_of_done"):
        raw = product.get("definition_of_done")
    elif cfg:
        raw = cfg.get("definition_of_done")
    return parse_items(raw)


def parse_items(raw):
    if not raw:
        return []
    items = []
    for entry in raw:
        if isinstance(entry, str):
            text = entry.strip()
            label = None
        elif isinstance(entry, dict):
            text = str(entry.get("text") or "").strip()
            label = entry.get("label")
            label = str(label).strip() if isinstance(label, str) and label.strip() else None
        else:
            continue
        if text:
            items.append({"text": text, "label": label})
    return items


def product_goal(product):
    """The Product Goal sentence, or "" when the product does not set one."""
    if not isinstance(product, dict):
        return ""
    goal = product.get("product_goal")
    if not isinstance(goal, str):
        return ""
    return goal.strip()
