# Role reports and a personal snapshot

A plan for who a report names, and for a report about one person's own work.
The journeys in [JOURNEYS.md](JOURNEYS.md) are the notes this plan decides from.
[REPORTING_PLAN.md](REPORTING_PLAN.md) stays as it was: it shipped the three
audiences this plan builds on.

Nothing here is built yet.

## The decision

Only the product manager's report names individual people: assignees, comment
authors, the person who edited a page, and the owner of a register entry.
Every other report describes the work and leaves the names out.

Two more reports are about one person, and they ignore role:

- A **snapshot** of that person's open work, as it stands today. It is not
  "what changed since last time."
- A **summary** of that person's work over a sprint or a stretch of days.

An analyst, a developer, and a service designer do not each get their own
report shape. They share one detailed report with the names removed. Leadership
stays the short report. Partner stays the report that is safe to send outside
the team.

## What is true today

`audiences.default` is already the shape used when `--audience` is left off.
`pm report`, `pm metrics`, and `pm release-notes` read it. A missing value
means `pm`. `pm brief` remembers the depth of each meeting, and a meeting
that has never been prepared starts at `pm` even when `audiences.default`
is something else.

The product-management report names people in several places:

- The sources table has an Assignee column (`core/report_render.py`,
  `sources_appendix`).
- Changed pages say who edited them (`docs_block`, "by {name}").
- Register entries can show an Owner. Leadership still shows that owner on
  decisions (`register_block`, `show_owner`).
- Comments are rendered as `2026-09-22 Dana: the excerpt`
  (`core/comments.py`, `format_line`).
- The material sent to the model includes `Assignee:` on each issue
  (`core/model.py`, `_item_line`).

Leadership already drops the sources table and speaks in Epics. Partner
already drops lines that contain a person's name (`core/audience.py`,
`redact`). The leaks are the ones in the list above: a leadership decision
owner, a comment author on a non-pm release note, an assignee inside a model
prompt.

A weekly report is a window. With no flags it starts at the last run for
that audience and then moves that memory. `--since`, `--days`, and
`--sprint` are a read: they set the window and leave the memory where it
was (`core/window.py`). There is no report that means "where do things
stand right now," and there is no report limited to `assignee = currentUser()`.
That query exists (`core/queries.py`, `assignee.me`) and is not used by the
report.

`pm today` is the open Sprint for the whole project, plus the decisions in
it. It is not a personal snapshot.

## Shapes

Four shapes. The first three exist. `work` is new.

| Shape | People | What the file contains |
|---|---|---|
| `pm` | Yes | The full weekly report: Epics, child items, pages, registers, comments, and the sources table with assignees. |
| `work` | No | The same full report, with every person field omitted. |
| `leadership` | No | The short file: Epic table, signal, target, headline delivery numbers. Person fields that still slip through are removed. |
| `partner` | No | Labelled Epics and pages only, in plain status words. The existing redaction stays. Person fields are removed before that pass. |

`pm metrics --audience partner` still stops. `work` uses the full metrics
tables, which already speak in counts rather than names. Leadership keeps
the headline table.

## Role

`role` is the setting a person writes once. It chooses the shape for
`pm report`, `pm metrics`, `pm release-notes`, and the first `pm brief`
for a meeting. A later brief for that same meeting keeps the depth it
already saved.

| `role` | Shape |
|---|---|
| `pm` | `pm` |
| `leadership` | `leadership` |
| `partner` | `partner` |
| `analyst` | `work` |
| `developer` | `work` |
| `service-designer` | `work` |

Missing `role` means `pm`. Current installs keep today's behaviour.

```yaml
role: pm
```

Resolution for one run:

1. `--audience`, when passed, wins. Add `work` to the allowed values.
2. Otherwise `role`, when set, maps to a shape.
3. Otherwise `audiences.default`.
4. Otherwise `pm`.

`audiences.default` stays so a file that already sets it keeps working.
On a new install, set `role` and leave `audiences.default` at `pm`. When
`role` is set, it wins over `audiences.default`. The config comment says
that, so the two lines cannot be read as a tie.

`--audience work` lets a product manager preview the nameless file without
changing `role`.

`pm brief` on a new meeting uses this same resolution instead of a hardcoded
`pm`. A saved meeting depth still wins over `role`.

## Names come out everywhere except `pm`

One predicate, `names_people(shape)`, is true only for `pm`. Render and
prompt code ask it. The gathered records can still carry assignee and
author; the file and the model prompt are what change.

When the shape is not `pm`:

- The sources table omits the Assignee column.
- Page lines omit "by {name}". The date and the title stay.
- Register lines omit Owner, including leadership decisions.
- Comment lines are `2026-09-22: the excerpt`, with the author removed.
- `_item_line` does not append `Assignee:`.
- Partner redaction still runs after that, for keys, links, and any name
  that arrived inside model prose.

`pm today`, `pm daily`, `pm show`, `pm lint`, and `pm ready` keep names.
They are working screens, not the role report. A Daily Scrum still says
who moved a ticket.

## Snapshot

`pm me` with no window flags.

This is a point in time. It does not read or write the weekly-report
memory, and it does not remember the previous snapshot. Running it twice
in one day can produce the same file. Role is ignored: a service designer
and a product manager get the same kind of page, about the signed-in
account.

Who it includes:

- The signed-in Jira user (`assignee = currentUser()`), inside the
  configured projects.
- Open issues only. Finished work belongs in the summary.
- Issues that sit outside every workstream still appear, under a heading
  "Outside your workstreams", so a missing Component does not hide your
  own ticket.

What it shows, without calling the model:

- The date, and the line "Snapshot. This is where the work stands, not what changed since last time."
- The open Sprint's name and goal, when any of these issues are in that Sprint.
- Counts: open, in progress, blocked, overdue.
- One block per workstream, then per Epic. Each issue shows key, summary, type, status, Sprint, due date, and days since it was updated. Blocked issues say so.

Printed to the terminal and written to `me_snapshot_{date}.md` under the
output directory.

## Summary

`pm me` with a window: `--sprint`, `--since YYYY-MM-DD`, or `--days N`.
`pm me --summary` uses the usual window from config when you do not want
to type it:

```yaml
me:
  summary: sprint    # or a number of days, such as 14
```

Missing `me.summary` means the open Sprint. `--sprint`, `--since`, and
`--days` override that for one run. The window is a read. It does not move
the weekly-report memory or any personal memory.

The summary covers issues assigned to the same person, in the same
projects:

- Finished in the window.
- Still open, and updated in the window.
- Comments on those issues in the window, author included, because the
  subject is this person and the comment is about their work.
- Still open at the end, even if nothing moved, as a short list of what
  remains.

Grouped by Epic. No model in the first version. The file is
`me_summary_{stamp}.md`, where the stamp is the sprint id or the start
date, plus today's date.

## Asking about someone else

`--who "A. Lee"` selects a person other than the signed-in user, for either
the snapshot or the summary. Lookup uses the existing user search
(`core/sources.py`, `resolve_assignee`).

Only a product manager can pass `--who`. The check is the effective shape:
it must be `pm`, from `role`, from `audiences.default`, or from
`--audience pm` on that run. Anyone else gets a one-line refusal and the
report does not run. Their own `pm me` still works.

A product manager's own `pm me`, with no `--who`, is the signed-in account,
not the whole team. The team, with names, remains `pm report`.

## Files to touch

- `core/audience.py`: shapes include `work`. `resolve_shape(cfg, args)`
  implements the order above. `names_people(shape)`. Role names and the
  map live here.
- `core/config.py`: `role` is one of the six names when present. `work` is
  a legal `audiences.default`. `me.summary` is `sprint` or a positive
  integer.
- `config.yaml`: comments and the `role` and `me` examples. No
  `config_version` bump. Both keys are optional, and missing means today's
  behaviour plus "summary uses the open Sprint" once `pm me` exists.
- `core/report_render.py`, `core/model.py`, `core/comments.py`: the name
  omissions. `format_line` gains an author switch rather than a second
  formatter.
- `commands/report.py`, `commands/brief.py`, `commands/release_notes.py`,
  `commands/metrics.py`: ask `resolve_shape`. Brief's first meeting uses
  it. Metrics accepts `work` and refuses `partner` as it does now.
- `commands/me.py`: snapshot and summary. New.
- `pm.py`: `pm me`, `--who`, `--summary`, and the window flags already used
  by `pm report`. `--audience` choices gain `work` on report, brief,
  metrics, release notes, and `pm me` (so a product manager can pass
  `--audience pm --who` from a non-pm default).
- `docs/JOURNEYS.md` and the README line that points at it: follow this
  plan once it is agreed. The config comment for `audiences.default`
  mentions `role`.

## Steps

1. **Names.** `names_people` and the omissions in the render, the comment
   line, and the model material. Leadership and partner tests cover a
   decision owner, a comment author, and an assignee line.
2. **Shape `work`.** The pm render with names off, its own output file, and
   `--audience work`. A test that the sources table has no Assignee column
   and the Epic sections remain.
3. **`role`.** The map, the resolution order, config validation, and the
   brief's first meeting. A test that `role: service-designer` produces
   `work` even when `audiences.default` is `pm`, and that `--audience
   leadership` still wins for that run.
4. **Snapshot.** `pm me` against a fake Jira: open issues for the current
   user, an issue with no Component, nothing written to report state.
5. **Summary.** `pm me --sprint` and `pm me --days 14`. Finished versus
   still open. Report state unchanged.
6. **`--who`.** A pm role resolves a name. A `work` role is refused. The
   signed-in user's snapshot still runs.

## Tests already implied

- Partner redaction still removes a name that the model wrote, after the
  author strip.
- `pm metrics --audience work` returns the full tables. `partner` still
  exits.
- A snapshot does not call the model.
- Two shapes in one suite do not share report-state files (`work` uses the
  same `output_name` rule as `leadership`).

## Not in this plan

- A different prose prompt per role. Analyst, developer, and service
  designer read one nameless detailed report.
- A snapshot that compares itself with the previous snapshot.
- Changing `pm today` into "assigned to me".
- Letting a non-pm role list a colleague's work.
- Any edit to `docs/REPORTING_PLAN.md` or `docs/USABILITY_PLAN.md`.
