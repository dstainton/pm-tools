"""Who a report is for: product management, leadership, or partners."""

import os
import re

from core import output


LEVELS = ("pm", "leadership", "partner")

DEFAULTS = {
    "default": "pm",
    "warm": ["pm"],
    "pm": {"name": "Product management"},
    "leadership": {"name": "Leadership", "at_risk_due_days": 14, "max_docs_per_product": 5},
    "partner": {
        "name": "Partners",
        "epic_labels": ["partner-visible"],
        "page_labels": ["partner-visible"],
        "exclude_labels": ["internal"],
        "include_jira_links": False,
        "include_confluence_links": False,
        "show_target_dates": False,
    },
}


def settings(cfg):
    block = cfg.get("audiences") if isinstance(cfg.get("audiences"), dict) else {}
    out = {
        "default": block.get("default") or DEFAULTS["default"],
        "warm": list(block.get("warm") or DEFAULTS["warm"]),
    }
    for level in LEVELS:
        merged = dict(DEFAULTS[level])
        override = block.get(level) if isinstance(block.get(level), dict) else {}
        merged.update(override)
        out[level] = merged
    return out


def level(cfg, args):
    chosen = getattr(args, "audience", None) if args is not None else None
    chosen = chosen or settings(cfg)["default"] or "pm"
    if chosen not in LEVELS:
        raise SystemExit(
            f"Unknown audience {chosen}. Use one of: {', '.join(LEVELS)}.")
    return chosen


def display_name(cfg, who):
    return settings(cfg).get(who, {}).get("name") or who


def state_path(cfg, who, args):
    name = (cfg.get("output") or {}).get("state_file") or "report_state.json"
    if who != "pm":
        root, ext = os.path.splitext(name)
        name = f"{root}_{who}{ext or '.json'}"
    return output.place(cfg, name, getattr(args, "out", None) if args else None)


def output_name(cfg, who, date):
    template = (cfg.get("output") or {}).get("file") or "weekly_report_{date}.md"
    if "{audience}" in template:
        return template.format(date=date, audience=who)
    if who == "pm":
        return template.format(date=date)
    if "{date}" in template:
        return template.format(date=f"{who}_{date}")
    root, ext = os.path.splitext(template.format(date=date))
    return f"{root}_{who}{ext}"


def partner_visible_epic(epic, ws, opts):
    labels = {str(label).lower() for label in (epic.get("labels") or [])}
    wanted = {str(label).lower() for label in (opts.get("epic_labels") or [])}
    if labels & wanted:
        return True
    return bool((ws or {}).get("partner_visible"))


def partner_visible_page(page, opts):
    labels = {str(label).lower() for label in (page.get("labels") or [])}
    wanted = {str(label).lower() for label in (opts.get("page_labels") or [])}
    return bool(labels & wanted)


def redact(text, names, allowed_keys, drop_all_keys=False):
    """Drop lines that name a person or a key that is not allowed."""
    kept = []
    removed = 0
    key_re = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
    name_set = {name for name in names if name and name not in ("Unassigned",)}
    for line in (text or "").splitlines():
        if any(name in line for name in name_set):
            removed += 1
            continue
        keys = key_re.findall(line)
        if drop_all_keys and keys:
            removed += 1
            continue
        if any(key not in allowed_keys for key in keys):
            removed += 1
            continue
        kept.append(line)
    return "\n".join(kept), removed
