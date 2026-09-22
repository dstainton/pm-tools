"""Config version and the migrations `pm update` walks.

Version 1 is the shape `pm init` copies. Nothing migrates into that shape:
nobody has an older installed config. Later releases append to MIGRATIONS.
A migration inserts missing keys and bumps `config_version`. It does not
replace values that are already set.
"""

import os
import re

from core import config_edit


# (from_version, function). Empty at the first install.
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
