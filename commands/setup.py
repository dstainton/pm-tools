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
from core import local_models
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
        "  pm setup --section model --model-endpoint http://127.0.0.1:11434/v1 "
        "--model-name qwen3:8b\n"
        "  pm setup --section confluence --confluence-space APS "
        "--confluence-root \"API Program Services\"\n"
        "One section later:  pm setup --section jira|model|workstreams|confluence\n"
        "A non-interactive run never installs Ollama or Lemonade."
    )


def _confluence_hint():
    return (
        "Confluence is optional. One shared space:\n"
        "  pm setup --section confluence --confluence-space APS "
        "--confluence-root \"API Program Services\"\n"
        "Then set confluence_page on a product or workstream, or pass\n"
        "  --confluence-page to pm products add / pm workstreams add.\n"
        "A space on its own still reads that whole space. Registers are\n"
        "edited in the config; the template has a commented example."
    )


def _real(value):
    text = str(value or "").strip()
    if not text:
        return False
    if text.startswith("<") and text.endswith(">"):
        return False
    return True


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
    key_env = getattr(args, "model_api_key_env", None)
    api_key = getattr(args, "model_api_key", None)
    if key_env:
        api_key = "${{ENV:{0}}}".format(key_env)
    if endpoint or name or api_key:
        if not migrations.has_top_level(text, "model"):
            text = migrations.insert_missing_block(
                text, "model", [], before_key="jira")
        if endpoint:
            text, status = config_edit.set_scalar(
                text, "model", "endpoint", local_models.chat_url(endpoint),
                replace=(local_models.SHIPPED_ENDPOINT,))
            notes.append(f"model.endpoint {status}")
        if name:
            text, status = config_edit.set_scalar(
                text, "model", "name", name,
                replace=(local_models.SHIPPED_NAME,))
            notes.append(f"model.name {status}")
        if api_key:
            text, status = config_edit.set_scalar(
                text, "model", "api_key", api_key)
            if key_env:
                notes.append(f"model.api_key {status} (env {key_env})")
            else:
                notes.append(f"model.api_key {status}")
    text, extra = apply_confluence_settings(text, args)
    notes.extend(extra)
    return text, notes


def _ask_confluence(text, args):
    """Ask for one shared space and folder titles. Blank answers skip."""
    import yaml
    loaded = yaml.safe_load(text) or {}
    block = loaded.get("confluence") if isinstance(loaded.get("confluence"), dict) else {}
    print("Confluence")
    print("  One shared space, or a space on each workstream.")
    print("  Leave a prompt blank to skip it. A value already set is left alone.")
    if not _real(block.get("space")) and not getattr(args, "confluence_space", None):
        space = _ask("Shared space key (blank to skip): ")
        if space:
            args.confluence_space = space
    if (getattr(args, "confluence_space", None) or _real(block.get("space"))) \
            and not _real(block.get("root_title")) \
            and not getattr(args, "confluence_root", None):
        root = _ask("Team page title (blank to skip): ")
        if root:
            args.confluence_root = root
    if not (getattr(args, "confluence_space", None) or _real(block.get("space"))):
        return
    pages = []
    for kind, rows in (("product", loaded.get("products") or []),
                       ("workstream", loaded.get("workstreams") or [])):
        for row in rows:
            if not isinstance(row, dict) or not row.get("abbrev"):
                continue
            if _real(row.get("confluence_page")) or _real(row.get("confluence_page_id")) \
                    or _real(row.get("confluence_space")):
                continue
            title = _ask(f"{kind} {row['abbrev']} folder title (blank to skip): ")
            if title:
                pages.append((kind, row["abbrev"], title))
    if pages:
        args.confluence_pages = pages


def apply_confluence_settings(text, args):
    """Write a shared space, the team page, and folder titles when blank."""
    notes = []
    space = getattr(args, "confluence_space", None)
    root = getattr(args, "confluence_root", None)
    pages = getattr(args, "confluence_pages", None) or []
    if not (space or root or pages):
        return text, notes
    import yaml
    loaded = yaml.safe_load(text) or {}
    jira = loaded.get("jira") if isinstance(loaded.get("jira"), dict) else {}
    site = getattr(args, "site", None)
    if site:
        wiki = site if str(site).startswith("http") else f"https://{site}.atlassian.net"
        wiki = wiki.rstrip("/")
        if not wiki.endswith("/wiki"):
            wiki += "/wiki"
    else:
        base = str(jira.get("base_url") or "").rstrip("/")
        wiki = (base + "/wiki") if _real(base) and not base.endswith("/wiki") else base
    email = getattr(args, "email", None) or (jira.get("email") if _real(jira.get("email")) else "")
    token = ""
    if getattr(args, "token_env", None):
        token = "${{ENV:{0}}}".format(args.token_env)
    elif getattr(args, "token", None):
        token = args.token
    elif _real(jira.get("api_token")):
        token = jira.get("api_token")
    placeholders = {
        "base_url": ("https://<YOUR_ORG>.atlassian.net/wiki",),
        "email": ("<YOUR_LOGIN_EMAIL>",),
        "api_token": ("<YOUR_CONFLUENCE_API_TOKEN>",),
    }
    for key, value in (("base_url", wiki), ("email", email), ("api_token", token)):
        if not value:
            continue
        text, status = config_edit.set_scalar(
            text, "confluence", key, value, replace=placeholders[key])
        notes.append(f"confluence.{key} {status}")
    if space:
        text, status = config_edit.set_scalar(text, "confluence", "space", space)
        notes.append(f"confluence.space {status}")
    if root:
        text, status = config_edit.set_scalar(text, "confluence", "root_title", root)
        notes.append(f"confluence.root_title {status}")
    for kind, abbrev, title in pages:
        list_key = "products" if kind == "product" else "workstreams"
        text, status = config_edit.set_entry_scalar(
            text, list_key, abbrev, "confluence_page", title)
        notes.append(f"{list_key} {abbrev} confluence_page {status}")
    return text, notes


def _catalog(text):
    import yaml
    loaded = yaml.safe_load(text) or {}
    if not isinstance(loaded, dict):
        loaded = {}
    catalog = local_models.settings(loaded)
    endpoints = []
    for item in catalog["endpoints"]:
        if not isinstance(item, dict) or not item.get("endpoint"):
            continue
        endpoints.append({
            "name": str(item.get("name") or item["endpoint"]),
            "endpoint": str(item["endpoint"]),
            "api_key": str(item.get("api_key") or ""),
        })
    return endpoints, catalog["recommendations"]


def _print_scan(found, endpoints, gib, recommendations):
    if gib is None:
        print("Memory: could not read system RAM.")
    else:
        print(f"Memory: {gib:.1f} GiB.")
    if not found:
        print("No local server answered. Checked:")
        for item in endpoints:
            print(f"  {item['name']}  {item['endpoint']}")
        return
    print("Local servers that answered:")
    for number, item in enumerate(found, 1):
        print(f"  {number}  {item['name']}  {item['endpoint']}")
        recommended, note = local_models.recommend(
            item["models"], recommendations, gib)
        if note:
            print(f"     {note}")
        if not item["models"]:
            print("     (no model ids)")
            continue
        for model_id in item["models"]:
            mark = " (recommended)" if model_id == recommended else ""
            print(f"     {model_id}{mark}")


def _choose_model(found, gib, recommendations, args):
    raw = _ask("Provider number (blank to skip): ")
    if not raw:
        return
    try:
        provider = found[int(raw) - 1]
    except (ValueError, IndexError):
        print("That number is not in the list.")
        return
    models = provider["models"]
    recommended, _note = local_models.recommend(models, recommendations, gib)
    if models:
        print(f"Models on {provider['name']}:")
        for number, model_id in enumerate(models, 1):
            mark = " (recommended)" if model_id == recommended else ""
            print(f"  {number}  {model_id}{mark}")
        picked = _ask("Model number (blank to skip): ")
        if not picked:
            return
        try:
            args.model_name = models[int(picked) - 1]
        except (ValueError, IndexError):
            print("That number is not in the list.")
            return
    args.model_endpoint = local_models.chat_url(provider["endpoint"])
    existing = provider.get("api_key") or ""
    hint = ""
    if existing:
        hint = " Press enter to use the key already on this provider."
    typed = _ask("API key (blank for none, or ${ENV:NAME})." + hint + " ")
    if typed:
        args.model_api_key = typed
    elif existing:
        args.model_api_key = existing


def _offer_install(endpoints, recommendations, args):
    print("Install a local server?")
    print("  1  Ollama")
    print("  2  Lemonade Server")
    choice = _ask("Choice (blank to skip): ").strip()
    kind = {"1": "ollama", "2": "lemonade"}.get(choice)
    if not kind:
        print("Did not install a local server.")
        return
    plan = local_models.installer(kind)
    print(plan["display"])
    print(plan["docs"])
    if not plan.get("command"):
        print(plan["after"])
        print("Did not install a local server.")
        return
    confirm = _ask("Type yes to run this official installer: ")
    if confirm.strip().lower() != "yes":
        print("Did not install a local server.")
        return
    code = local_models.run_install(plan)
    if code != 0:
        print(f"The installer exited {code}.")
        print(plan["after"])
        return
    found = local_models.probe(endpoints)
    gib = local_models.memory_gib()
    _print_scan(found, endpoints, gib, recommendations)
    if not found:
        print(plan["after"])
        return
    _choose_model(found, gib, recommendations, args)


def _discover_models(text, args, interactive):
    """Probe configured endpoints. Prompt only when this is a terminal."""
    endpoints, recommendations = _catalog(text)
    found = local_models.probe(endpoints)
    gib = local_models.memory_gib()
    _print_scan(found, endpoints, gib, recommendations)
    if found:
        if interactive:
            _choose_model(found, gib, recommendations, args)
        return
    if not interactive:
        print("Did not install a local server.")
        print("Re-run `pm setup` in a terminal to choose one, "
              "or pass --model-endpoint and --model-name.")
        return
    _offer_install(endpoints, recommendations, args)


def run(args):
    section = getattr(args, "section", None)
    interactive = _tty() and not getattr(args, "yes", False)
    if not interactive and not any([
            getattr(args, "site", None), getattr(args, "email", None),
            getattr(args, "token_env", None), getattr(args, "token", None),
            getattr(args, "project", None), getattr(args, "model_endpoint", None),
            getattr(args, "model_name", None),
            getattr(args, "model_api_key", None),
            getattr(args, "model_api_key_env", None),
            getattr(args, "confluence_space", None),
            getattr(args, "confluence_root", None),
            section]):
        sys.exit(_flags_help())

    dest = _dest(args)
    if not os.path.exists(dest):
        init_cmd.run(type("A", (), {"path": dest, "force": False})())
    if not os.path.exists(dest):
        sys.exit(f"No config at {dest}.")

    text = _read(dest)
    ask_jira = section in (None, "jira", "workstreams", "confluence")
    if interactive and ask_jira and getattr(args, "open_browser", True):
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

    discover = section == "model" or (interactive and section is None)
    if discover:
        _discover_models(text, args, interactive)

    if interactive and section in (None, "confluence"):
        _ask_confluence(text, args)

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

    if not discover and getattr(args, "model_endpoint", None):
        endpoint = getattr(args, "model_endpoint", None) or ""
        key_env = getattr(args, "model_api_key_env", None)
        if key_env:
            key = os.environ.get(key_env, "")
        else:
            key = local_models.expand_secret(getattr(args, "model_api_key", None))
        if endpoint:
            try:
                ids = sources.fetch_model_ids(endpoint, api_key=key)
                print("  Models: " + ", ".join(ids[:12]))
            except Exception as exc:                          # noqa: BLE001
                print(f"  Could not list models: {exc}")

    print("Next: pm doctor")
    if section:
        print(f"Section: {section}")
    if section == "confluence" and not interactive \
            and not getattr(args, "confluence_space", None) \
            and not getattr(args, "confluence_root", None) \
            and not getattr(args, "confluence_pages", None):
        print(_confluence_hint())
