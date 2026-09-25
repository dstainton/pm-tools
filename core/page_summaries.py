"""One cached sentence per Confluence page version."""

import datetime as dt
import hashlib
import json
import os

from core import cache as cache_core
from core import model, pages, prompts


PAGE_KINDS = ("decision", "risk", "dependency", "requirement", "design",
              "meeting", "status", "other")


def store_path(cfg):
    folder = os.path.join(cache_core.settings(cfg)["path"], "pages")
    os.makedirs(folder, exist_ok=True)
    return folder


def _record_path(cfg, page):
    return os.path.join(store_path(cfg), f"{page.get('page_id')}-{page.get('version')}.json")


def load(cfg, page):
    path = _record_path(cfg, page)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def save(cfg, page, record):
    path = _record_path(cfg, page)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh)


def summarise(cfg, page, refresh=False):
    """{"summary", "kind"}. A stored version is reused unless refresh is set."""
    if page.get("title_only"):
        return {"summary": "", "kind": ""}
    if not refresh:
        stored = load(cfg, page)
        if stored:
            return {"summary": stored.get("summary") or "", "kind": stored.get("kind") or ""}
    opts = pages.page_settings(cfg)
    body = (page.get("body_text") or "")[: int(opts.get("summary_chars") or 6000)]
    user = (
        f"Page {page.get('page_id')}, version {page.get('version')} ({page.get('type') or 'page'})\n"
        f"Title: {page.get('title') or ''}\n"
        f"Labels: {', '.join(page.get('labels') or [])}\n\n"
        f"Text:\n{body}\n\n"
        f"{prompts.get(cfg, 'pages.tail')}"
    )
    data, _err = model.call_model_json(
        cfg.get("model") or {}, prompts.get(cfg, "pages.summary"), user)
    if not data:
        return {"summary": "", "kind": ""}
    row = data[0] if isinstance(data[0], dict) else {}
    summary = str(row.get("summary") or "")[:240]
    kind = str(row.get("kind") or "")
    if kind not in PAGE_KINDS:
        kind = "other"
    record = {"summary": summary, "kind": kind,
              "model": (cfg.get("model") or {}).get("name") or "",
              "stored_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    save(cfg, page, record)
    return {"summary": summary, "kind": kind}


def pick_epic(cfg, page, candidates):
    """One listed Epic key, or '' . Stored beside the summary."""
    keys = [row.get("key") for row in candidates if row.get("key")]
    if not keys or not page.get("summary"):
        return ""
    digest = hashlib.sha256(",".join(keys).encode("utf-8")).hexdigest()[:12]
    path = os.path.join(store_path(cfg),
                        f"{page.get('page_id')}-{page.get('version')}-epic-{digest}.json")
    try:
        with open(path, encoding="utf-8") as fh:
            stored = json.load(fh)
        if stored.get("epic") in keys or stored.get("epic") == "":
            return stored.get("epic") or ""
    except (OSError, ValueError):
        stored = None
    lines = "\n".join(f"- {row.get('key')}: {row.get('summary') or ''}" for row in candidates if row.get("key"))
    user = (
        f"Epics:\n{lines}\n\n"
        f"Page: {page.get('title') or ''}\n"
        f"Summary: {page.get('summary') or ''}\n\n"
        f"{prompts.get(cfg, 'pages.tail')}"
    )
    data, _err = model.call_model_json(
        cfg.get("model") or {}, prompts.get(cfg, "pages.epic_match"), user)
    chosen = ""
    if data and isinstance(data[0], dict):
        chosen = str(data[0].get("epic") or "")
    if chosen not in keys:
        chosen = ""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"epic": chosen}, fh)
    return chosen


def apply_kind(page):
    """Label kind wins, then the summary kind, then other. A blog stays an update."""
    if not page.get("kind"):
        page["kind"] = page.get("_summary_kind") or "other"
    if page.get("type") == "blogpost" and page.get("kind") == "other":
        page["kind"] = "update"
    return page


def fill(cfg, pages_in, budget=None):
    """Summarise newest first. Returns how many model calls were made."""
    opts = pages.page_settings(cfg)
    if not opts.get("summaries"):
        return 0
    cap = opts["max_summaries"] if budget is None else budget
    ordered = sorted(pages_in, key=lambda page: page.get("updated") or "", reverse=True)
    calls = 0
    for page in ordered:
        if page.get("title_only"):
            continue
        stored = load(cfg, page)
        if stored:
            page["summary"] = stored.get("summary") or ""
            page["_summary_kind"] = stored.get("kind") or ""
            apply_kind(page)
            continue
        if calls >= cap:
            page["summary"] = ""
            page["unsummarised"] = True
            continue
        before = load(cfg, page)
        result = summarise(cfg, page)
        if result.get("summary") and before is None:
            calls += 1
        page["summary"] = result.get("summary") or ""
        page["_summary_kind"] = result.get("kind") or ""
        apply_kind(page)
    return calls
