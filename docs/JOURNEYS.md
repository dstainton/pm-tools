# User journeys

Who uses pm-tools, and what a normal week looks like. The commands for each
person are in [docs/roles](roles/README.md). This file is the reasoning
behind those pages. The design is in
[ROLE_REPORTS_PLAN.md](ROLE_REPORTS_PLAN.md).

A role chooses the report. Privacy is separate: only the product-management
report names people. The analyst, the developer, and the service designer
each get their own report, and none of those reports name people.
**Leadership** and **Partners** stay the shorter files. `work` is the older
generic internal report, available with `--audience work`. Each profile
keeps its own file and its own memory of the last run.

`role` in the settings file chooses the profile. A missing `role` means
`pm`. `audiences.default` applies only when `role` is absent. `--audience`
wins for one run.

One install is one Jira user: the email and token in the settings file.
`pm today` and `pm do` act for that person. A second person who wants their
own morning list installs their own copy, or points `--config` at their own
file.

## Where each role stands

| Role | In the tool | Who runs the commands |
|---|---|---|
| Product manager | `role: pm`, or no `role` at all. The full report names people. `pm me --who` can show a colleague's open work. | They do. |
| Leadership | `role: leadership`. The short Epic report. Names stay off the page. | The product manager, who then sends the file. A leader with several teams uses one settings file each. |
| Partner | `role: partner`. The page that is safe to send. `pm metrics` stops if you ask for this audience. | The product manager. The brief is preparation, and the file says to keep it internal. |
| Business analyst | `role: analyst`. The report leads with refinement, requirement changes, and decisions. `pm ready --plan` is the planning view. | They do, from their own settings file or a shared one. |
| Developer | `role: developer`. The report leads with blockers, dependencies, ADRs, and what shipped. `pm me` is their own open work. | They do. |
| Service designer | `role: service-designer`. Changed service documentation comes before Epic detail. The design-review brief includes those pages. | They do. |

## Role in the config

```yaml
role: pm
```

| `role` | Report | Names people |
|---|---|---|
| `pm` | Product management | Yes |
| `leadership` | Portfolio | No |
| `partner` | External | No |
| `analyst` | Requirements and refinement | No |
| `developer` | Blockers, ADRs, and delivery context | No |
| `service-designer` | Service documentation and experience decisions | No |

`pm report`, `pm metrics`, `pm release-notes`, and the first `pm brief` for a meeting read this value when you leave `--audience` off. Someone who always wants the leadership file sets `role: leadership` once, and passes `--audience partner` only for the file that leaves the building.

`pm brief` remembers the depth last used for that meeting name (`--for`). A meeting you have not prepared before uses `role`, then `audiences.default`, then `pm`.

`pm me` ignores `role`. It is the signed-in user's own work.

## Product manager

This is the person who installed pm-tools. The morning screen, the backlog
checks, and the files for other people all start here.

What they need:

- A short list each morning, with a number on anything that needs a decision.
- A place to catch a thought before it is a ticket.
- A Daily Scrum view of what moved and who has what.
- A pass or fail before Sprint Planning, and a draft for the gaps.
- A weekly account of the work, and a shorter one for the rooms they walk into.
- Numbers they can stand behind: how much finishes, how long it takes, when the open work might land.

A week, with the commands that exist today:

1. Morning. `pm today` shows the Sprint Goal, what needs a decision, what moved, and what has stalled. `pm do 2` carries out item 2 after showing the change. `pm schedule add today --at 08:30` can print that screen on weekday mornings.
2. During the day. `pm note "customer wants an SSO audit export"` catches a thought. `pm inbox` files it as a ticket later. `pm show APS-30` is one ticket. `pm triage` is the queue of mentions, blocked work, and new bugs.
3. Daily Scrum. `pm daily` is what moved since yesterday, comments from that window, and work in progress.
4. Before planning. `pm lint` lists missing estimates, parents, and dates. `pm ready` is a pass or fail against the team's rules. `pm refine` drafts titles, acceptance criteria, and estimates into a file. Edit the file, then `pm refine --apply` sends back what you kept.
5. Before a meeting. `pm brief --for "Monthly portfolio review"` is what changed since you last met that group. After the meeting, `pm brief --for "Monthly portfolio review" --debrief notes.md` turns the notes into decisions and actions.
6. End of the week, or end of the Sprint. `pm report` is the full weekly file. `pm report --sprint --audience leadership` is the open Sprint for leadership. `pm publish` sends a file to Confluence or Teams after you confirm.
7. When someone asks how delivery is going. `pm metrics` is the full table. `pm metrics --audience leadership` is the headline. `pm release-notes --since 2026-08-01` is what finished.

A named window (`--since`, `--days`, `--sprint`) does not move the memory of the last run. The next plain `pm report` still starts from the last time you ran it for that audience.

## Leadership

Leadership reads. They do not run the program. They need the shape of the portfolio: which Epics are moving, which are at risk, what decision is waiting, and whether the open work has a landing date. Ticket rows, aging lists, and the refinement worksheet are the product manager's tools.

What they need:

- One line per Epic: status, how many children are done, a signal, and a target date.
- Epics marked At risk when they are blocked, past due, or due inside two weeks and still under half done (`leadership.at_risk_due_days`, 14 unless you change it).
- Decisions and risks from the registers, without the full page.
- A delivery headline: done per week, median cycle time, how much is open, and a landing date.
- What shipped, counted by Epic.

What the product manager runs:

1. The night before, or that morning. `pm warm --audience pm,leadership` prepares the summaries. `pm schedule add warm --at 07:00` can do this on a timer. Scheduled commands never write to Jira.
2. Before the meeting. `pm brief --for "Leadership" --audience leadership` is an Epic table, the decisions that room owes, and overdue or blocked work counted by Epic. The first run has no "since last time". The next run remembers this audience.
3. The Sprint review of record. `pm report --sprint --audience leadership` uses the open Sprint as the window and writes the leadership file. The sources list is Epics and documents.
4. When they ask for the numbers. `pm metrics --audience leadership` is rate, median cycle time, open count, and landing. It leaves out the aging ticket list and the forecast-points column.
5. When they ask what shipped. `pm release-notes --audience leadership --since YYYY-MM-DD` groups finished work by Epic and counts it.
6. After you have read the file. `pm publish` sends it. `pm brief --for "Leadership" --debrief notes.md` files what the room decided.

The product manager's own `pm report` is a separate file with a separate memory. Running the leadership report does not move the product-management one.

## Partner

A partner reads a page the product manager is willing to forward. The page names the work they are allowed to see, in plain status words, and it leaves out internal ticket keys, links, and names unless the settings say otherwise.

What they need:

- The features they share with you, with a status of Planned, In progress, or Delivered, and a percent done.
- Pages you have marked as safe to share.
- Release notes in sentences, without a key on every line.
- A product manager who has already decided what is owed in the room, without that worksheet being the thing that gets forwarded.

What has to be true in Jira and Confluence first:

- An Epic they should see carries the label `partner-visible`, or the workstream is marked partner-visible.
- A page they should see carries `partner-visible`.
- Anything labelled `internal` stays out of the release notes.
- Those label names live under `audiences.partner` and can be changed.

What the product manager runs:

1. `pm report --audience partner` writes the partner file. Only labelled Epics appear. Links and target dates stay off unless `include_jira_links`, `include_confluence_links`, or `show_target_dates` is turned on.
2. `pm release-notes --audience partner --since YYYY-MM-DD` keeps the labelled work and drops lines that name a person or a ticket key.
3. `pm brief --for "Partner review" --audience partner` is the preparation for that meeting. The file says it is internal. It is the list you use to walk in. The report and the release notes are the pages you can send.
4. `pm publish` sends the report or the notes after you confirm.

`pm metrics --audience partner` stops. There is no partner view of throughput or cycle time.

The partner file has its own memory. A partner report on Monday does not change the window of Friday's product-management report.

## Business analyst

The work is the refinement afternoon inside the product manager's week. The commands are on the [analyst](roles/analyst.md) page. `role: analyst` makes `pm report` the requirements report: decisions that affect requirements, changed requirement pages, dependencies, and Epic context. It does not append delivery metrics. `pm ready --plan` groups ready and not-ready work by Epic and sets that beside recent throughput, without choosing a Sprint load. `pm me` is their own open work.

What they need:

- The stories that are not ready: missing title, acceptance criteria, estimate, parent, or dates.
- A draft they can edit before anything is written to Jira.
- The team's ready rules as a pass or fail, in time for Sprint Planning.
- A tray for a request that is not a ticket yet.
- One ticket on screen while they are writing criteria.
- The same snooze decisions as the product manager, when both of them touch the backlog.

A session:

1. `pm lint --workstream SDX` lists the gaps. The result is exact. It does not ask the model.
2. `pm ready --workstream SDX` is pass or fail against the working agreement. `pm ready --deep` also asks the model, and that part is a suggestion.
3. `pm refine --workstream SDX` writes a worksheet of draft titles, criteria, and estimates. Delete a field to leave it unchanged. `pm refine --apply` writes what remains, after a preview.
4. `pm review` asks which titles are vague and which criteria are thin. Read it before acting on it.
5. `pm note "..."` and `pm inbox` catch a request and turn it into a ticket when it is ready.
6. `pm show APS-30` is the ticket they are writing against.
7. `pm coverage` lists open tickets no workstream claims, and tickets two workstreams both claim.

If the analyst is a second person:

- They can edit the refine worksheet if they can open the file. Applying it still uses the Jira token of whoever runs `pm refine --apply`.
- `state.shared_path` on a synced folder shares snooze decisions and the inbox. `today.json`, the cache, and the write log stay on each machine. The settings file describes this as the way the product manager and the analyst see the same queues.
- Their own `pm today` needs their own config. That screen is the open Sprint and the decisions in it. It is the product manager's morning list, aimed at whoever's token is in the file.

What this journey does not change:

- Ready and refine look at the workstream's backlog. They do not start from "assigned to the analyst". `pm me` is that personal list.
- `pm do` and `pm refine --apply` write to Jira as the person whose token is in the file.

## Developer

"Developer" here means someone on the Scrum team building the product. It is not the "For developers" section of the README, which is about changing pm-tools itself. The commands are on the [developer](roles/developer.md) page. `role: developer` selects a report that leads with blockers, dependencies, ADRs, and technical decisions. It does not list the whole documentation inventory, and it does not forecast the portfolio. `pm metrics --sprint` is the Sprint review.

What they need:

- The Sprint Goal and what is in the open Sprint.
- What moved since yesterday, and who is on what, in time for the Daily Scrum.
- Whether a story is ready before the team forecasts it.
- One ticket: status, parent, acceptance criteria, link.
- A short account of what shipped, when they are checking a release.

Commands:

1. `pm daily` is the Daily Scrum snapshot: movement, comments in that window, and work in progress. It does not use the model.
2. `pm ready` is the team's working agreement as a pass or fail. The team can run it before planning and ignore the rest of the morning screen.
3. `pm show APS-30` is one ticket.
4. `pm release-notes --since YYYY-MM-DD` is what finished. `--audience leadership` shortens that to Epics. The partner version is the one that strips keys.
5. `pm today` shows the open Sprint for the project: the goal, what needs a decision, what moved, what stalled. The decisions are overdue, blocked, unassigned, and untouched work. That is a portfolio view of the Sprint.

`pm me` is the open tickets assigned to the signed-in user. `pm today` stays the whole open Sprint, not that personal list.

`pm do` and `pm refine --apply` change Jira as the configured user, after a confirmation. They stay the product manager's writes.

A developer who installs pm-tools with their own token gets their own mentions inside `pm triage`, because mentions follow the account on that token. The Sprint list on `pm today` is still the whole open Sprint.

## Service designer

This is the person on the team who draws the service end to end: what a person experiences, what staff do, and which systems sit behind that. Journey maps, blueprints, and research live in Confluence beside the backlog. The commands are on the [service designer](roles/service-designer.md) page.

What they need:

- Which pages that describe the service changed: research, journey maps, blueprints, decisions.
- Which Epics a person using the service would notice.
- Decisions and risks that change the experience.
- One ticket when a story touches a step in the journey.
- The same Sprint window the product manager uses, when they are preparing a review.

With `role: service-designer`, `pm report` names that role in the header and does not name assignees, comment authors, or page editors. Changed service pages come before Epic detail. Delivery metrics are not appended.

1. `pm report` leads with research, journey, blueprint, and service pages, then decisions and risks that change the experience, then Epic movement.
2. `pm report --sprint` is that same file for the open Sprint.
3. `pm brief --for "Design review"` includes the changed Confluence pages, not only the backlog.
4. `pm show APS-30` is one ticket while they are looking at a step in the journey.
5. `pm release-notes --since YYYY-MM-DD` is what finished, when they are checking whether the experience moved.

`pm me` is their own open work, and it ignores role.

## What the guide keeps

| Journey | Where it lives |
|---|---|
| Product manager | [product-manager.md](roles/product-manager.md). [START.md](START.md) is the short form. |
| Leadership | [leadership.md](roles/leadership.md). One settings file per team when the teams do not share a project. |
| Partner | [partner.md](roles/partner.md). The labelling step, and the brief kept internal. |
| Business analyst | [analyst.md](roles/analyst.md). Requirement report, plus `pm ready --plan`. |
| Developer | [developer.md](roles/developer.md). Blockers, ADRs, and `pm metrics --sprint`. |
| Service designer | [service-designer.md](roles/service-designer.md). Changed service documentation, including the design-review brief. |
| Personal snapshot and summary | `pm me`. A snapshot is open work today. A summary is that work over a sprint or a number of days. Neither one follows role. |
