# User journeys

A working list of who uses pm-tools, and what a normal week looks like for
each of them. The aim is to choose which journeys belong in the guide.
Nothing here adds a setting or a command.

Three report shapes already exist. **Product management** is the full file,
and it is the default. **Leadership** and **Partners** are the shorter
files a product manager writes for other rooms, with `pm report`,
`pm brief`, `pm metrics`, and `pm release-notes`. Each shape keeps its own
file and its own memory of the last run.

**Business analyst**, **developer**, and **service designer** are sketched
below so the need is visible. The plan in
[ROLE_REPORTS_PLAN.md](ROLE_REPORTS_PLAN.md) gives them one shared detailed
report with people's names left out, plus a personal snapshot that ignores
role.

One install is one Jira user: the email and token in the settings file.
`pm today` and `pm do` act for that person. A second person who wants their
own morning list installs their own copy, or points `--config` at their own
file.

## Where each role stands

| Role | In the tool today | Who runs the commands |
|---|---|---|
| Product manager | The person the program is built for. `audiences.default` is `pm` unless you change it. | They do. |
| Leadership | An audience on the report, the brief, metrics, and release notes. | The product manager, who then sends the file. |
| Partner | An audience on the report, the brief, and release notes. `pm metrics` stops if you ask for this audience. | The product manager. The brief is preparation, and the file says to keep it internal. |
| Business analyst | No audience. Refinement commands already cover most of the work. Shared state can carry snooze decisions and the inbox to a second person. | Open. See the journey. |
| Developer | No audience. The Daily Scrum, the ready check, and a single ticket already exist as commands. | Open. See the journey. |
| Service designer | No audience. The product-management report already includes changed pages, decisions, and Epics. | Open. See the journey. |

## Role in the config

The choice already has a home. In the settings file it is `audiences.default`:

```yaml
audiences:
  default: pm
```

`pm` is the product manager's full report. `leadership` and `partner` are the other two files. When the line is missing, report, metrics, and release notes use `pm`.

`pm report`, `pm metrics`, and `pm release-notes` read this value when you leave `--audience` off. Someone who always wants the leadership file sets `default: leadership` once, and passes `--audience partner` only for the file that leaves the building.

`pm brief` remembers the depth last used for that meeting name (`--for`). A meeting you have not prepared before still starts at `pm`, even when `audiences.default` is something else.

This setting is the role for the install today. [ROLE_REPORTS_PLAN.md](ROLE_REPORTS_PLAN.md) is the plan for the next step: a `role` value, a detailed report that does not name people, and a personal snapshot that ignores role.

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

Sketched only. The work is real, and most of the commands already exist. They are the refinement afternoon inside the product manager's week. This section is here so we can see whether that afternoon deserves its own page, and whether a second person should run it.

What they need:

- The stories that are not ready: missing title, acceptance criteria, estimate, parent, or dates.
- A draft they can edit before anything is written to Jira.
- The team's ready rules as a pass or fail, in time for Sprint Planning.
- A tray for a request that is not a ticket yet.
- One ticket on screen while they are writing criteria.
- The same snooze decisions as the product manager, when both of them touch the backlog.

A session with today's commands:

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

What this journey does not have:

- An audience flag. The output is a worksheet and a pass or fail, not a narrative for a room.
- A command that starts from "assigned to the analyst". Ready and refine look at the workstream's backlog.

## Developer

Sketched only. "Developer" here means someone on the Scrum team building the product. It is not the "For developers" section of the README, which is about changing pm-tools itself.

What they need:

- The Sprint Goal and what is in the open Sprint.
- What moved since yesterday, and who is on what, in time for the Daily Scrum.
- Whether a story is ready before the team forecasts it.
- One ticket: status, parent, acceptance criteria, link.
- A short account of what shipped, when they are checking a release.

Commands that already serve a piece of that:

1. `pm daily` is the Daily Scrum snapshot: movement, comments in that window, and work in progress. It does not use the model.
2. `pm ready` is the team's working agreement as a pass or fail. The team can run it before planning and ignore the rest of the morning screen.
3. `pm show APS-30` is one ticket.
4. `pm release-notes --since YYYY-MM-DD` is what finished. `--audience leadership` shortens that to Epics. The partner version is the one that strips keys.
5. `pm today` shows the open Sprint for the project: the goal, what needs a decision, what moved, what stalled. The decisions are overdue, blocked, unassigned, and untouched work. That is a portfolio view of the Sprint.

What this journey does not have:

- A "mine" view. The open-Sprint query is the whole project Sprint, not `assignee = currentUser()`.
- A write command that is safe to hand to the whole team. `pm do` and `pm refine --apply` change Jira as the configured user, after a confirmation.
- An audience. A developer reading the leadership report is a reader of a file the product manager already produces.

A developer who installs pm-tools with their own token gets their own mentions inside `pm triage`, because mentions follow the account on that token. The Sprint list on `pm today` is still the whole open Sprint.

## Service designer

Sketched only. This is the person on the team who draws the service end to end: what a person experiences, what staff do, and which systems sit behind that. Journey maps, blueprints, and research live in Confluence beside the backlog.

What they need:

- Which pages that describe the service changed: research, journey maps, blueprints, decisions.
- Which Epics a person using the service would notice.
- Decisions and risks that change the experience.
- One ticket when a story touches a step in the journey.
- The same Sprint window the product manager uses, when they are preparing a review.

What they can run today, with `audiences.default` left as `pm`:

1. `pm report` includes changed Confluence pages, the decision, risk, and ADR registers, and the Epics. That is the layer a design review starts from.
2. `pm report --sprint` is that same file for the open Sprint.
3. `pm brief --for "Design review"` is what changed since the last design review.
4. `pm show APS-30` is one ticket while they are looking at a step in the journey.
5. `pm release-notes --since YYYY-MM-DD` is what finished, when they are checking whether the experience moved.

The plan for this role is in [ROLE_REPORTS_PLAN.md](ROLE_REPORTS_PLAN.md). They share one detailed report with the analyst and the developer, and that file does not name assignees, comment authors, or page editors. The product manager's report is the one that does. A personal snapshot of their own open work ignores role.

## A starting cut

These are proposals. The journeys above stay in this file either way, so a cut is a choice about the guide, not a loss of the notes.

| Journey | Proposal | Why |
|---|---|---|
| Product manager | Keep, and treat it as the spine of the guide. | Every other journey hangs off commands this person runs. [docs/START.md](START.md) is the short form. |
| Leadership | Keep as its own page. | The commands, the file, and the memory already exist. The guide should say which command to run before which meeting. |
| Partner | Keep as its own page. | The labelling step is easy to miss, and the brief is preparation rather than the page you send. Both need a sentence in the guide. |
| Business analyst | Same nameless detailed report as the developer and the service designer. Refinement stays `pm lint`, `pm ready`, and `pm refine`. | The report difference from the product manager is the names. The worksheet is unchanged. |
| Developer | Same nameless detailed report. Daily Scrum, ready, and one ticket stay as they are. | A personal Sprint queue is `pm me`, not a change to `pm today`. |
| Service designer | One shared detailed report with the analyst and the developer, without people's names. | The difference from the product manager is the names, not a separate narrative. See [ROLE_REPORTS_PLAN.md](ROLE_REPORTS_PLAN.md). |
| Role in the config | Add `role`, mapped to a shape. Keep `audiences.default` when `role` is absent. | Missing `role` stays the product manager. `service-designer`, `analyst`, and `developer` use the nameless detailed report. |
| Personal snapshot and summary | Build `pm me`. | A snapshot is where your own open work stands today. A summary is that work over a sprint or a number of days. Neither one follows role. |

If we keep the first three, the guide gains one week for the person who runs pm-tools, one page for the leadership file, and one page for the partner file. The analyst, developer, and service designer share the nameless detailed report in the plan. `pm me` is the personal snapshot and the personal summary.
