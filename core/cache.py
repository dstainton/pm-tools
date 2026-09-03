"""A local fetch cache so repeated commands (and `pm today`) stay fast.

Search results are stored as one JSON file per query under `cache.path`
(default `~/.pm/cache`). A query is reused when it is younger than
`cache.ttl_seconds` (default 300).

Run-time flags, set once on the Jira config by `attach`:

  default   use a hit if it is still fresh; otherwise fetch and store
  cached    use a hit even if it is stale (a plane / offline run)
  refresh   ignore hits; fetch and store

A cache miss in `cached` mode still fetches — we cannot invent results.
Nothing here is shared between machines; it is a speed and offline aid.
"""

import hashlib
import json
import os
import time


DEFAULT_PATH = "~/.pm/cache"
DEFAULT_TTL = 300


def settings(cfg):
    """Read the `cache:` block, with defaults filled in."""
    block = cfg.get("cache") if isinstance(cfg.get("cache"), dict) else {}
    enabled = block.get("enabled", True)
    path = os.path.expanduser(block.get("path") or DEFAULT_PATH)
    try:
        ttl = int(block.get("ttl_seconds", DEFAULT_TTL) or DEFAULT_TTL)
    except (TypeError, ValueError):
        ttl = DEFAULT_TTL
    return {"enabled": bool(enabled), "path": path, "ttl_seconds": max(0, ttl)}


def cache_key(kind, *parts):
    """Stable filename stem for one cached call."""
    blob = json.dumps([kind, *parts], sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class FetchCache:
    """File-backed cache for Jira search payloads."""

    def __init__(self, path, ttl_seconds, mode="default"):
        self.path = path
        self.ttl_seconds = ttl_seconds
        self.mode = mode if mode in ("default", "cached", "refresh") else "default"

    def _file(self, key):
        return os.path.join(self.path, f"{key}.json")

    def get(self, key):
        """Return the stored payload, or None when we should fetch."""
        if self.mode == "refresh":
            return None
        path = self._file(key)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                record = json.load(fh)
        except (ValueError, OSError):
            return None
        stored_at = record.get("stored_at") or 0
        age = time.time() - float(stored_at)
        if self.mode == "cached" or age <= self.ttl_seconds:
            return record.get("payload")
        return None

    def put(self, key, payload):
        os.makedirs(self.path, exist_ok=True)
        record = {"key": key, "stored_at": time.time(), "payload": payload}
        path = self._file(key)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(record, fh)
        os.replace(tmp, path)

    def entry_count(self):
        if not os.path.isdir(self.path):
            return 0
        return sum(1 for name in os.listdir(self.path) if name.endswith(".json"))

    def newest_age_seconds(self):
        """Age of the most recently written entry, or None if empty."""
        if not os.path.isdir(self.path):
            return None
        newest = None
        for name in os.listdir(self.path):
            if not name.endswith(".json"):
                continue
            stamp = os.path.getmtime(os.path.join(self.path, name))
            newest = stamp if newest is None else max(newest, stamp)
        if newest is None:
            return None
        return time.time() - newest


def attach(cfg, mode="default"):
    """Hang a FetchCache on the Jira config so `search_issues` can see it.

    `cfg` is the full loaded config. The cache object is stored on
    `cfg['jira']['_fetch_cache']`, which every fetch already receives.
    """
    opts = settings(cfg)
    if not opts["enabled"]:
        return None
    cache = FetchCache(opts["path"], opts["ttl_seconds"], mode=mode)
    jira = cfg.setdefault("jira", {})
    jira["_fetch_cache"] = cache
    cfg["_fetch_cache"] = cache
    return cache


def status_line(cfg):
    """One-line cache summary for `pm doctor`."""
    opts = settings(cfg)
    cache = cfg.get("_fetch_cache")
    if not opts["enabled"]:
        return opts["path"], 0, "disabled"
    count = cache.entry_count() if cache else 0
    if count == 0:
        return opts["path"], 0, "empty"
    age = cache.newest_age_seconds() if cache else None
    if age is None:
        return opts["path"], count, "empty"
    warm = age <= opts["ttl_seconds"]
    return opts["path"], count, "warm" if warm else "stale"
