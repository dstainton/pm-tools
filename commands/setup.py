"""`pm setup` — fill in the config one step at a time.

Writes the local file only. Jira and Confluence are read to check an
answer, never to change them. A value that is already set is left alone.
When stdin is not a terminal, this names the flags and stops.
"""

import os
import sys
import webbrowser

from commands import init as init_cmd
from core import config_edit
from core import migrations
from core import sources
from core.paths import config_file


TOKEN_PAGE = "https://id.atlassian.com/manage-profile/security/api-tokens"


def _tty():
    try:
        return bool(sys.stdin.isatty())
    except (AttributeError, ValueError):
        return False


def _ask(prompt):
    print(prompt, end="", flush=True)
    return input("").strip()


def _dest(args):
    path = getattr(args, "path", None) or os.path.expanduser(config_file())
    return os.path.expanduser(path)


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _set_jira(text, key, value):
    return config_edit.set_jira_field_if_blank(text, key, value)


def _flags_help():
    return (
        "stdin is not a terminal, so `pm setup` will not prompt.\n"
        "  pm setup --site dpdd --email you@example.com "
        "--token-env JIRA_TOKEN --project APS --yes\n"
        "One section later:  pm setup --section jira|model|workstreams|confluence"
    )


def _jira_cfg(text_path):
    """Best-effort jira block for a live check. Missing values stay blank."""
    import yaml
    with open(text_path, "r", encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh) or {}
    jira = loaded.get("jira") if isinstance(loaded.get("jira"), dict) else {}
    token = str(jira.get("api_token") or "")
    if token.startswith("${ENV:") and token.endswith("}"):
        token = os.environ.get(token[6:-1], "")
    return {
        "base_url": jira.get("base_url") or "",
        "email": jira.get("email") or "",
        "api_token": token,
        "project": jira.get("project") or "",
    }


def apply_known(text, args):
    """Write only the flags that were passed, and only into blank fields."""
    notes = []
    site = getattr(args, "site", None)
    if site:
        url = site if site.startswith("http") else f"https://{site}.atlassian.net"
        text, status = _set_jira(text, "base_url", url)
        notes.append(f"jira.base_url {status}")
    email = getattr(args, "email", None)
    if email:
        text, status = _set_jira(text, "email", email)
        notes.append(f"jira.email {status}")
    env_name = getattr(args, "token_env", None)
    token = getattr(args, "token", None)
    if env_name:
        text, status = _set_jira(text, "api_token", "${{ENV:{0}}}".format(env_name))
        notes.append(f"jira.api_token {status} (env {env_name})")
    elif token:
        text, status = _set_jira(text, "api_token", token)
        notes.append(f"jira.api_token {status}")
    project = getattr(args, "project", None)
    if project:
        text, status = _set_jira(text, "project", project)
        notes.append(f"jira.project {status}")
    endpoint = getattr(args, "model_endpoint", None)
    name = getattr(args, "model_name", None)
    if endpoint or name:
        if not migrations.has_top_level(text, "model"):
            text = migrations.insert_missing_block(
                text, "model", ["  endpoint: \"\"", "  name: \"\""],
                before_key="jira")
        if endpoint and not migrations._block_has_key(text, "model", "endpoint"):
            text = migrations._insert_under(text, "model", f'  endpoint: "{endpoint}"')
            notes.append("model.endpoint written")
        elif endpoint:
            notes.append("model.endpoint kept")
        if name and not migrations._block_has_key(text, "model", "name"):
            text = migrations._insert_under(text, "model", f'  name: "{name}"')
            notes.append("model.name written")
        elif name:
            notes.append("model.name kept")
    return text, notes


def run(args):
    section = getattr(args, "section", None)
    interactive = _tty() and not getattr(args, "yes", False)
    if not interactive and not any([
            getattr(args, "site", None), getattr(args, "email", None),
            getattr(args, "token_env", None), getattr(args, "token", None),
            getattr(args, "project", None), getattr(args, "model_endpoint", None),
            getattr(args, "model_name", None), section]):
        sys.exit(_flags_help())

    dest = _dest(args)
    if not os.path.exists(dest):
        init_cmd.run(type("A", (), {"path": dest, "force": False})())
    if not os.path.exists(dest):
        sys.exit(f"No config at {dest}.")

    text = _read(dest)
    if interactive and getattr(args, "open_browser", True):
        print(f"Opening the API token page:\n  {TOKEN_PAGE}")
        try:
            webbrowser.open(TOKEN_PAGE)
        except OSError as exc:
            print(f"Could not open a browser ({exc}). Open that page yourself.")
        if not getattr(args, "token_env", None):
            env_name = _ask("Env var for the token (blank to paste it): ")
            if env_name:
                args.token_env = env_name
            else:
                args.token = _ask("API token: ")
        if not getattr(args, "site", None):
            args.site = _ask("Jira site name (for example dpdd): ")
        if not getattr(args, "email", None):
            args.email = _ask("Atlassian email: ")

    text, notes = apply_known(text, args)
    _write(dest, text)
    print(f"Updated {dest}")
    for note in notes:
        print(f"  {note}")

    if getattr(args, "project", None) or (interactive and section in (None, "jira", "workstreams")):
        try:
            jira = _jira_cfg(dest)
            if jira["base_url"] and jira["api_token"]:
                me = sources.fetch_myself(jira)
                print(f"  Jira says hello, {me.get('displayName') or 'there'}.")
                if not jira["project"]:
                    projects = sources.fetch_projects(jira)
                    shown = ", ".join(p["key"] for p in projects[:12])
                    print(f"  Projects you can see: {shown}")
        except Exception as exc:                              # noqa: BLE001
            print(f"  Could not verify Jira yet: {exc}")

    if section == "model" or getattr(args, "model_endpoint", None):
        endpoint = getattr(args, "model_endpoint", None) or ""
        if endpoint:
            try:
                ids = sources.fetch_model_ids(endpoint)
                print("  Models: " + ", ".join(ids[:12]))
            except Exception as exc:                          # noqa: BLE001
                print(f"  Could not list models: {exc}")

    print("Next: pm doctor")
    if section:
        print(f"Section: {section}")
