"""Local OpenAI-compatible servers: where they listen, and what fits.

The lists here are the defaults. `config.yaml` ships the same lists under
`local_models:`. `pm update` inserts that block only when it is missing, so
an edit you made is kept. Delete the block and run `pm update` to take the
catalog that shipped with the new program. When the block is absent at
runtime, these defaults are used.
"""

import os
import platform
import re
import shutil
import subprocess

import requests

from core import sources


SHIPPED_ENDPOINT = "http://127.0.0.1:8080/v1/chat/completions"
SHIPPED_NAME = "qwen-local"

# `endpoint` is the OpenAI-compatible base (it ends in /v1). Chat is
# `{endpoint}/chat/completions`. An entry may set `api_key` (or
# `${ENV:NAME}`) when that server expects a bearer token.
DEFAULT_ENDPOINTS = [
    {"name": "llama.cpp", "endpoint": "http://127.0.0.1:8080/v1"},
    {"name": "Ollama", "endpoint": "http://127.0.0.1:11434/v1"},
    {"name": "LM Studio", "endpoint": "http://127.0.0.1:1234/v1"},
    {"name": "vLLM", "endpoint": "http://127.0.0.1:8000/v1"},
    {"name": "Jan", "endpoint": "http://127.0.0.1:1337/v1"},
    {"name": "Lemonade", "endpoint": "http://127.0.0.1:13305/api/v1"},
    {"name": "GPT4All", "endpoint": "http://127.0.0.1:4891/v1"},
]

# First row whose `min_gib` is <= installed RAM wins. `models` are hints:
# a served id matches when the hint appears in it, ignoring case and
# the separators - : _ / .
DEFAULT_RECOMMENDATIONS = [
    {
        "min_gib": 48,
        "models": ["qwen3-30b", "qwen3-32b", "qwen2.5-32b"],
        "note": "About 48 GB of RAM. A 30B-class model fits.",
    },
    {
        "min_gib": 24,
        "models": ["qwen3-14b", "qwen2.5-14b"],
        "note": "About 24 GB of RAM. A 14B-class model fits.",
    },
    {
        "min_gib": 16,
        "models": ["qwen3-8b", "qwen2.5-7b", "llama3.1-8b"],
        "note": "About 16 GB of RAM. An 8B-class model fits.",
    },
    {
        "min_gib": 8,
        "models": ["qwen3-4b", "qwen2.5-3b", "llama3.2-3b"],
        "note": "About 8 GB of RAM. A 3B or 4B model fits.",
    },
    {
        "min_gib": 0,
        "models": ["qwen3-1.7b", "qwen3-0.6b", "qwen2.5-1.5b"],
        "note": "Under 8 GB of RAM. Stay with a small model.",
    },
]

_ENV_RE = re.compile(r"^\$\{ENV:([A-Za-z0-9_]+)\}$")

OLLAMA_INSTALL = "curl -fsSL https://ollama.com/install.sh | sh"
LEMONADE_SNAP = "sudo snap install lemonade-server"
LEMONADE_PPA = (
    "sudo add-apt-repository ppa:lemonade-team/stable\n"
    "  sudo apt install lemonade-server"
)


def settings(cfg):
    """Endpoint list and RAM catalog from config, or the defaults here."""
    block = cfg.get("local_models") if isinstance(cfg, dict) else None
    if not isinstance(block, dict):
        block = {}
    endpoints = block.get("endpoints")
    recommendations = block.get("recommendations")
    if not isinstance(endpoints, list) or not endpoints:
        endpoints = DEFAULT_ENDPOINTS
    if not isinstance(recommendations, list) or not recommendations:
        recommendations = DEFAULT_RECOMMENDATIONS
    return {
        "endpoints": list(endpoints),
        "recommendations": list(recommendations),
    }


def expand_secret(value):
    """Resolve `${ENV:NAME}` for a probe. An unset variable becomes blank."""
    text = str(value or "").strip()
    match = _ENV_RE.match(text)
    if not match:
        return text
    return os.environ.get(match.group(1), "")


def chat_url(endpoint):
    """Chat-completions URL for a base or a URL that is already one."""
    url = str(endpoint or "").rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/completions"):
        url = url[: -len("/completions")]
    return url + "/chat/completions"


def memory_gib():
    """Installed RAM in GiB, or None when this platform does not say."""
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / (1024 * 1024)
    except (OSError, IndexError, ValueError):
        pass
    if shutil.which("sysctl"):
        try:
            out = subprocess.check_output(
                ["sysctl", "-n", "hw.memsize"],
                text=True, timeout=2, stderr=subprocess.DEVNULL)
            return int(out.strip()) / (1024 ** 3)
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    return None


def _compact(text):
    text = str(text).lower()
    text = re.sub(r"[:_/.]+", "-", text)
    text = re.sub(r"[^a-z0-9-]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def _fitting_row(catalog, gib):
    if gib is None:
        return None
    rows = []
    for row in catalog or []:
        if not isinstance(row, dict):
            continue
        try:
            minimum = float(row.get("min_gib") or 0)
        except (TypeError, ValueError):
            continue
        rows.append((minimum, row))
    rows.sort(key=lambda pair: pair[0], reverse=True)
    for minimum, row in rows:
        if gib >= minimum:
            return row
    return None


def recommend(ids, catalog, gib):
    """Return `(model_id or None, note)`.

    One served model is the recommendation. Otherwise the catalog row
    with the highest `min_gib` that still fits is matched against the
    served ids. Unknown RAM does not invent a size.
    """
    clean = [str(item) for item in (ids or []) if item]
    row = _fitting_row(catalog, gib)
    if gib is None:
        note = "Could not read system memory, so there is no size recommendation."
    elif row is not None:
        note = str(row.get("note") or "")
    else:
        note = "No size recommendation matches this machine."
    if len(clean) == 1:
        return clean[0], note or "This server has one model."
    if gib is None or row is None:
        return None, note
    hints = [_compact(hint) for hint in (row.get("models") or []) if hint]
    for model_id in clean:
        compact = _compact(model_id)
        if any(hint and hint in compact for hint in hints):
            return model_id, note
    extra = " None of the served models match that size."
    return None, (note + extra) if note else extra.strip()


def probe(endpoints, timeout=2):
    """Ask each server for model ids. A failure is skipped.

    A 200 with an empty list still counts as responsive. `api_key` on an
    entry is sent as a bearer token when it is set.
    """
    rows = [
        item for item in (endpoints or [])
        if isinstance(item, dict) and item.get("endpoint")
    ]
    if not rows:
        return []

    def one(item):
        try:
            ids = sources.fetch_model_ids(
                str(item["endpoint"]),
                api_key=expand_secret(item.get("api_key")),
                timeout=timeout)
        except (requests.RequestException, ValueError, OSError):
            return None
        return {
            "name": str(item.get("name") or item["endpoint"]),
            "endpoint": str(item["endpoint"]),
            "api_key": str(item.get("api_key") or ""),
            "models": list(ids or []),
        }

    from concurrent.futures import ThreadPoolExecutor
    found = []
    workers = min(8, len(rows))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(one, rows):
            if result is not None:
                found.append(result)
    return found


def installer(kind):
    """Official install for Ollama or Lemonade, or instructions when none.

    `command` is None when this platform has no single unattended command.
    The caller runs `command` only after the user types yes.
    """
    system = platform.system()
    if kind == "ollama":
        docs = "https://ollama.com/download"
        after = ("Start it with `ollama serve` if it is not already running, "
                 "then run `pm setup --section model`.")
        if system == "Linux":
            return _plan("Ollama", docs,
                         ["sh", "-c", OLLAMA_INSTALL], OLLAMA_INSTALL, after)
        if system == "Darwin" and shutil.which("brew"):
            return _plan("Ollama", docs, ["brew", "install", "ollama"],
                         "brew install ollama", after)
        if system == "Windows" and shutil.which("winget"):
            display = "winget install --id Ollama.Ollama -e"
            return _plan("Ollama", docs,
                         ["winget", "install", "--id", "Ollama.Ollama", "-e"],
                         display, after)
        return _plan("Ollama", docs, None,
                     "Download the installer from https://ollama.com/download",
                     after)
    if kind == "lemonade":
        docs = "https://lemonade-server.ai/docs/guide/install/"
        after = ("Lemonade listens at http://127.0.0.1:13305/api/v1. "
                 "Then run `pm setup --section model`.")
        if system == "Linux" and shutil.which("snap"):
            return _plan("Lemonade Server", docs,
                         ["sudo", "snap", "install", "lemonade-server"],
                         LEMONADE_SNAP, after)
        if system == "Windows" and shutil.which("winget"):
            display = "winget install --id AMD.LemonadeServer -e"
            return _plan(
                "Lemonade Server", docs,
                ["winget", "install", "--id", "AMD.LemonadeServer", "-e"],
                display, after)
        display = LEMONADE_SNAP + "\n  or, on Ubuntu:\n  " + LEMONADE_PPA
        return _plan("Lemonade Server", docs, None, display, after)
    raise ValueError(f"unknown installer {kind}")


def _plan(name, docs, command, display, after):
    return {
        "name": name,
        "docs": docs,
        "command": command,
        "display": display,
        "after": after,
    }


def run_install(plan):
    """Run an official installer. Returns the exit code, or None if none."""
    command = plan.get("command") if isinstance(plan, dict) else None
    if not command:
        return None
    completed = subprocess.run(command, check=False)
    return completed.returncode


def yaml_quote(value):
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def catalog_lines():
    """Indented body of the `local_models:` block inserted by migration."""
    lines = [
        "  # Servers `pm setup` probes. `endpoint` is the OpenAI-compatible",
        "  # base, ending in /v1. Chat is that base plus /chat/completions.",
        "  # Add api_key on an entry when that server expects a bearer token.",
        "  # This catalog is updated in the GitHub template. `pm update`",
        "  # inserts the block only when it is missing. Delete `local_models:`",
        "  # and run `pm update` to take the catalog shipped with the new program.",
        "  endpoints:",
    ]
    for item in DEFAULT_ENDPOINTS:
        lines.append(f"    - name: {yaml_quote(item['name'])}")
        lines.append(f"      endpoint: {yaml_quote(item['endpoint'])}")
    lines.append("  recommendations:")
    lines.append("    # First row whose min_gib is <= installed RAM wins.")
    lines.append("    # `models` are hints. A served id matches when the hint")
    lines.append("    # appears in it, ignoring case and - : _ / .")
    for row in DEFAULT_RECOMMENDATIONS:
        lines.append(f"    - min_gib: {int(row['min_gib'])}")
        quoted = ", ".join(yaml_quote(model) for model in row["models"])
        lines.append(f"      models: [{quoted}]")
        lines.append(f"      note: {yaml_quote(row['note'])}")
    return lines
