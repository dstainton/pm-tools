# Everyday commands

Once `pm setup` has run, these are the commands that fill a week.

- `pm today` each morning. `pm do N` for the number on the screen.
- `pm lint` prints the findings, then writes the file. Severity is a word (`Error`, `Warn`, `Review`).
- `pm ready` is the team's working agreement, as a pass or a fail.
- `pm refine` is the queue for titles, criteria, and estimates.
- `pm note` and `pm inbox` are capture and filing.
- `pm report` and `pm brief` narrate a period. With no flags they mean "since last time". `--since YYYY-MM-DD`, `--days`, and `--sprint 138` ask for a window. A named window does not move the "last time" memory. `role` chooses the report: product management, analyst, developer, service designer, leadership, or partner. `--audience work` is the older generic internal report. `--audience` overrides the role for one run. Each profile keeps its own file and its own memory. A missing `role` means product management. `--sources full` adds the source tables. The default keeps the inline citations.
- `pm ready --plan` is the planning view. `pm metrics --sprint` is the Sprint review. `pm today --all` includes blocker links. Full delivery tables stay on `pm metrics`.
- `pm me` is your own open work as it stands today. `--sprint`, `--since`, or `--days` is that window. It does not move the weekly-report memory.
- `pm show APS-30` is one issue, on screen.

A Sprint is both the issues in it and the fortnight it covers. `--sprint 138` uses both.
