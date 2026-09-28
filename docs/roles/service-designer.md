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

The report includes changed Confluence pages, the decision, risk, and ADR
registers, and the Epics. `--sprint` is the open Sprint and does not move
the memory of the last report.

Today this file still names assignees and page editors, because the default
report is the product manager's. The [plan](../ROLE_REPORTS_PLAN.md) changes
that for this role: the same detail, without the names.

## A design review

```text
pm brief --for "Design review"
```

What changed since you last prepared that meeting. After the review:

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

## Planned

`role: service-designer` selects the detailed report with people's names
left out. You share that shape with the analyst and the developer.
`pm me` is your own open work as a snapshot, and it ignores role. See the
[plan](../ROLE_REPORTS_PLAN.md).
