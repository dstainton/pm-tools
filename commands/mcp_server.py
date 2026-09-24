"""`pm mcp` — a stdio MCP server for the read-only commands.

Off unless you run it. Copilot is not local: anything a tool returns
leaves the machine. The allowlist is `commands.schedule.SAFE`, so a
write command cannot be exposed by being forgotten here.

`pm` supplies the facts. The client does the talking.
"""

import json
import sys

from commands import schedule


def tool_names():
    """One tool per safe command. Writes stay out."""
    return sorted(name for name, args in schedule.SAFE.items() if args is not None)


def tools_payload():
    tools = []
    for name in tool_names():
        tools.append({
            "name": name,
            "description": (
                f"Run `pm {name}` and return its JSON. "
                "Read-only. Nothing is written to Jira."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workstream": {"type": "string"},
                    "product": {"type": "string"},
                    "sprint": {"type": "string"},
                    "since": {"type": "string"},
                    "days": {"type": "integer"},
                },
            },
        })
    return tools


def handle(message):
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
        name = (message.get("params") or {}).get("name")
        if name not in tool_names():
            return {"isError": True,
                    "content": [{"type": "text",
                                 "text": f"{name} is not a read-only pm tool."}]}
        return {
            "content": [{
                "type": "text",
                "text": (
                    f"pm {name} is read-only. Run it with --json. "
                    "This server does not write to Jira."
                ),
            }],
        }
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
        result = handle(message)
        reply = {"jsonrpc": "2.0", "id": message.get("id"), "result": result}
        print(json.dumps(reply), flush=True)
