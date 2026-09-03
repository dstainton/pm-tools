"""Where local and shared state files live.

Personal files (cache, write log, today's numbered list) stay in `~/.pm`.
Decisions and the inbox follow `state.shared_path` when that is set, so the
PM and the BA see the same queues on a synced folder. An empty or missing
path keeps those files in `~/.pm` too.
"""

import os


def local_dir(cfg=None):
    block = (cfg or {}).get("state") if isinstance((cfg or {}).get("state"), dict) else {}
    override = (block or {}).get("local_path")
    return os.path.expanduser(override or "~/.pm")


def shared_dir(cfg):
    block = cfg.get("state") if isinstance(cfg.get("state"), dict) else {}
    path = (block or {}).get("shared_path") or ""
    path = str(path).strip()
    if not path:
        return local_dir(cfg)
    return os.path.expanduser(path)


def _join(folder, name):
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, name)


def decisions_path(cfg):
    return _join(shared_dir(cfg), "decisions.json")


def inbox_path(cfg):
    return _join(shared_dir(cfg), "inbox.json")


def write_log_path(cfg):
    return _join(local_dir(cfg), "write-log.jsonl")


def today_path(cfg):
    block = cfg.get("today") if isinstance(cfg.get("today"), dict) else {}
    explicit = (block or {}).get("state_file")
    if explicit:
        return os.path.expanduser(explicit)
    return os.path.join(local_dir(cfg), "today.json")
