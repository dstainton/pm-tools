"""`pm update` — upgrade the installed code, then the config.

The code upgrade depends on how pm-tools was installed. The config upgrade
never replaces `~/.pm/config.yaml`. It walks migrations until
`config_version` matches the installed template, and it writes only when
that result still validates.

  pm update
  pm update --code-only
  pm update --config-only
  pm update --dry-run

This command does not load config first. A file that is one version behind
may not pass validation until the migration has run.
"""

import difflib
import os
import re
import subprocess
import sys

import yaml

from core import config as config_core
from core.migrations import (MigrationError, apply_migrations,
                             bundled_template_path, read_version,
                             template_version)


SECRET_KEYS = ("api_token", "client_secret", "webhook")
_SECRET_RE = re.compile(
    r"^(\s*(?:" + "|".join(SECRET_KEYS) + r"):\s*)(.*)$", re.M)


def user_config_path(explicit=None):
    """The config `pm update` may edit. Never the bundled template."""
    if explicit:
        path = explicit
    elif os.environ.get("PM_CONFIG"):
        path = os.environ["PM_CONFIG"]
    else:
        path = "~/.pm/config.yaml"
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.exists(path):
        sys.exit(f"No config at {path}.\n"
                 "Create one with:  pm init")
    template = os.path.abspath(bundled_template_path())
    package_root = os.path.dirname(template)
    if os.path.abspath(path) == template or _is_inside(path, package_root):
        sys.exit(f"Refusing to edit {path}.\n"
                 "That file is part of the pm-tools install. "
                 "Your config lives at ~/.pm/config.yaml.")
    return path


def _is_inside(path, folder):
    path = os.path.abspath(path)
    folder = os.path.abspath(folder)
    return path == folder or path.startswith(folder + os.sep)


def classify_install():
    """How this process was installed, and the command that upgrades it.

    Returns a dict: kind, detail, command (list or None). `command` is what
    to run. Editable checkouts have no command; the user pulls git.
    """
    try:
        from importlib.metadata import distribution
        dist = distribution("pm-tools")
    except Exception:                              # noqa: BLE001
        dist = None

    if dist is None:
        root = os.path.dirname(os.path.abspath(bundled_template_path()))
        return {
            "kind": "source",
            "detail": f"Running from {root}. Update the code with git pull "
                      f"in that directory.",
            "command": None,
        }

    location = str(dist.locate_file(""))
    direct = _direct_url(dist)
    editable = bool((direct.get("dir_info") or {}).get("editable"))
    url = direct.get("url") or ""
    prefix = sys.prefix.replace("\\", "/")
    pipx = "/pipx/" in prefix.lower() or "pipx" in prefix.lower()

    if pipx and not editable:
        return {
            "kind": "pipx",
            "detail": "Installed with pipx.",
            "command": ["pipx", "upgrade", "pm-tools"],
        }
    if editable:
        root = location
        return {
            "kind": "editable",
            "detail": f"Editable install at {root}. Update the code with "
                      f"git pull in that directory.",
            "command": None,
        }
    if url.startswith("https://github.com/dstainton/pm-tools"):
        return {
            "kind": "pip-git",
            "detail": f"Installed from {url}.",
            "command": [sys.executable, "-m", "pip", "install", "--upgrade", url],
        }
    return {
        "kind": "unknown",
        "detail": "Could not tell how pm-tools was installed, so no upgrade "
                  "command was run.",
        "command": None,
    }


def _direct_url(dist):
    import json
    try:
        raw = dist.read_text("direct_url.json")
    except (OSError, TypeError, FileNotFoundError):
        return {}
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def upgrade_code(dry_run=False):
    """Run the code upgrade. Return False when the caller must stop."""
    info = classify_install()
    print(info["detail"])
    command = info["command"]
    if info["kind"] == "unknown":
        print("Fix the install, then run pm update again. "
              "The config was not changed.")
        return False
    if command is None:
        return True
    shown = " ".join(command)
    if dry_run:
        print(f"Would run: {shown}")
        return True
    print(f"Running: {shown}")
    try:
        completed = subprocess.run(command, check=False)
    except OSError as err:
        print(f"Code upgrade failed: {err}")
        print("The config was not changed.")
        return False
    if completed.returncode != 0:
        print(f"Code upgrade failed (exit {completed.returncode}).")
        print("The config was not changed.")
        return False
    return True


def redact(text):
    """Hide secret values in a preview."""
    return _SECRET_RE.sub(r"\1<redacted>", text)


def upgrade_config(path, dry_run=False, migrations=None, target=None):
    """Migrate `path` up to `target`. Return True when the file changes."""
    from core.migrations import MIGRATIONS
    if migrations is None:
        migrations = MIGRATIONS
    if target is None:
        target = template_version()
    with open(path, "r", encoding="utf-8") as fh:
        original = fh.read()
    version = read_version(original)
    if version >= target:
        print(f"Config is current (config_version {version}).")
        return False
    try:
        updated = apply_migrations(original, migrations, target)
    except MigrationError as err:
        sys.exit(f"Could not upgrade {path}: {err}\n"
                 "The file was not changed.")
    if dry_run:
        print(f"Would upgrade {path} from config_version {version} "
              f"to {target}:")
        diff = difflib.unified_diff(
            redact(original).splitlines(), redact(updated).splitlines(),
            fromfile=path, tofile=path, lineterm="")
        print("\n".join(diff) or "(no textual change)")
        return False
    if not _valid(updated):
        return False
    _atomic_write(path, updated)
    print(f"Upgraded {path} to config_version {target}.")
    return True


def _valid(text):
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as err:
        sys.exit(f"Refusing to write: the upgrade is not valid YAML ({err}).\n"
                 "The file was not changed.")
    if not isinstance(data, dict):
        sys.exit("Refusing to write: the upgrade is not a config mapping.\n"
                 "The file was not changed.")
    try:
        config_core.validate(data)
    except SystemExit as err:
        message = err.code if isinstance(err.code, str) else err
        sys.exit(f"Refusing to write: {message}\nThe file was not changed.")
    return True


def _atomic_write(path, text):
    folder = os.path.dirname(path) or "."
    tmp = os.path.join(folder, f".{os.path.basename(path)}.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def run(args):
    code_only = getattr(args, "code_only", False)
    config_only = getattr(args, "config_only", False)
    dry_run = getattr(args, "dry_run", False)
    if code_only and config_only:
        sys.exit("Choose one of --code-only or --config-only.")

    if not config_only:
        if not upgrade_code(dry_run=dry_run):
            sys.exit(1)
    if code_only:
        return

    path = user_config_path(getattr(args, "config", None))
    upgrade_config(path, dry_run=dry_run)
