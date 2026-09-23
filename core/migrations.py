"""Config version and the migrations `pm update` walks.

Version 1 is the shape `pm init` copies. Nothing migrates into that shape:
nobody has an older installed config. Later releases append to MIGRATIONS.
A migration inserts missing keys and bumps `config_version`. It does not
replace values that are already set.
"""

import os
import re

from core import config_edit


# (from_version, function). Version 1 is the first install. Each later
# release that adds a key appends one step.
MIGRATIONS = []

_VERSION_RE = re.compile(r"^config_version:\s*(\d+)\s*(?:#.*)?$")
_KEY_RE = re.compile(r"^([A-Za-z_][\w-]*):")


class MigrationError(Exception):
    """A migration could not move the file to the next version."""


def bundled_template_path():
    """The config.yaml shipped with this install.

    A checkout keeps the template next to pm.py. A pip/pipx install puts it
    in `<prefix>/share/pm-tools/config.yaml`.
    """
    here = os.path.dirname(os.path.abspath(__file__))          # .../core
    root = os.path.dirname(here)
    candidates = [
        os.path.join(root, "config.yaml"),
        os.path.join(sys_prefix_share(), "config.yaml"),
        os.path.join(here, "config.yaml"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[0]


def sys_prefix_share():
    import sys
    return os.path.join(sys.prefix, "share", "pm-tools")


def read_version(text):
    """Top-level `config_version`, or 0 when the key is absent."""
    for line in text.splitlines():
        match = _VERSION_RE.match(line)
        if match:
            return int(match.group(1))
    return 0


def template_version(path=None):
    path = path or bundled_template_path()
    with open(path, "r", encoding="utf-8") as fh:
        return read_version(fh.read())


def set_version(text, version):
    """Write `config_version`, inserting it when the file has none."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if _VERSION_RE.match(line):
            lines[index] = f"config_version: {version}"
            return _with_newline(lines, text)
    lines.insert(0, f"config_version: {version}")
    return _with_newline(lines, text)


def _with_newline(lines, original):
    body = "\n".join(lines)
    if original.endswith("\n") or not original:
        return body + "\n"
    return body + "\n"


def has_top_level(text, key):
    for line in text.splitlines():
        match = _KEY_RE.match(line)
        if match and match.group(1) == key:
            return True
    return False


def insert_missing_block(text, key, body_lines, before_key=None):
    """Insert a top-level block when `key` is absent. Leave it when present."""
    if has_top_level(text, key):
        return text
    lines = text.splitlines()
    insert_at = len(lines)
    if before_key:
        before, _end = config_edit.find_block(lines, before_key)
        if before is None:
            for index, line in enumerate(lines):
                match = _KEY_RE.match(line)
                if match and match.group(1) == before_key:
                    before = index
                    break
        if before is not None:
            insert_at = before
    block = ["", f"{key}:"] + list(body_lines)
    return _with_newline(lines[:insert_at] + block + lines[insert_at:], text)


def _block_has_key(text, block, key):
    lines = text.splitlines()
    start, end = config_edit.find_block(lines, block)
    if start is None:
        return False
    pattern = re.compile(rf"^\s+{re.escape(key)}\s*:")
    return any(pattern.match(line) for line in lines[start + 1:end])


def _insert_under(text, block, line):
    """Insert `line` as the first child of a top-level block."""
    lines = text.splitlines()
    start, _end = config_edit.find_block(lines, block)
    if start is None:
        return text
    lines.insert(start + 1, line)
    return _with_newline(lines, text)


def to_version_2(text):
    """Add `ready.max_points` when it is missing. Leave everything else.

    Product Goal and Definition of Done stay absent until someone sets
    them. An existing `max_points` is not replaced.
    """
    if not has_top_level(text, "ready"):
        text = insert_missing_block(
            text, "ready", ["  max_points: 8"], before_key="daily")
    elif not _block_has_key(text, "ready", "max_points"):
        text = _insert_under(text, "ready", "  max_points: 8")
    return set_version(text, 2)


MIGRATIONS.append((1, to_version_2))


def to_version_3(text):
    """Add blocked names and the model run budget. Leave set values alone.

    `blocked` is how the team spells "blocked". `model.total_timeout` caps
    a whole command, on top of the per-call `timeout`. The model-result
    cache TTL is filled in memory when the key is absent; it is written
    here too so the file shows the knob.
    """
    if not has_top_level(text, "blocked"):
        text = insert_missing_block(
            text, "blocked",
            ["  statuses: [Blocked]", "  labels: [blocked]"],
            before_key="today")
    if not has_top_level(text, "model"):
        text = insert_missing_block(
            text, "model", ["  total_timeout: 3600"], before_key="jira")
    elif not _block_has_key(text, "model", "total_timeout"):
        text = _insert_under(text, "model", "  total_timeout: 3600")
    if has_top_level(text, "cache") and not _block_has_key(
            text, "cache", "model_ttl_seconds"):
        text = _insert_under(text, "cache", "  model_ttl_seconds: 604800")
    return set_version(text, 3)


MIGRATIONS.append((2, to_version_3))


_COMMENT_LINES = (
    ("enabled", "  enabled: true"),
    ("max_per_issue", "  max_per_issue: 3"),
    ("max_issues", "  max_issues: 25"),
    ("excerpt_chars", "  excerpt_chars: 240"),
    ("report_days", "  report_days: 7"),
    ("section_chars", "  section_chars: 6000"),
)


def to_version_4(text):
    """Add the comments block. Leave a value that is already set.

    Narrative commands read Jira comments inside their own window. The
    block holds the caps. A switched-off `enabled` stays off.
    """
    if not has_top_level(text, "comments"):
        text = insert_missing_block(
            text, "comments", [line for _key, line in _COMMENT_LINES],
            before_key="confluence")
    else:
        for key, line in reversed(_COMMENT_LINES):
            if not _block_has_key(text, "comments", key):
                text = _insert_under(text, "comments", line)
    return set_version(text, 4)


MIGRATIONS.append((3, to_version_4))


def apply_migrations(text, migrations, target):
    """Walk `migrations` until `text` is at `target`.

    `migrations` is a list of `(from_version, function)`. Each function
    returns the new text and must leave `config_version` one higher.
    """
    version = read_version(text)
    if version >= target:
        return text
    by_source = {src: fn for src, fn in migrations}
    while version < target:
        fn = by_source.get(version)
        if fn is None:
            raise MigrationError(
                f"config_version {version} cannot reach {target}. "
                f"No migration is defined for this step.")
        text = fn(text)
        new_version = read_version(text)
        if new_version != version + 1:
            raise MigrationError(
                f"Migration from {version} left config_version at "
                f"{new_version}; expected {version + 1}.")
        version = new_version
    return text
