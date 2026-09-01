"""The local-model call, shared by any command that needs inference.

Talks to an OpenAI-compatible local endpoint (for example llama.cpp). No data
leaves your machine beyond your own local server.
"""

import json
import re

import requests


REPORT_SYSTEM_PROMPT = """You are a product manager preparing a weekly \
state-of-product snapshot for {audience}. Write clearly for a busy reader: \
short paragraphs and tight bullets, plain language, no filler.

For the workstream provided, produce these sections as Markdown:
### What changed since last week
### Progress this sprint
### Roadmap status
### Decisions since last report
### Open dependencies
### Decisions we are waiting on
### Risks

Rules you must follow:
- Use ONLY the material given below. Do not invent status, dates, or names.
- For "What changed since last week", summarise the CHANGE SUMMARY block in two \
or three tight bullets — lead with what is new or has moved. If it says this is \
the first run, write exactly: "First report — no prior week to compare against."
- When a fact comes from a source item, cite its tag in square brackets right \
after the sentence, e.g. [SDX-J3]. Only use tags that appear in the material.
- If a section has no supporting material, write exactly: "No update this week."
- Do not write a reference list; that is added automatically afterwards.
- Do not repeat the workstream name as a heading; start at "### What changed \
since last week"."""


def call_model(model_cfg, system_prompt, user_content):
    """Send one system+user turn to the local model and return the text.

    Returns a readable error string (never raises) so a single failed call
    doesn't sink a whole run.
    """
    payload = {
        "model": model_cfg["name"],
        "temperature": model_cfg["temperature"],
        "max_tokens": model_cfg["max_tokens"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }
    try:
        resp = requests.post(model_cfg["endpoint"], json=payload,
                             timeout=model_cfg["timeout"])
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except requests.RequestException as err:
        return (f"_Could not reach the model endpoint ({err}). "
                f"Is the local OpenAI-compatible server running?_")


def call_model_json(model_cfg, system_prompt, user_content):
    """Like call_model, but expects a JSON array back and parses it robustly.

    Local models sometimes wrap JSON in prose or ```json fences. We pull out the
    first well-formed JSON array we can find. Returns (data, error):
      * on success: (list, None)
      * on failure: (None, "reason string")   -- never raises
    """
    raw = call_model(model_cfg, system_prompt, user_content)
    if raw.startswith("_Could not reach"):
        return None, raw

    # Strip code fences if present.
    text = re.sub(r"^```(?:json)?|```$", "", raw.strip(),
                  flags=re.MULTILINE).strip()

    # First try the whole thing; then fall back to the first [...] block.
    for candidate in (text, _first_json_array(text)):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
            if isinstance(data, list):
                return data, None
        except (ValueError, TypeError):
            continue
    return None, f"Model did not return valid JSON. Raw start: {raw[:120]}..."


def _first_json_array(text):
    """Return the substring from the first '[' to its matching ']', or ''."""
    start = text.find("[")
    if start == -1:
        return ""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return ""


def build_material(items):
    """Turn gathered items into a compact, taggable block for the model."""
    if not items:
        return "(No items were found for this workstream.)"
    lines = []
    for it in items:
        block = f"[{it['ref']}] ({it['source']}) {it['title']}"
        if it["detail"]:
            block += f"\n    {it['detail']}"
        lines.append(block)
    return "\n".join(lines)


def infer_report_section(model_cfg, audience, workstream, items, change_block):
    """Ask the local model to write the report section for one workstream."""
    material = build_material(items)
    user_content = (
        f"Workstream: {workstream['name']} ({workstream['abbrev']})\n\n"
        f"CHANGE SUMMARY (since last week):\n{change_block}\n\n"
        f"Material:\n{material}"
    )
    return call_model(model_cfg,
                      REPORT_SYSTEM_PROMPT.format(audience=audience),
                      user_content)
