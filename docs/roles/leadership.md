# Leadership

You read the short report: one line per Epic, what is at risk, and whether
the open work has a landing date. You do not need the refinement worksheet
or the names of individual people.

Put `role: leadership` in the settings file and the short report is the
default. `--audience` still wins for one run. The leadership file leaves
out assignees, comment authors, and decision owners.

## One team in the file

When several teams share a Jira project and one settings file, name the
team:

```text
pm report --workstream SDX --audience leadership --sprint
pm metrics --workstream SDX --audience leadership
pm release-notes --workstream SDX --audience leadership --since 2026-08-01
```

`--product IP` is the same idea for a whole product. `--sprint` uses the
open Sprint and does not move the memory of the last leadership report.

Before the meeting:

```text
pm brief --for "Leadership" --audience leadership
```

The first run has no "since last time". The next one remembers this meeting.

## Several teams, one config each

Use a separate settings file when the teams do not share a Jira project, a
Confluence space, or a token. Each file has its own products, workstreams,
and output folder, so the reports do not overwrite each other.

Create one file per team, then fill it in. `pm setup` will not replace a
value you have already set.

```text
pm init --path ~/.pm-tools/aps.yaml
pm setup --path ~/.pm-tools/aps.yaml
pm init --path ~/.pm-tools/des.yaml
pm setup --path ~/.pm-tools/des.yaml
```

Point both files at the same token in the environment, so the token is not
copied into either file:

```yaml
api_token: "${ENV:JIRA_TOKEN}"
```

Give each file its own output folder:

```yaml
output:
  directory: "~/.pm-tools/out/aps"
```

The settings flag can go before or after the command name. Pass it once.
On Windows PowerShell, with `role: leadership` in each file:

```powershell
pm doctor --config $HOME\.pm-tools\aps.yaml
pm --config $HOME\.pm-tools\aps.yaml report --sprint
pm report --config $HOME\.pm-tools\des.yaml --sprint
```

On macOS or Linux, `~/.pm-tools/aps.yaml` is the same path. `PM_CONFIG`
points a whole terminal session at one file:

```powershell
$env:PM_CONFIG = "$HOME\.pm-tools\aps.yaml"
pm report --sprint
```

Check each file on its own. `pm doctor` tells you what is wrong in the file
it opened.

```text
pm doctor --config ~/.pm-tools/aps.yaml
pm doctor --config ~/.pm-tools/des.yaml
```

## What you can skip

`pm lint`, `pm refine`, and `pm do` are the product manager's tools. The
leadership file is `pm report`, `pm metrics`, `pm release-notes`, and
`pm brief`.

## The setting

```yaml
role: leadership
```

With that line, `pm report --sprint` is the short Epic report. Decision
owners and comment authors stay off the page. The design is in the
[plan](../ROLE_REPORTS_PLAN.md).
