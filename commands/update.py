"""`pm update` — upgrade the installed code, then the config.

The code upgrade depends on how pm-tools was installed. The config upgrade
never replaces `~/.pm-tools/config.yaml`. It walks migrations until
`config_version` matches the installed template, and it writes only when
that result still validates.

A pip or pipx install replaces the files on disk while this process still
has the old migrations loaded. After that install succeeds, this command
starts `pm update --config-only` so the new code applies the new steps.

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
import shutil
import subprocess
import sys

import yaml

from core import config as config_core
from core.migrations import (MigrationError, apply_migrations,
                             bundled_template_path, read_version,
                             template_version)
from core.paths import config_file


SECRET_KEYS = ("api_token", "client_secret", "webhook")
GIT_SPEC = "git+https://github.com/dstainton/pm-tools.git"
_SECRET_RE = re.compile(
    r"^(\s*(?:" + "|".join(SECRET_KEYS) + r"):\s*)(.*)$", re.M)


def user_config_path(explicit=None):
    """The config `pm update` may edit. Never the bundled template."""
    if explicit:
        path = explicit
    elif os.environ.get("PM_CONFIG"):
        path = os.environ["PM_CONFIG"]
    else:
        path = config_file()
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.exists(path):
        sys.exit(f"No config at {path}.\n"
                 "Create one with:  pm init")
    template = os.path.abspath(bundled_template_path())
    package_root = os.path.dirname(template)
    if os.path.abspath(path) == template or _is_inside(path, package_root):
        sys.exit(f"Refusing to edit {path}.\n"
                 "That file is part of the pm-tools install. "
                 f"Your config lives at {config_file()}.")
    return path


def _is_inside(path, folder):
    path = os.path.abspath(path)
    folder = os.path.abspath(folder)
    return path == folder or path.startswith(folder + os.sep)


def git_spec(url):
    """A pip spec that reinstalls the latest commit, not a cached wheel.

    `direct_url.json` stores `https://...git`. pipx and pip want `git+https`.
    A commit pin is not included: `pm update` should fetch the branch tip.
    """
    if not url:
        return GIT_SPEC
    cleaned = url.split("#", 1)[0].strip()
    if cleaned.startswith("git+"):
        return cleaned
    if cleaned.startswith(("https://", "http://", "ssh://")):
        return "git+" + cleaned
    return GIT_SPEC


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
        # `pipx upgrade` runs `pip install --upgrade`. When the version in
        # pyproject.toml does not change, pip leaves the old files in place
        # and reports the package unchanged. `--force` reinstalls the git tip.
        return {
            "kind": "pipx",
            "detail": "Installed with pipx.",
            "command": ["pipx", "install", "--force", git_spec(url)],
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
            "command": [sys.executable, "-m", "pip", "install",
                        "--force-reinstall", git_spec(url)],
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
    """Run the code upgrade.

    Returns `stop` when the caller must exit, `current` when this process
    already has the migrations to apply, `preview` when a dry run would
    install and then migrate, and `replaced` when a new install is on disk
    and the config step must start a new process.
    """
    info = classify_install()
    print(info["detail"])
    command = info["command"]
    if info["kind"] == "unknown":
        print("Fix the install, then run pm update again. "
              "The config was not changed.")
        return "stop"
    if command is None:
        return "current"
    shown = " ".join(command)
    if dry_run:
        print(f"Would run: {shown}")
        print("Would then run: pm update --config-only")
        print("That second step uses the migrations the install just wrote.")
        return "preview"
    print(f"Running: {shown}")
    try:
        completed = subprocess.run(command, check=False)
    except OSError as err:
        print(f"Code upgrade failed: {err}")
        print("The config was not changed.")
        return "stop"
    if completed.returncode != 0:
        print(f"Code upgrade failed (exit {completed.returncode}).")
        print("The config was not changed.")
        return "stop"
    return "replaced"


def config_only_command(args):
    """How to start the config step once the new code is on disk."""
    program = sys.argv[0] or "pm"
    if not os.path.isabs(program):
        program = shutil.which(program) or program
    command = [program, "update", "--config-only"]
    config = getattr(args, "config", None)
    if config:
        command.extend(["--config", config])
    return command


def continue_with_new_code(args):
    """Migrate with the code that just got installed, not this process."""
    command = config_only_command(args)
    print("Applying the config upgrade with the newly installed code.")
    print("Running: " + " ".join(command))
    try:
        completed = subprocess.run(command, check=False)
    except OSError as err:
        sys.exit("The program was upgraded, but the config step could not "
                 f"start: {err}\nRun:  pm update --config-only")
    sys.exit(completed.returncode)


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
        outcome = upgrade_code(dry_run=dry_run)
        if outcome == "stop":
            sys.exit(1)
        if code_only or outcome == "preview":
            return
        if outcome == "replaced":
            continue_with_new_code(args)
    if code_only:
        return

    path = user_config_path(getattr(args, "config", None))
    upgrade_config(path, dry_run=dry_run)
