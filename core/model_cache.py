"""File cache for model replies.

A key is a hash of the prompt, the user content, the model name, and the
sampling settings. An issue whose text did not change produces the same key,
so a second `pm inbox` or a re-run of `pm review` after a small edit only
pays for the batches that changed.

Lives under `cache.path/model`. `--cached` reuses a hit past the TTL.
`--refresh` ignores hits and stores the new reply. A failure string is never
stored: the next run should try again.
"""

import json
import os
import time

from core.cache import cache_key


DEFAULT_TTL = 604800


def _enabled(model_cfg):
    return bool(model_cfg.get("_model_cache_path")) and bool(
        model_cfg.get("_model_cache_enabled", True))


def _file(model_cfg, key):
    return os.path.join(model_cfg["_model_cache_path"], f"{key}.json")


def make_key(model_cfg, system_prompt, user_content, temperature):
    return cache_key(
        "model",
        model_cfg.get("name"),
        temperature,
        model_cfg.get("top_p"),
        model_cfg.get("top_k"),
        model_cfg.get("presence_penalty"),
        model_cfg.get("max_tokens"),
        bool(model_cfg.get("enable_thinking")),
        system_prompt,
        user_content,
    )


def lookup(model_cfg, system_prompt, user_content, temperature):
    """Return the stored reply, or None when the call should go to the model."""
    if not _enabled(model_cfg):
        return None
    if model_cfg.get("_cache_mode") == "refresh":
        return None
    path = _file(model_cfg, make_key(
        model_cfg, system_prompt, user_content, temperature))
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            record = json.load(fh)
    except (ValueError, OSError):
        return None
    text = record.get("text")
    if not isinstance(text, str) or not text or text.startswith("_"):
        return None
    age = time.time() - float(record.get("stored_at") or 0)
    ttl = model_cfg.get("_model_ttl", DEFAULT_TTL)
    if model_cfg.get("_cache_mode") == "cached" or age <= ttl:
        return text
    return None


def store(model_cfg, system_prompt, user_content, temperature, text):
    if not _enabled(model_cfg):
        return
    if not isinstance(text, str) or not text or text.startswith("_"):
        return
    folder = model_cfg["_model_cache_path"]
    os.makedirs(folder, exist_ok=True)
    key = make_key(model_cfg, system_prompt, user_content, temperature)
    path = _file(model_cfg, key)
    record = {"key": key, "stored_at": time.time(), "text": text}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(record, fh)
    os.replace(tmp, path)


def status_line(model_cfg):
    """`(path, count, state)` for `pm doctor`."""
    path = model_cfg.get("_model_cache_path") or ""
    if not model_cfg.get("_model_cache_enabled", True):
        return path, 0, "disabled"
    if not path or not os.path.isdir(path):
        return path, 0, "empty"
    count = sum(1 for name in os.listdir(path) if name.endswith(".json"))
    if count == 0:
        return path, 0, "empty"
    return path, count, "warm"
