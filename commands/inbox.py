"""`pm note` / `pm inbox` — capture now, file later.

Capture is instant and offline. Filing happens from the inbox, with a
model suggestion you can edit, and a Jira create that is previewed first.
"""

import datetime as dt
import json
import os
import sys

from core import model, paths, products as product_core, writes


INBOX_PROMPT = """\
Suggest how to file this note as a Jira Product Backlog item.

Return a JSON object with exactly these keys:
- "product": a product abbrev from the list, or ""
- "workstream": a workstream abbrev from the list, or ""
- "issuetype": Story, Task, or Bug
- "title": a clear title
- "criteria": one or two Given/When/Then lines, or ""

Use ONLY abbrevs from the list. Do not invent people or dates.
file this note. Do not write any text outside the JSON object.
"""


def _load(cfg):
    path = paths.inbox_path(cfg)
    if not os.path.exists(path):
        return {"next": 1, "notes": []}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (ValueError, OSError):
        return {"next": 1, "notes": []}


def _save(cfg, store):
    path = paths.inbox_path(cfg)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(store, fh, indent=2)


def _note(cfg, args):
    text = " ".join(getattr(args, "text", None) or [])
    if not text:
        sys.exit("What should I capture? e.g.  pm note \"customer wants SSO export\"")
    store = _load(cfg)
    n = store.get("next", 1)
    store["next"] = n + 1
    store.setdefault("notes", []).append({
        "n": n,
        "text": text,
        "at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "workstream": getattr(args, "workstream", None),
        "product": getattr(args, "product", None),
    })
    _save(cfg, store)
    print(f"Captured #{n}. Nothing else needed now.")


def _catalogue(cfg):
    products = product_core.listed_products(cfg)
    streams = cfg.get("workstreams") or []
    lines = ["Products: " + ", ".join(p["abbrev"] for p in products)]
    lines.append("Workstreams: " + ", ".join(
        f"{w['abbrev']} ({w.get('product') or 'UNASSIGNED'})" for w in streams))
    return "\n".join(lines)


def _suggest(cfg, note):
    user = (
        f"{_catalogue(cfg)}\n\n"
        f"Note: {note['text']}\n"
        f"Tagged workstream: {note.get('workstream') or '(none)'}\n"
        f"Tagged product: {note.get('product') or '(none)'}\n\n"
        f"Return the JSON object now."
    )
    raw = model.call_model(cfg["model"], INBOX_PROMPT, user)
    try:
        # Prefer a JSON object even if the model wrapped it.
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            return {}
        data = json.loads(raw[start:end + 1])
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def _list(cfg, args):
    store = _load(cfg)
    notes = [n for n in store.get("notes") or [] if not n.get("dropped")]
    if not notes:
        print("Inbox is empty. Capture with:  pm note \"...\"")
        return
    for note in notes:
        print(f"#{note['n']}  {note['text']}")
        print(f"    {note.get('at', '')[:16].replace('T', ' ')}")
        suggestion = _suggest(cfg, note)
        title = note.get("title") or suggestion.get("title")
        criteria = note.get("criteria") or suggestion.get("criteria")
        stream = note.get("workstream") or suggestion.get("workstream")
        if suggestion or note.get("title") or note.get("criteria"):
            print(f"    suggests   {suggestion.get('product') or '—'} · "
                  f"{stream or '—'} · "
                  f"{suggestion.get('issuetype') or 'Story'}")
        if title:
            print(f"    title      {title}")
        if criteria:
            print(f"    criteria   {criteria}")
        print(f"    → pm inbox create {note['n']}    "
              f"pm inbox edit {note['n']}    "
              f"pm inbox drop {note['n']}")
        print("")


def _drop(cfg, args):
    n = getattr(args, "target", None)
    if n is None:
        sys.exit("Which note? e.g.  pm inbox drop 7")
    store = _load(cfg)
    for note in store.get("notes") or []:
        if note.get("n") == n:
            note["dropped"] = True
            _save(cfg, store)
            print(f"Dropped #{n}.")
            return
    sys.exit(f"No inbox note #{n}.")


def _create(cfg, args):
    n = getattr(args, "target", None)
    if n is None:
        sys.exit("Which note? e.g.  pm inbox create 7")
    store = _load(cfg)
    note = next((x for x in store.get("notes") or [] if x.get("n") == n
                 and not x.get("dropped")), None)
    if note is None:
        sys.exit(f"No inbox note #{n}.")
    suggestion = _suggest(cfg, note)
    # Stored edits win over the model, so a correction made before create
    # is the one that gets filed. The model does not overwrite them.
    title = (getattr(args, "title", None) or note.get("title")
             or suggestion.get("title") or note["text"])
    itype = getattr(args, "issuetype", None) or suggestion.get("issuetype") or "Story"
    product = note.get("product") or suggestion.get("product")
    stream_ab = (getattr(args, "workstream", None) or note.get("workstream")
                 or suggestion.get("workstream"))
    ws = None
    if stream_ab:
        ws = next((w for w in (cfg.get("workstreams") or [])
                   if w["abbrev"].lower() == str(stream_ab).lower()), None)
    from core import workstreams as ws_core
    project = (ws_core.project_of(cfg, ws) if ws
               else (cfg.get("jira") or {}).get("project"))
    components = ws_core.components_of(ws) if ws else []
    criteria = (getattr(args, "criteria", None) or note.get("criteria")
                or suggestion.get("criteria") or "")
    fields = {
        "project": {"key": project},
        "summary": title,
        "issuetype": {"name": itype},
    }
    if components:
        fields["components"] = [{"name": c} for c in components]
    if criteria:
        fields["description"] = writes.adf_doc(
            f"Captured from inbox #{n}.\n\nAcceptance criteria:\n{criteria}")
    else:
        fields["description"] = writes.adf_doc(f"Captured from inbox #{n}: {note['text']}")
    action = writes.action_create_issue(fields, kind="inbox-create", summary=title)
    result = writes.apply_action(cfg, args, action)
    if result and result.get("key"):
        note["dropped"] = True
        note["created"] = result["key"]
        _save(cfg, store)


def run_note(cfg, args):
    _note(cfg, args)


def _edit(cfg, args):
    """Correct a note before create. Writes inbox.json only."""
    n = getattr(args, "target", None)
    if n is None:
        sys.exit("Which note? e.g.  pm inbox edit 7 --title \"Clearer title\"")
    title = getattr(args, "title", None)
    stream = getattr(args, "workstream", None)
    criteria = getattr(args, "criteria", None)
    if title is None and stream is None and criteria is None:
        sys.exit("What should change? Pass --title, --workstream, or --criteria.")
    store = _load(cfg)
    note = next((x for x in store.get("notes") or [] if x.get("n") == n
                 and not x.get("dropped")), None)
    if note is None:
        sys.exit(f"No inbox note #{n}.")
    if title is not None:
        note["title"] = title
    if stream is not None:
        note["workstream"] = stream
    if criteria is not None:
        note["criteria"] = criteria
    _save(cfg, store)
    print(f"Updated #{n}. Nothing was sent to Jira.")


def run_inbox(cfg, args):
    action = getattr(args, "action", "list") or "list"
    if action == "list":
        _list(cfg, args)
    elif action == "create":
        _create(cfg, args)
    elif action == "drop":
        _drop(cfg, args)
    elif action == "edit":
        _edit(cfg, args)
    else:
        sys.exit(f"Unknown inbox action {action}. Try: list, edit, create, drop.")
