# Business analyst

You get stories ready for planning: a missing title, acceptance criteria,
or estimate, and a draft you can edit before anything is written to Jira.
You and the product manager can share snooze decisions and the inbox. You
do not need a report that names who on the team holds each ticket.

## The refinement session

```text
pm lint --workstream SDX
pm ready --workstream SDX
pm refine --workstream SDX
```

`pm lint` lists the gaps. The result follows fixed rules. `pm ready` is a
pass or fail against the team's working agreement. `pm ready --deep` also
asks the model, and that part is a suggestion you read before you act on
it.

`pm refine` writes a worksheet. Delete a field to leave it unchanged.
Apply what you kept:

```text
pm refine --apply
```

The command shows the write and asks first. It uses the Jira token of
whoever runs it.

Titles and criteria, as a suggestion:

```text
pm review --workstream SDX
```

## One ticket while you write

```text
pm show APS-30
```

## A request that is not a ticket yet

```text
pm note "the export should include the audit id"
pm inbox
```

`pm inbox create 1` turns note 1 into a ticket after you confirm.

## The same decisions as the product manager

Set `state.shared_path` in both settings files to a synced folder. Snooze
decisions and the inbox are shared. The morning list, the cache, and the
write log stay on each machine.

```yaml
state:
  shared_path: "~/OneDrive/pm-tools-shared"
```

## Tickets no team owns

```text
pm coverage
```

Open tickets no workstream claims, tickets two workstreams both claim, and
Components nobody uses.

## Your report

```yaml
role: analyst
```

`pm report --sprint` is then the detailed report with people's names left
out. You share that shape with the developer and the service designer.

```text
pm me
pm me --sprint
```

`pm me` is your own open work as a snapshot. `pm me --sprint` is that work
over the open Sprint. A report about a colleague is the product manager's
command. The design is in the [plan](../ROLE_REPORTS_PLAN.md).
