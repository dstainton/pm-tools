# Service designer

You follow the service end to end: what a person experiences, what staff
do, and which systems sit behind that. Journey maps, research, and
blueprints live in Confluence beside the backlog. You need the pages, the
decisions, and the Epics. You do not need a report that names who holds
each ticket.

## What changed in the service

```text
pm report --sprint
pm report --workstream SDX --sprint
```

With `role: service-designer`, changed research, journey, blueprint, and
service pages come first, then decisions and risks that affect the
experience, then Epic movement. The header names the service designer
role. Assignees, page editors, and comment authors stay off the page.
`--sprint` is the open Sprint and does not move the memory of the last
report. Delivery metrics are not appended.

## A design review

```text
pm brief --for "Design review"
```

What changed since you last prepared that meeting, including changed
service documentation. After the review:

```text
pm brief --for "Design review" --debrief notes.md
```

## One story that touches a step

```text
pm show APS-30
```

## What just shipped

```text
pm release-notes --since 2026-09-15
```

## Your own settings file

If the service crosses a team that already has a file, `--workstream` is
enough. If you keep research in a different Confluence space, use a
settings file of your own. Creating a second file is written out on the
[leadership](leadership.md) page.

```text
pm report --config ~/.pm-tools/service.yaml --sprint
```

## Your report

```yaml
role: service-designer
```

That selects the service-designer report. It is not the analyst report
and it is not the developer report. `--audience work` is the older generic
internal report, for one run.

```text
pm me
```

`pm me` is your own open work as a snapshot, and it ignores role.
