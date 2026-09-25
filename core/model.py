"""The local-model call, shared by any command that needs inference.

Talks to an OpenAI-compatible local endpoint (llama.cpp). Nothing leaves the
machine beyond that server.

Prompts and sampling are tuned for **Qwen3.8-27B Q3_K_M** in instruct
(non-thinking) mode:

* Qwen3.8 thinks by default. A Q3_K_M run that is allowed to think will spend
  its token budget inside ``<think>`` and return empty or half-cut JSON. Every
  request therefore turns thinking off, and any leftover think block is stripped.
* Q3_K_M follows short, numbered instructions and a fill-in skeleton much more
  reliably than a long essay of rules. Format goes last; one example is worth
  a paragraph of description.
* Official Qwen instruct sampling is temperature 0.7 / top_p 0.8 / top_k 20 /
  presence_penalty 1.5. JSON calls drop the temperature further so a 3-bit
  quant is less likely to invent keys or wrap the array in prose.
"""

import json
import os
import re
import time

import requests

from core import model_cache, prompts


# ---------------------------------------------------------------------------
#  Prompts — short, numbered, format last. Written for Qwen3.8 Q3_K_M.
# ---------------------------------------------------------------------------
# The text lives in core.prompts. These names stay so existing callers and
# tests keep working. REPORT_SYSTEM_PROMPT still contains {audience}.

REPORT_HEADINGS = prompts.headings(None)
EMPTY_SECTION = prompts.values_of(None, "report.section")["empty_section"]
FIRST_RUN_LINE = prompts.values_of(None, "report.section")["first_run_line"]
REPORT_SYSTEM_PROMPT = prompts.get(None, "report.section", audience="{audience}")
REPORT_USER_TAIL = prompts.get(None, "report.section_tail")


# ---------------------------------------------------------------------------
#  Thinking / chat-template helpers
# ---------------------------------------------------------------------------

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_THINK_TAG = re.compile(r"</?think>", re.IGNORECASE)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def strip_thinking(text):
    """Remove Qwen3.8 think blocks so only the visible answer remains."""
    if not text:
        return ""
    cleaned = _THINK_BLOCK.sub("", text)
    cleaned = _THINK_TAG.sub("", cleaned)
    return cleaned.strip()


def message_text(payload):
    """Pull the assistant text out of an OpenAI-shaped chat response."""
    try:
        msg = payload["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return ""
    content = msg.get("content") or ""
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                parts.append(part.get("text") or part.get("content") or "")
            else:
                parts.append(str(part))
        content = "".join(parts)
    return strip_thinking(content)


def _with_no_think(model_cfg, user_content):
    """Prefix /no_think so Qwen3 hybrid templates skip the think block.

    Harmless on a server that already disabled thinking; ignored by models
    that do not recognise the token.
    """
    if model_cfg.get("enable_thinking"):
        return user_content
    if model_cfg.get("no_think_suffix", True) is False:
        return user_content
    if user_content.lstrip().startswith("/no_think"):
        return user_content
    return "/no_think\n" + user_content


def build_payload(model_cfg, system_prompt, user_content, temperature=None):
    """OpenAI-compatible body, with Qwen3.8 instruct-mode knobs filled in."""
    thinking = bool(model_cfg.get("enable_thinking", False))
    payload = {
        "model": model_cfg["name"],
        "temperature": (model_cfg["temperature"] if temperature is None
                        else temperature),
        "max_tokens": model_cfg["max_tokens"],
        "top_p": model_cfg.get("top_p", 0.8),
        "presence_penalty": model_cfg.get("presence_penalty", 1.5),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _with_no_think(model_cfg, user_content)},
        ],
        "chat_template_kwargs": {
            "enable_thinking": thinking,
            "preserve_thinking": False,
        },
    }
    top_k = model_cfg.get("top_k", 20)
    if top_k is not None:
        payload["top_k"] = top_k
    return payload


# ---------------------------------------------------------------------------
#  The two call flavours
# ---------------------------------------------------------------------------

BUDGET_MESSAGE = (
    "_The model budget for this run is used up. "
    "Raise model.total_timeout, or run `pm warm` first._"
)


def _used_temperature(model_cfg, temperature):
    if temperature is None:
        return model_cfg.get("temperature")
    return temperature


def _over_budget(model_cfg):
    deadline = model_cfg.get("_deadline")
    return deadline is not None and time.monotonic() > deadline


def attach(cfg, mode="default"):
    """Point model calls at the result cache and arm the run budget.

    Called once from `pm` after the fetch cache is attached. Commands that
    call the model directly in a test skip this and simply do not cache.
    """
    from core import cache as fetch_cache
    from core import paths

    model_cfg = cfg.setdefault("model", {})
    opts = fetch_cache.settings(cfg)
    block = cfg.get("cache") if isinstance(cfg.get("cache"), dict) else {}
    try:
        model_ttl = int(block.get("model_ttl_seconds", model_cache.DEFAULT_TTL)
                        or model_cache.DEFAULT_TTL)
    except (TypeError, ValueError):
        model_ttl = model_cache.DEFAULT_TTL
    model_cfg["_cache_mode"] = mode if mode in ("default", "cached", "refresh") else "default"
    model_cfg["_model_cache_enabled"] = bool(opts["enabled"])
    model_cfg["_model_cache_path"] = os.path.join(opts["path"], "model")
    model_cfg["_model_ttl"] = max(0, model_ttl)
    model_cfg["_timing_path"] = os.path.join(paths.local_dir(cfg), "model_timing.json")
    model_cfg["_calls"] = 0
    model_cfg["_cache_hits"] = 0
    total = model_cfg.get("total_timeout") or 0
    try:
        total = float(total)
    except (TypeError, ValueError):
        total = 0
    if total > 0:
        model_cfg["_deadline"] = time.monotonic() + total
    else:
        model_cfg.pop("_deadline", None)
    return model_cfg


def announce(model_cfg, count, what):
    """Print the call count and an estimate before a multi-call run."""
    model_cfg["_progress_total"] = count
    model_cfg["_progress_done"] = 0
    if count < 2:
        return
    seconds, measured = _read_rate(model_cfg)
    if seconds:
        minutes = max(1, int(round(count * seconds / 60.0)))
        when = f", {measured}" if measured else ""
        print(f"{what} — {count} model calls. "
              f"Last measured: {seconds:.0f}s per call (pm doctor{when}). "
              f"Estimate: ~{minutes} minute{'s' if minutes != 1 else ''}.")
    else:
        print(f"{what} — {count} model calls. "
              f"Run `pm doctor` once to time the model on this machine.")


def tick(model_cfg, detail):
    """One line of progress for a run `announce` already counted."""
    total = int(model_cfg.get("_progress_total") or 0)
    done = int(model_cfg.get("_progress_done") or 0) + 1
    model_cfg["_progress_done"] = done
    if total >= 2:
        print(f"  [{done}/{total}] {detail}")


def _read_rate(model_cfg):
    path = model_cfg.get("_timing_path")
    if not path or not os.path.exists(path):
        return None, None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None, None
    seconds = data.get("seconds")
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds <= 0:
        return None, None
    return float(seconds), str(data.get("measured") or "")


def _remember_rate(model_cfg, elapsed):
    path = model_cfg.get("_timing_path")
    if not path:
        return
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    import datetime as dt
    record = {
        "seconds": round(float(elapsed), 2),
        "measured": dt.date.today().isoformat(),
        "model": model_cfg.get("name") or "",
    }
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(record, fh)
    os.replace(tmp, path)


def call_model(model_cfg, system_prompt, user_content, temperature=None,
               use_cache=True):
    """Send one system+user turn and return the visible assistant text.

    Returns a readable error string (never raises) so a single failed call
    does not sink a whole run. A cached reply is returned without a call.
    `pm doctor` passes use_cache=False so a ping times the model itself.
    """
    used = _used_temperature(model_cfg, temperature)
    if use_cache:
        cached = model_cache.lookup(model_cfg, system_prompt, user_content, used)
        if cached is not None:
            model_cfg["_cache_hits"] = int(model_cfg.get("_cache_hits") or 0) + 1
            return cached
    if _over_budget(model_cfg):
        return BUDGET_MESSAGE
    payload = build_payload(model_cfg, system_prompt, user_content, temperature)
    model_cfg["_calls"] = int(model_cfg.get("_calls") or 0) + 1
    try:
        resp = requests.post(model_cfg["endpoint"], json=payload,
                             timeout=model_cfg["timeout"])
        resp.raise_for_status()
        text = message_text(resp.json())
        text = text or "_The model returned an empty reply._"
    except requests.RequestException as err:
        return (f"_Could not reach the model endpoint ({err}). "
                f"Is the local OpenAI-compatible server running?_")
    if use_cache:
        model_cache.store(model_cfg, system_prompt, user_content, used, text)
    return text


def call_model_json(model_cfg, system_prompt, user_content):
    """Like call_model, but expects a JSON array and parses it robustly.

    Qwen3.8 Q3_K_M sometimes wraps JSON in a think block, a fence, or a
    sentence. We strip those, then take the first well-formed array.
    Returns (data, error): (list, None) on success, (None, reason) on failure.
    """
    json_temp = model_cfg.get("json_temperature", 0.2)
    raw = call_model(model_cfg, system_prompt, user_content,
                     temperature=json_temp)
    if raw.startswith("_Could not reach") or raw.startswith("_The model"):
        return None, raw

    text = strip_thinking(raw)
    text = _FENCE.sub("", text).strip()

    for candidate in (text, _first_json_array(text)):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(data, list):
            return data, None
        # A single object is a common Q3 slip; wrap it.
        if isinstance(data, dict):
            return [data], None
    return None, f"Model did not return valid JSON. Raw start: {raw[:120]}..."


def _first_json_array(text):
    """Return the substring from the first '[' to its matching ']', or ''."""
    start = text.find("[")
    if start == -1:
        return ""
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return ""


# ---------------------------------------------------------------------------
#  Report assembly
# ---------------------------------------------------------------------------

def build_material(items, max_items=40, detail_limit=180, comment_budget=6000):
    """Turn gathered items into a compact, taggable block for the model.

    Q3_K_M loses the plot when the prompt is a wall of text, so we cap both
    how many items go in and how long each detail line is. Comment lines
    keep their own length and share `comment_budget` characters across the
    section. The status line stays on `detail_limit`.
    """
    if not items:
        return "(No items were found for this workstream.)"
    lines = []
    shown = items[:max_items]
    used = 0
    omitted_comments = 0
    limit = 0 if comment_budget is None else int(comment_budget)
    for it in shown:
        block = f"[{it['ref']}] ({it['source']}) {it['title']}"
        if it.get("detail"):
            detail_cap = detail_limit
            if it.get("source") in ("Confluence", "SharePoint"):
                detail_cap = int(it.get("excerpt_chars") or 2000)
            block += f"\n    {short_detail(it['detail'], detail_cap)}"
        wrote = False
        for line in it.get("comments") or []:
            if used + len(line) > limit:
                break
            block += f"\n    {line}"
            used += len(line)
            wrote = True
        if (it.get("comments") or []) and not wrote:
            omitted_comments += 1
        lines.append(block)
    omitted = len(items) - len(shown)
    if omitted:
        lines.append(f"(+{omitted} more items omitted to keep the prompt short.)")
    if omitted_comments:
        lines.append(
            f"(+{omitted_comments} commented issues omitted "
            f"to keep the prompt short.)")
    return "\n".join(lines)


def short_detail(text, limit):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def ping(model_cfg):
    """Cheap connectivity check for `pm doctor`. Returns (ok, detail)."""
    import time
    start = time.monotonic()
    text = call_model(model_cfg, "Reply with the single word pong and nothing else.",
                      "pong", use_cache=False)
    elapsed = time.monotonic() - start
    thinking = "thinking on" if model_cfg.get("enable_thinking") else "thinking off"
    if text.startswith("_Could not reach"):
        return False, f"{text} ({elapsed:.1f}s)"
    if text.startswith("_The model returned an empty"):
        return False, f"empty reply in {elapsed:.1f}s, {thinking}"
    _remember_rate(model_cfg, elapsed)
    return True, f"answered in {elapsed:.1f}s, {thinking}"


def infer_leadership(model_cfg, product, facts, cfg=None):
    return call_model(model_cfg, prompts.get(cfg, "report.leadership"),
                      f"Product: {product.get('name')} ({product.get('abbrev')})\n\n{facts}\n")


def infer_partner(model_cfg, product, facts, cfg=None):
    return call_model(model_cfg, prompts.get(cfg, "report.partner"),
                      f"Product: {product.get('name')}\n\n{facts}\n")


def _item_line(item):
    """One Jira child, in the grouped-material shape."""
    kind = item.get("issuetype") or "Item"
    title = item.get("summary") or item.get("title") or item.get("key") or "item"
    bits = [f"  [{item.get('ref') or item.get('key')}] ({kind}) {title}"]
    status = item.get("status") or ""
    assignee = item.get("assignee") or ""
    extra = []
    if status:
        extra.append(f"Status: {status}")
    if assignee:
        extra.append(f"Assignee: {assignee}")
    if extra:
        bits[0] += " | " + " | ".join(extra)
    return bits


def _page_line(page, budget):
    """A document line, plus its summary. Excerpt only while `budget` remains.

    Returns (lines, budget_left). A page that does not fit is title and summary.
    """
    tag = page.get("ref") or "D?"
    kind = page.get("kind") or page.get("type") or "page"
    updated = str(page.get("updated") or "")[:10]
    when = f", updated {updated}" if updated else ""
    title = page.get("title") or "page"
    change = page.get("change") or ""
    status = page.get("status") or ""
    if change:
        bits = [p for p in (kind, change, status) if p]
        if page.get("high"):
            bits.insert(2, "High")
        head = f"  [{tag}] ({', '.join(bits)}) {title}"
    else:
        head = f"  [{tag}] (Confluence {kind}{when}) {title}"
    lines = [head]
    if page.get("summary"):
        lines.append(f"      Summary: {page['summary']}")
    excerpt = page.get("body_text") or page.get("detail") or ""
    excerpt = re.sub(r"\s+", " ", str(excerpt)).strip()
    if excerpt and not page.get("title_only") and budget > 0:
        if len(excerpt) <= budget:
            lines.append(f"      {excerpt}")
            budget -= len(excerpt)
        # A page that does not fit keeps the title and summary only.
    return lines, budget


def _pick_children(epic, max_per_epic):
    """Moved, new, commented, blocked, in progress, then the rest."""
    from core import blocked
    items = [it for it in epic.get("items") or [] if it.get("source", "Jira") == "Jira"]
    moved = {it.get("key") for it in epic.get("moved") or []}
    new = {it.get("key") for it in epic.get("new") or []}
    ranked = []

    def take(pred):
        for item in items:
            key = item.get("key")
            if key in {it.get("key") for it in ranked}:
                continue
            if pred(item, key):
                ranked.append(item)

    take(lambda _item, key: key in moved)
    take(lambda _item, key: key in new)
    take(lambda item, _key: bool(item.get("comments")))
    take(lambda item, _key: blocked.is_blocked(item))
    take(lambda item, _key: (item.get("status_category") or "") == "indeterminate")
    take(lambda _item, _key: True)
    shown = ranked[:max_per_epic]
    return shown, len(ranked) - len(shown)


def build_grouped_material(epics, loose_pages, comment_budget=6000,
                           page_budget=8000, max_items=40, max_per_epic=8,
                           register_entries=None):
    """Epic-grouped material. Comments and page excerpts share their budgets."""
    lines = []
    shown = 0
    used_comments = 0
    comment_limit = 0 if comment_budget is None else int(comment_budget)
    pages_left = int(page_budget or 0)
    omitted_comments = 0

    def comments_of(item):
        nonlocal used_comments, omitted_comments
        extra = []
        wrote = False
        for line in item.get("comments") or []:
            if used_comments + len(line) > comment_limit:
                break
            extra.append(f"      {line}")
            used_comments += len(line)
            wrote = True
        if (item.get("comments") or []) and not wrote:
            omitted_comments += 1
        return extra

    def room():
        return shown < int(max_items)

    for epic in epics or []:
        if not room():
            break
        if epic.get("key"):
            due = f" | due {epic['due']}" if epic.get("due") else ""
            done = epic.get("children_done") or 0
            total = epic.get("children_total") or 0
            signal = epic.get("signal") or ""
            lines.append(
                f"Epic {epic['key']}: {epic.get('summary') or ''} | "
                f"{epic.get('status') or '—'} | {done} of {total} done{due}"
                f"{(' | ' + signal) if signal else ''}"
            )
        else:
            lines.append("Not under an Epic")
        children, more = _pick_children(epic, max_per_epic)
        for item in children:
            if not room():
                break
            lines.extend(_item_line(item))
            lines.extend(comments_of(item))
            shown += 1
        if more and room():
            lines.append(f"  (+{more} more under this Epic)")
        pages = list(epic.get("pages") or [])
        if epic.get("key"):
            pages.extend(entry for entry in (register_entries or [])
                         if entry.get("epic") == epic["key"])
        seen_pages = set()
        for page in pages:
            marker = page.get("page_id") or page.get("ref") or id(page)
            if marker in seen_pages or not room():
                continue
            seen_pages.add(marker)
            block, pages_left = _page_line(page, pages_left)
            lines.extend(block)
            shown += 1

    documents = [page for page in (loose_pages or []) if page.get("source") != "Jira"]
    if documents and room():
        lines.append("Documents not tied to an Epic")
        for page in documents:
            if not room():
                break
            block, pages_left = _page_line(page, pages_left)
            lines.extend(block)
            shown += 1
    unmatched = [entry for entry in (register_entries or []) if not entry.get("epic")]
    if unmatched and room():
        lines.append("Register changes")
        for entry in unmatched:
            if not room():
                break
            block, pages_left = _page_line(entry, pages_left)
            lines.extend(block)
            shown += 1
    if omitted_comments:
        lines.append(
            f"(+{omitted_comments} commented issues omitted "
            f"to keep the prompt short.)")
    if not lines:
        return "(No items were found for this workstream.)"
    return "\n".join(lines)


def infer_report_section(model_cfg, audience, workstream, items, change_block,
                         comment_budget=6000, cfg=None, material=None,
                         epics=None, loose_pages=None, page_budget=8000,
                         register_entries=None):
    """Ask the local model to write the report section for one workstream.

    A list in `items` keeps the flat material the older callers send. Pass
    `material` (or `epics`) for the grouped block. Warm and the report must
    pass the same `material` string.
    """
    if material is None:
        if epics is not None:
            material = build_grouped_material(
                epics, loose_pages or [], comment_budget=comment_budget,
                page_budget=page_budget, register_entries=register_entries)
        else:
            material = build_material(items, comment_budget=comment_budget)
    user_content = (
        f"Workstream: {workstream['name']} ({workstream['abbrev']})\n\n"
        f"CHANGE SUMMARY:\n{change_block}\n\n"
        f"Material:\n{material}\n\n"
        f"{prompts.get(cfg, 'report.section_tail')}"
    )
    return call_model(model_cfg,
                      prompts.get(cfg, "report.section", audience=audience),
                      user_content)
