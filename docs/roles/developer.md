# Developer

You want the Sprint Goal, what moved since yesterday, whether a story is
ready, and one ticket on screen. The weekly file that names every assignee
is the product manager's. Yours is the work, plus a snapshot of what is
assigned to you.

"Developer" here means someone on the team building the product. Changing
pm-tools itself is the "For developers" section of the README.

## Daily Scrum

```text
pm daily
```

What moved since yesterday, comments from that window, and work in
progress. This screen still says who moved a ticket. It is the working
view for the Scrum, not the role report.

## Before the team forecasts a story

```text
pm ready --workstream SDX
pm show APS-30
```

`pm ready` is the team's working agreement as a pass or fail. `pm show`
is one ticket: status, parent, and link.

## What shipped

```text
pm release-notes --since 2026-08-01
pm release-notes --version 2.4
```

`--audience leadership` shortens that to Epics. `--audience partner` is
the page with keys and names removed, for someone outside the team.

## One team in a shared file

```text
pm daily --workstream SDX
pm ready --workstream ITK
```

When your team has its own Jira project, use your own settings file. The
steps for a second file are on the [leadership](leadership.md) page:
`pm init --path`, `pm setup --path`, then `--config` before or after the
command, as in `pm daily --config ~/.pm-tools/aps.yaml`. Pass it once.

## What to leave alone

`pm do` and `pm refine --apply` write to Jira as the person whose token is
in the file, after a confirmation. They are the product manager's writes.
`pm today` is the whole open Sprint and the decisions in it, not the list
of tickets assigned to you.

## Your report

```yaml
role: developer
```

`pm report` is then the detailed report without assignees or comment
authors.

```text
pm me
pm me --sprint
```

`pm me` is the open tickets assigned to the signed-in user, as they stand
today. `pm me --sprint` is your work over that Sprint. The design is in
the [plan](../ROLE_REPORTS_PLAN.md).
