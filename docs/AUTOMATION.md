# Automation

`pm` stays a program you run. It does not listen on a port.

## Overnight warm

`pm warm` fills the model cache in this order: review, page summaries, the report, then the inbox. Schedule it before the report so the morning run is a cache hit:

```
pm schedule add warm --at 06:30
pm schedule add report --at 07:30
```

`pm warm --audience pm,leadership` also drafts the leadership product summaries. `work` belongs in that list when the install uses the nameless report. `audiences.warm` in config is the list used when `--audience` is omitted, and a scheduled `warm` always uses it, so set it to the profiles you report on, for example `[pm, leadership]`. A nameless shape is cached separately from `pm`, because that prompt leaves people's names out.

## Scripts

Some read commands accept `--json` where a script needs structure. `pm lint --json` and `pm metrics --json` write a JSON file and print its path. `pm report --json` writes a JSON file beside the Markdown report. `pm show KEY --json` prints JSON. `pm today --json` prints only the numbered actions as JSON on standard output; progress goes to standard error, and the list is still saved to `today.json`. `pm schedule` registers read-only commands and refuses anything that writes.

Exit status: `pm lint --fail-on error` and `pm ready --fail-under` exit non-zero when the gate fails. `pm coverage` exits non-zero when work is unclaimed. Other commands exit non-zero when they cannot do what you asked.

## Power Automate

A cloud flow cannot start a program on your laptop. Two patterns work:

- Power Automate Desktop runs `pm` on the machine.
- `pm` writes JSON or Markdown into a OneDrive or SharePoint folder (`state.shared_path` or `--out`) and a cloud flow triggers on the new file.

## MCP

`pm mcp` speaks newline-delimited JSON on stdin. It is off until you pass `--yes-i-understand`. `tools/list` names the read-only commands in `commands/schedule.py` (`SAFE`), except `brief`. `tools/call` does not run the command yet: it returns a note to run it with `--json`. `pm do`, `pm refine`, and the other write commands are not tools. Copilot is not local: a tool result leaves the machine. The local-model promise is unchanged for every other command.
