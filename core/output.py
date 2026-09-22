"""Where command output files are written.

Relative report, lint, ready, daily, refine, metrics and brief files land
in `output.directory` (default `~/.pm/out`). An absolute path is used as
given. `--out DIR` overrides the directory for one run.
"""

import os


DEFAULT_DIRECTORY = "~/.pm/out"


def directory(cfg, override=None):
    """The folder for this run, created if it does not exist."""
    if override:
        path = os.path.expanduser(override)
    else:
        block = cfg.get("output") if isinstance(cfg.get("output"), dict) else {}
        path = os.path.expanduser((block or {}).get("directory") or DEFAULT_DIRECTORY)
    os.makedirs(path, exist_ok=True)
    return path


def place(cfg, name, override=None):
    """Resolve one output file name against the output directory."""
    name = os.path.expanduser(name)
    if os.path.isabs(name):
        folder = os.path.dirname(name)
        if folder:
            os.makedirs(folder, exist_ok=True)
        return name
    folder = directory(cfg, override)
    if os.path.normpath(folder) == ".":
        return name
    return os.path.join(folder, name)
