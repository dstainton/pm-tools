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
import re

import requests


# ---------------------------------------------------------------------------
#  Prompts — short, numbered, format last. Written for Qwen3.8 Q3_K_M.
# ---------------------------------------------------------------------------

# Seven headings, in this order. The model fills them in; we never ask it to
# invent a structure.
REPORT_HEADINGS = (
    "What changed since last week",
    "Progress this sprint",
    "Roadmap status",
    "Decisions since last report",
    "Open dependencies",
    "Decisions we are waiting on",
    "Risks",
)

EMPTY_SECTION = "No update this week."
FIRST_RUN_LINE = "First report — no prior week to compare against."

REPORT_SYSTEM_PROMPT = """\
Write a weekly status note for {audience}.

Use ONLY the CHANGE SUMMARY and the Material. Do not invent people, dates, \
status, or work.

Output exactly these seven headings, in this order, and nothing else:
### What changed since last week
### Progress this sprint
### Roadmap status
### Decisions since last report
### Open dependencies
### Decisions we are waiting on
### Risks

Rules:
1. Each section is 2 to 4 short bullets, or this exact sentence: \
No update this week.
2. If CHANGE SUMMARY says this is the first run, the first section is \
exactly: First report — no prior week to compare against.
3. After a fact, cite its tag like [SDX-J3]. Use only tags that appear in \
the Material.
4. Do not add a title, a workstream heading, or a reference list.

Example of one filled section:
### Progress this sprint
- Status endpoint is in review. [SDX-J1]
- Certificate rotation is past its due date. [SDX-J4]
"""

REPORT_USER_TAIL = "Write the seven sections now."


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

def call_model(model_cfg, system_prompt, user_content, temperature=None):
    """Send one system+user turn and return the visible assistant text.

    Returns a readable error string (never raises) so a single failed call
    does not sink a whole run.
    """
    payload = build_payload(model_cfg, system_prompt, user_content, temperature)
    try:
        resp = requests.post(model_cfg["endpoint"], json=payload,
                             timeout=model_cfg["timeout"])
        resp.raise_for_status()
        text = message_text(resp.json())
        return text or "_The model returned an empty reply._"
    except requests.RequestException as err:
        return (f"_Could not reach the model endpoint ({err}). "
                f"Is the local OpenAI-compatible server running?_")


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

def build_material(items, max_items=40, detail_limit=180):
    """Turn gathered items into a compact, taggable block for the model.

    Q3_K_M loses the plot when the prompt is a wall of text, so we cap both
    how many items go in and how long each detail line is.
    """
    if not items:
        return "(No items were found for this workstream.)"
    lines = []
    shown = items[:max_items]
    for it in shown:
        block = f"[{it['ref']}] ({it['source']}) {it['title']}"
        if it.get("detail"):
            block += f"\n    {short_detail(it['detail'], detail_limit)}"
        lines.append(block)
    omitted = len(items) - len(shown)
    if omitted:
        lines.append(f"(+{omitted} more items omitted to keep the prompt short.)")
    return "\n".join(lines)


def short_detail(text, limit):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def infer_report_section(model_cfg, audience, workstream, items, change_block):
    """Ask the local model to write the report section for one workstream."""
    material = build_material(items)
    user_content = (
        f"Workstream: {workstream['name']} ({workstream['abbrev']})\n\n"
        f"CHANGE SUMMARY:\n{change_block}\n\n"
        f"Material:\n{material}\n\n"
        f"{REPORT_USER_TAIL}"
    )
    return call_model(model_cfg,
                      REPORT_SYSTEM_PROMPT.format(audience=audience),
                      user_content)
