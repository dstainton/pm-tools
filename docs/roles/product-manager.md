# Product manager

You run pm-tools for the team. The morning screen, the backlog checks, and
the files other people read all start here. With no `role` set, this is the
report you get.

## A typical morning

```text
pm today
pm do 2
```

`pm today` is the Sprint Goal and a numbered list of what needs a decision.
`pm do 2` carries out item 2 after showing you the change. It asks before
it writes to Jira.

Catch a thought without leaving what you were doing:

```text
pm note "customer wants an SSO audit export"
pm inbox
```

`pm inbox` is where that note waits until you turn it into a ticket or drop
it.

## Daily Scrum

```text
pm daily
```

What moved since yesterday, comments from that window, and who has what now.

## Before planning

```text
pm lint --workstream SDX
pm ready --workstream SDX
pm refine --workstream SDX
```

`pm lint` lists missing estimates, parents, and dates. `pm ready` is a pass
or fail against the team's rules. `pm refine` writes a worksheet of draft
titles, acceptance criteria, and estimates. Edit the file, then:

```text
pm refine --apply
```

That shows the change and asks before it writes.

## The weekly file, with names

```text
pm report
pm report --sprint
```

`pm report` covers the time since the last product-management report, then
remembers this run. `pm report --sprint` is the open Sprint and does not
move that memory. This file names assignees, comment authors, and who
edited a page. It is the one report that does.

One product or one team:

```text
pm report --product IP
pm report --workstream SDX --sprint
```

## Files for other rooms

```text
pm report --sprint --audience leadership
pm brief --for "Leadership" --audience leadership
pm report --audience partner
pm release-notes --audience partner --since 2026-08-01
```

`--audience` is for this run only. Your next plain `pm report` is still the
product-management file.

Before a meeting that is not one of those three shapes:

```text
pm brief --for "Monthly portfolio review"
```

After it:

```text
pm brief --for "Monthly portfolio review" --debrief notes.md
```

Send a file you have read:

```text
pm publish ~/.pm-tools/out/weekly_report_leadership_2026-09-28.md
```

## One ticket

```text
pm show APS-30
```

## Your own work

```text
pm me
pm me --who "A. Lee"
pm me --sprint
```

`pm me` is the open work assigned to the signed-in account, as it stands
today. It does not compare with a previous date, and it does not move the
weekly report memory. `pm me --who "A. Lee"` is the same page for someone
else. That flag is only available when the report shape is `pm`.
`pm me --sprint` is the work finished and still open in the open Sprint.

Other roles: [leadership](leadership.md), [partner](partner.md),
[analyst](analyst.md), [developer](developer.md),
[service designer](service-designer.md).
