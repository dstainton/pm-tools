# Automation

`pm` stays a program you run. It does not listen on a port.

## Overnight warm

`pm warm` fills the model cache in this order: review, page summaries, the report, then the inbox. Schedule it before the report so the morning run is a cache hit:

```
pm schedule add warm --at 06:30
pm schedule add report --at 07:30
```

`pm warm --audience pm,leadership` also drafts the leadership product summaries. `audiences.warm` in config is the list used when `--audience` is omitted.

## Scripts

Read commands accept `--json` where a script needs structure (`pm lint --json`, `pm metrics --json`, `pm today --json`, `pm show KEY --json`). `pm schedule` registers read-only commands and refuses anything that writes.

Exit status: `pm lint --fail-on error` and `pm ready --fail-under` exit non-zero when the gate fails. `pm coverage` exits non-zero when work is unclaimed. Other commands exit non-zero when they cannot do what you asked.

## Power Automate

A cloud flow cannot start a program on your laptop. Two patterns work:

- Power Automate Desktop runs `pm` on the machine.
- `pm` writes JSON or Markdown into a OneDrive or SharePoint folder (`state.shared_path` or `--out`) and a cloud flow triggers on the new file.

## MCP

`pm mcp` speaks newline-delimited JSON on stdin. It is off until you pass `--yes-i-understand`. The tools are the read-only commands in `commands/schedule.py` (`SAFE`). `pm do`, `pm refine`, and the other write commands are not tools. Copilot is not local: a tool result leaves the machine. The local-model promise is unchanged for every other command.
