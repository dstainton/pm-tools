"""`pm mcp` — a stdio MCP server for the read-only commands.

Off unless you run it. Copilot is not local: anything a tool returns
leaves the machine. The allowlist is `commands.schedule.SAFE`, so a
write command cannot be exposed by being forgotten here.

`pm` supplies the facts. The client does the talking.
"""

import json
import os
import subprocess
import sys

from commands import schedule

# Tool argument -> pm option. Only options the command accepts are offered.
_OPTIONS = {
    "workstream": ("--workstream", "string"),
    "product": ("--product", "string"),
    "sprint": ("--sprint", "string"),
    "since": ("--since", "string"),
    "days": ("--days", "integer"),
}

CALL_TIMEOUT = 600


def _accepted(name):
    import pm
    parser = pm.build_parser()._pm_subs.get(name)
    if parser is None:
        return set()
    return {flag for action in parser._actions for flag in action.option_strings}


def tool_names():
    """One tool per safe command. Writes stay out."""
    return sorted(name for name, args in schedule.SAFE.items() if args is not None)


def tools_payload():
    tools = []
    for name in tool_names():
        accepted = _accepted(name)
        properties = {key: {"type": kind} for key, (flag, kind) in _OPTIONS.items()
                      if flag in accepted}
        tools.append({
            "name": name,
            "description": (
                f"Run `pm {name}` and return what it prints"
                + (" as JSON" if name == "today" else "")
                + ". Read-only. Nothing is written to Jira."
            ),
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "additionalProperties": False,
            },
        })
    return tools


def command_line(name, arguments, config_path=None):
    """argv for one tool call. Raises ValueError on an argument pm would not take."""
    accepted = _accepted(name)
    argv = [name] + list(schedule.SAFE.get(name) or [])
    for key, value in (arguments or {}).items():
        if key not in _OPTIONS or _OPTIONS[key][0] not in accepted:
            raise ValueError(f"pm {name} does not take {key}.")
        flag, kind = _OPTIONS[key]
        if kind == "integer":
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{key} must be a whole number of 1 or more.")
        elif not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must be a non-empty string.")
        # --flag=value keeps a value that starts with "-" from reading as an option.
        argv.append(f"{flag}={value}")
    argv.append("--json" if name == "today" else "--plain")
    if name == "daily":
        argv.append("--print")
    if config_path:
        argv.append(f"--config={config_path}")
    return argv


def call_tool(name, arguments, config_path=None):
    try:
        argv = command_line(name, arguments, config_path)
    except ValueError as exc:
        return _error(str(exc))
    import pm
    env = dict(os.environ, NO_COLOR="1")
    try:
        proc = subprocess.run(
            [sys.executable, os.path.abspath(pm.__file__)] + argv,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            stdin=subprocess.DEVNULL, env=env, timeout=CALL_TIMEOUT)
    except subprocess.TimeoutExpired:
        return _error(f"pm {name} took longer than {CALL_TIMEOUT} seconds.")
    except OSError as exc:
        return _error(f"pm {name} could not start: {exc}")
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return _error(f"pm {name} exited with {proc.returncode}.\n{detail[-2000:]}")
    return {"content": [{"type": "text", "text": proc.stdout}]}


def _error(text):
    return {"isError": True, "content": [{"type": "text", "text": text}]}


def handle(message, config_path=None):
    kind = message.get("method")
    if kind == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "pm", "version": "0"},
        }
    if kind == "tools/list":
        return {"tools": tools_payload()}
    if kind == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        if name not in tool_names():
            return _error(f"{name} is not a read-only pm tool.")
        return call_tool(name, params.get("arguments") or {}, config_path)
    return {}


def run(cfg, args):
    """Speak newline-delimited JSON on stdin/stdout. One object per line."""
    if not getattr(args, "yes_i_understand", False):
        sys.exit(
            "pm mcp sends tool results to the client. Copilot is not local, "
            "so those results leave this machine.\n"
            "Run `pm mcp --yes-i-understand` to start it. It is off by default."
        )
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            print(json.dumps({"error": "invalid json"}))
            continue
        if "id" not in message:
            continue    # a notification, such as notifications/initialized
        result = handle(message, getattr(args, "config", None))
        reply = {"jsonrpc": "2.0", "id": message.get("id"), "result": result}
        print(json.dumps(reply), flush=True)
