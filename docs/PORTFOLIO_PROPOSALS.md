# The next ten features

For a Senior PM with ADHD running a portfolio of several products, and the
Business Analyst who refines the backlog with them.

`docs/FEATURE_PROPOSALS.md` proposed twenty features by reading the code. This
list is different: it starts from the two people using the tool and how their
days actually go, then works back to what to build. Several items from the older
list survive here in a different shape, and the last section says what happened
to each.

Tranche 1 is built: item 1 (products), item 10 (doctor and the cache), and
item 2 (`pm today` / `pm do` as a preview). The rest is still a proposal.
`pm do` does not write to Jira yet.

---

## The two people

**The PM.** Several products, each with its own workstreams, all needing a
status you can defend to directors. ADHD makes specific parts of that job
expensive, and they are not the parts a normal backlog tool optimises:

| The cost | What it looks like on a Thursday |
|----------|----------------------------------|
| Task initiation | You know the backlog needs a pass. You open Jira, see 200 rows, and close it. |
| Working memory | Three tabs, two products, and by the time you find the ticket you came for you have forgotten which product you were reviewing. |
| Context switching | A standup question costs 20 minutes because the thread you were holding is gone. |
| Time blindness | "Certificate rotation" felt like last week. It was due nine days ago. |
| Re-deciding | The same 40 lint warnings every week, each one re-evaluated from scratch. |
| Capture | The best idea of the week happened between meetings and never made it into Jira. |

**The BA.** In Scrum terms a member of the Developers, and in practice the
person who does most of the refinement. They turn intent into refined,
estimable Product Backlog items. Their day is concrete: which items are not
ready, and what exactly is missing. They do not want a report — they want a
queue and a starting draft. Today `pm lint` tells them 40 things are wrong and
leaves them with 40 blank fields to fill.

`pm` currently produces good documents. Neither of these people needs another
document; they need a next action and a shorter list.

---

## The nine rules these ten features follow

1. **One front door.** Nine commands is eight too many to choose between when
   starting is the hard part. `pm today` is the habit; everything else is
   something `pm today` sends you to.
2. **The tool holds the context, not you.** Where you were, what you decided,
   what you already dismissed, when you last briefed this audience.
3. **Every line ends in an action, one keystroke away.** A finding that only
   describes a problem is homework. A finding with `pm do 3` next to it is done.
4. **Bounded by default.** Top few, never a wall. A capped list gets read; a
   complete list gets closed.
5. **No blank pages.** The model drafts, the human edits. Editing a wrong draft
   is enormously cheaper than starting from nothing.
6. **Decisions stick.** Say "not now" once and it stays said, with your reason
   attached, until the date you chose.
7. **Deterministic first.** Rules do the judging; Qwen3.8 Q3_K_M only drafts
   prose, in small batches, and never decides what is true.
8. **Nothing reaches Jira without a preview and one confirmation.** Every write
   is a diff you approved.
9. **Products and workstreams stay one command to add or remove, and there is
   still no JQL.** The two constraints from the last round hold for all of this.

---

## The ten

### 1. Products above workstreams — the portfolio layer

**Pain.** The model is one project and a flat list of workstreams. A portfolio
is products first, workstreams within them, and some products live in their own
Jira project. Right now three workstreams from three different products roll up
into one undifferentiated report, and there is no way to ask "how is Billing?"

**What it does.** Adds a product tag to each workstream and a `products:` block
for the names and per-product defaults. The workstream list stays flat, so
`pm workstreams add` and `remove` keep working exactly as they do.

```yaml
products:
  - name: "Data Exchange"
    abbrev: "DX"
    project: "APS"
  - name: "Billing Platform"
    abbrev: "BILL"
    project: "BILL"          # its own Jira project
    scopes:
      report: {sprint: any, status: open}   # this one does not use sprints

workstreams:
  - name: "Secure Data Exchange"
    abbrev: "SDX"
    product: "DX"
    components: ["Secure Data Exchange"]
```

```
pm products                     # list, with workstream counts
pm products add --name "Billing Platform" --abbrev BILL --project BILL
pm products check               # the same verification pm workstreams check does
pm lint --product BILL          # everything takes --product, -w still works
```

Reports gain a portfolio summary, then a section per product, then per
workstream. A workstream with no `product:` lands in an implicit "Unassigned"
product, so today's config keeps working untouched.

**Serves** both. **Touches** `core/workstreams.py`, `core/config.py`, a new
`commands/products.py` mirroring the workstreams one, and the header of each
report. Contained, because membership resolution is already a single function.
**Depends on** nothing. Everything else here depends on it.

**Success signal.** `pm lint --product BILL` returns only Billing work, and a
new product is three lines plus one `pm products check`.

---

### 2. `pm today` — the one command

**Pain.** Rule 1. Choosing between `standup`, `lint`, `ready` and `report`
is a decision tax on the hardest moment of the day, and none of them answers
"what should I do in the next ten minutes?"

**What it does.** One bounded screen across the whole portfolio, in the same
shape every day, with a numbered action list.

```
$ pm today
Thursday 3 September · 3 products · 41 open items

NEEDS YOU (3)
  1  BILL-88  Invoice export fails for EU tenants      bug, unassigned, 4 days in sprint
     → pm do 1     assign to yourself and reply to C. Diaz
  2  APS-30   Rotate exchange signing certificates     due 9 days ago, not started
     → pm do 2     set a realistic due date (suggests 17 Sep)
  3  APS-50   Expose exchange metrics on the gateway   blocked by APS-12 for 6 days
     → pm do 3     ask B. Ray for an ETA

MOVED SINCE YESTERDAY (2)
  APS-10   To Do → In Review by A. Lee (09:12)
  BILL-71  In Review → Done by C. Diaz (16:40)

AGING (1)
  APS-11   In Progress 19 days, untouched 12 — longest in Data Exchange

WITH THE BA (4 of 10 refined)
  SDX  4 tickets still fail Definition of Ready       pm refine -w SDX

3 findings snoozed until 14 Sep.
```

`pm do N` performs the offered action after showing exactly what it will send.
The numbering is written to `~/.pm/today.json`, so the numbers still mean what
they meant when you walked away from the terminal.

**Serves** the PM, mainly. **Touches** a new command that composes existing
fetches, plus the cache from item 10 — this has to come back in under about ten
seconds warm or the habit will not form. **Depends on** 1 and 10, and gets
better with 4, 5 and 6.

**Success signal.** It is the only command you type on a normal day, and the
`NEEDS YOU` list is short enough to actually clear.

---

### 3. `pm capture` and `pm inbox` — three seconds to get it out of your head

**Pain.** Ideas and commitments arrive between meetings, when opening Jira and
choosing a project, type, epic and title is nine decisions too many. So they go
into a notebook, or nowhere.

**What it does.** Splits capture from filing. Capture is instant and offline;
filing happens later, in one batch, from drafts.

```
$ pm note "customer wants an SSO audit export in billing"
Captured #7. Nothing else needed now.

$ pm note -w SDX "check whether cert rotation needs a comms plan"
Captured #8 against SDX.

$ pm inbox
#7  "customer wants an SSO audit export in billing"        Tue 14:02
    suggests   Billing Platform · Story
    title      Export the SSO audit log for tenant admins
    criteria   Given a tenant admin, when they request an audit export,
               then a CSV of sign-in events for the period is emailed to them.
    → pm inbox create 7    pm inbox edit 7    pm inbox drop 7

#8  "check whether cert rotation needs a comms plan"       Wed 08:15
    suggests   Data Exchange · SDX · Task, under APS-3
    → pm inbox create 8    pm inbox edit 8    pm inbox drop 8
```

The suggestion is the model's only job here, and a wrong guess costs one edit.
Nothing is created in Jira until `create`, which shows the payload first.

**Serves** the PM to capture, the BA to file. **Touches** a new command, a local
inbox file, `create_issue` in `core/sources.py`, and one small drafting prompt.
**Depends on** 1 for the product guess.

**Success signal.** A week goes by with nothing important living only in your
head or a notebook.

---

### 4. `pm triage` — the queue of things waiting on a decision from you

**Pain.** `pm standup` reports movement. Nothing reports the absence of
movement caused by you: the unassigned bug, the blocked story waiting on a
nudge, the comment that asked you a question on Monday.

**What it does.** A deterministic queue of "waiting on me", grouped by product,
each entry with the action that clears it.

```yaml
triage:
  unassigned_in_sprint: true
  blocked: true                   # flagged, Blocked status, or a blocked-by link
  mentions_me_within_days: 3      # comments that named you
  new_bugs_within_days: 1
  in_sprint_untouched_days: 3
  overdue: true
```

```
pm triage                         # the whole portfolio
pm triage --product BILL
pm triage --apply 2               # do the offered action, after a preview
```

**Serves** the PM. **Touches** a new command plus two fetches (issue links and
comments) in `core/sources.py`, and the write path shared with `pm do`. All
deterministic — no model. **Depends on** 1; shares the action mechanism with 2.

**Success signal.** Nothing sits blocked for a week because it was invisible.

---

### 5. `pm refine` — the BA's queue, with drafts instead of blank fields

**Pain.** `pm lint` and `pm review` hand the BA a list of 40 problems. Every one
of them starts as an empty field. This is the single biggest time sink in the
BA's week, and the place a local model earns its keep.

**What it does.** Turns the Definition-of-Ready gap list into an editable
worksheet with a draft for every gap, then writes back only what the BA kept.

```
$ pm refine -w SDX
6 tickets fail Definition of Ready. Drafts in refine_SDX_2026-09-03.md

  APS-11  vague title       → "Fix retry handling in the exchange client"
  APS-20  no criteria       → 3 criteria drafted
  APS-20  no estimate       → 3 points (median of 5 similar SDX stories)
  APS-31  no criteria       → 2 criteria drafted
  ...

Edit the file, delete anything you disagree with, then:
  pm refine --apply -w SDX         # shows a diff, asks once, writes to Jira
```

The estimate suggestion is deterministic — the median of closed, similar
tickets in the same workstream — not a guess from the model. Titles and
criteria are model drafts in the batches of eight that Qwen3.8 Q3_K_M handles
reliably.

**Serves** the BA above all, and the PM by making `pm ready` go green without a
meeting. **Touches** a new command over `commands/lint.py`, `commands/review.py`
and `commands/ready.py`, plus `update_issue`. The largest item here, and the
one with the highest payoff per hour of the BA's week. **Depends on** 1;
strongly paired with 6.

**A naming consequence worth deciding.** `pm refine` and `pm review` would sit
next to each other doing nearly the same thing — `review` reports the model's
opinion on titles and criteria, `refine` acts on it. Two commands that start
with `re` and overlap in purpose is exactly the choice-tax rule 1 exists to
remove. I would let `pm refine` absorb `pm review`, keeping `pm review` as a
deprecated alias for one release, so the vocabulary matches how the team
actually talks about the work: lint finds it, refine fixes it, ready gates it.

**Success signal.** Percent-ready climbs week over week without a refinement
session, and the BA's edits are mostly deletions rather than rewrites.

---

### 6. Findings that remember your decision

**Pain.** Rule 6, and the quiet reason backlog tools get abandoned. Every run
re-reports what you already considered and consciously let go, so every run
costs the same decisions again — plus a little guilt. For ADHD this is the
difference between a tool you open and one you avoid.

**What it does.** Gives every finding three verbs, each with a reason and an
expiry, and shrinks the reports to what is genuinely new.

```
pm lint --snooze APS-11 --until next-sprint --why "cosmetic, agreed with A. Lee"
pm lint --accept APS-40 --why "standalone spike, no parent by design"
pm lint --assign APS-20 --to dana
pm lint
  4 new findings · 11 hidden (3 snoozed, 2 accepted, 6 assigned)
  pm lint --all      to see everything again
```

`--assign --to <person>` is how a finding moves to whoever will refine it: it
lands in that person's `pm refine` queue and is tracked until it closes, so it
stops being re-reported and re-discovered. Deliberately a person rather than a
role — encoding a PM-to-BA pipeline would build the stage gate that the
Definition-of-Ready critique in `docs/TERMINOLOGY.md` warns about, and
refinement is a Scrum Team activity.

**Where the memory lives** is the one real design question, and it needs your
answer before this is built:

| Option | Shared with the BA | Cost |
|--------|--------------------|------|
| Local file in `~/.pm` | No | Simplest; two people drift apart |
| A shared file (OneDrive / SharePoint) | Yes | One path in config; needs the folder to sync |
| Jira labels and comments | Yes, and visible to everyone | Pollutes the backlog; needs write scope |

My recommendation: local by default, with `state.shared_path` for the PM/BA
pair, and Jira mirroring only for `--assign`, where the assignee genuinely
should see it in Jira.

**Serves** both. **Touches** a small `core/decisions.py` plus a filter in each
reporting command. Contained, and it makes items 2, 4 and 5 quieter every week
they are used.

**Success signal.** Report length falls week over week while the backlog
improves, and no finding is decided twice.

---

### 7. `pm brief` — meeting prep, and the debrief

**Pain.** Prep happens in the ten minutes before the meeting, from memory,
across several products. Afterwards the decisions live in your head until they
evaporate. Both halves are working-memory problems, and both are the kind of
recurring obligation ADHD punishes hardest.

**What it does.** One page per audience, with memory of the last time you met
*that* audience — which is not the same as last week.

```
pm brief --for "Monthly portfolio review"     # per-product status, decisions needed, risks
pm brief --for standup --product DX
pm brief --debrief notes.md                   # your scribbles → decisions and actions
```

The prep page is bounded: per product, what changed since that audience last
saw it, the two or three decisions you need from them, and the risks worth
their attention. The debrief turns rough notes into a decision list, an action
list with owners, and — with your approval — the Jira tickets for the actions.

**Serves** the PM, with the BA taking the actions. **Touches** a new command, a
per-audience state file reusing `core/state.py`, and one drafting prompt.
**Depends on** 1, and reads better with 8.

**Success signal.** Prep is reading one page, and no decision from a meeting is
lost by Friday.

---

### 8. `pm metrics` — portfolio health, and an antidote to time blindness

**Pain.** "Is Billing slipping?" currently has a vibes-based answer. And the
specific ADHD failure — a thing that feels like last week was three weeks ago —
needs numbers, not memory.

**What it does.** Deterministic delivery metrics per product and workstream,
from the changelog the standup already fetches.

- throughput: items reaching Done per week
- cycle time: first In Progress to Done, median and 85th percentile
- aging work in progress: how long each in-flight item has been in flight
- sprint scope change: what was added after the Sprint started
- forecast accuracy: what the Developers forecast versus what was Done
- a plain forecast: at the current rate, the open SDX work lands around 12 Oct

```
pm metrics --weeks 8
pm metrics --product BILL --json
```

**Serves** the PM, and directors indirectly. **Touches** a new command and a
changelog helper. No model. **Depends on** 1.

**Success signal.** The weekly report cites numbers with trends, and a slipping
product is visible before someone else notices it.

---

### 9. `pm publish` and `pm schedule` — obligations that do not need remembering

**Pain.** A Markdown file on a laptop is not a status update, and "send the
weekly report" is exactly the recurring, low-novelty task that gets dropped.

**What it does.** Publishes where people already read, and registers itself with
Windows Task Scheduler so it happens whether or not you remember.

```yaml
publish:
  confluence: {space: "APS", parent_page: "Weekly Reports"}
  teams_webhook: "${ENV:PM_TEAMS_WEBHOOK}"
```

```
pm report --product DX --publish
pm schedule add today --at 08:30          # pm today, every weekday morning
pm schedule add report --weekly fri@16:00
pm schedule list
```

Publishing is a write path, so `--dry-run` is the default until confirmed.
Scheduling only registers commands that are safe unattended — the read-only
ones. Nothing that writes to Jira ever runs on a timer.

**Serves** both. **Touches** a new command, a Confluence and webhook writer, and
a small PowerShell shim for Task Scheduler. **Depends on** 1; better after 8.

**Success signal.** The weekly update goes out without you thinking about it,
and `pm today` is waiting for you when you sit down.

---

### 10. `pm doctor` — the floor

**Pain.** A tool that fails obscurely on a Tuesday does not get a second
chance, and a wrong custom-field ID makes `no-estimate` silently pass on every
ticket — a report that is confidently wrong.

**What it does.** Verifies everything in one command, and fixes what it can.

```
pm doctor
  config          ~/.pm/config.yaml — 2 products, 4 workstreams        ok
  jira            connected as Dana Stainton                          ok
  projects        APS ok · BILL ok
  custom fields   story points customfield_10016                      ok
                  start date                                          MISSING
  membership      DX 18 items · BILL 12 · unclaimed 3                 warn
  model           qwen-local answered in 1.9s, thinking off           ok
  cache           ~/.pm/cache, 41 entries, warm                       ok

pm doctor --discover-fields      # find the field IDs and offer to write them
```

Shipped alongside it, because item 2 cannot be fast without it: a fetch cache
(`~/.pm/cache`, TTL in config, `--cached` and `--refresh`) which also makes
repeated `pm lint` runs instant and lets the tool work on a plane.

**Serves** both. **Touches** a new command reusing `commands/workstreams.py`
checks, plus `core/cache.py` and one decorator in `core/sources.py`. Low risk.
**Depends on** 1.

**Success signal.** A broken setup names its own fix, and `pm today` returns in
seconds.

---

## Cross-cutting decisions to make before building

These affect several items, so they are worth settling first.

1. **Jira write scope.** Items 3, 4, 5, 6 and 7 create or edit issues. Does the
   API token have write permission, and are you comfortable with the tool using
   it? Every write would be preview-then-confirm, logged to
   `~/.pm/write-log.jsonl`, with `--dry-run` available everywhere and nothing
   writing on a schedule.
2. **Where shared state lives.** See the table in item 6. This decides whether
   the PM/BA handoff works at all.
3. **Product to project mapping.** Are your products separate Jira projects,
   components within one project, or a mix? Item 1's shape is the same either
   way, but `pm products check` needs to know what to verify.
4. **Does the BA run `pm`, or receive its output?** If they run it, item 5 is a
   command on their machine and item 6 needs shared state. If they receive
   output, item 5 produces a file you send them and the loop closes more slowly.
5. **Teams or Confluence for item 9**, and whether a webhook is available
   without a ticket to IT.

## Suggested order

**First — the foundation and the daily habit.** Item 1 (products), item 10
(doctor and the cache), then item 2 (`pm today`). After this tranche there is
one command to type and it is fast.

**Second — the two work queues.** Item 6 (decisions stick), item 4 (`pm triage`),
item 5 (`pm refine`), item 3 (capture). Item 6 first, because it is what keeps
the other three from becoming noise. This tranche is where the BA's week
changes.

**Third — outward facing.** Item 8 (metrics), item 7 (brief), item 9 (publish
and schedule). These are what directors see, and they read better once there
are numbers behind them.

## What happened to the earlier twenty

| Earlier proposal | Now |
|------------------|-----|
| 1 `pm doctor`, 2 field discovery | Item 10, merged |
| 6 cache | Item 10, shipped with it |
| 7 `pm triage` | Item 4, with actions attached |
| 8 `pm metrics` | Item 8, per product, plus a forecast |
| 12 `pm publish` | Item 9, plus scheduling |
| 13 write-back | Absorbed into items 3, 4, 5 as preview-then-confirm |
| 15 multi-project membership | Absorbed into item 1 |
| 9 risk/decision register | Folded into item 7's brief; standalone `pm risks` deferred |
| 3 `pm coverage` | Deferred, but item 10 now reports unclaimed work |
| 4 output paths, 5 exit codes | Small; ride along with items 2 and 9 |
| 10 duplicates, 11 release notes, 14 sprint review | Still worth doing, below these ten |
| 16 deeper hierarchies, 17 concurrency, 18 CI, 19 keyring, 20 model resilience | Unchanged, still below the line — though CI gets more valuable with every item above |

## A note on vocabulary

The team says **refinement**, not grooming, so the tool should too: item 5 is
`pm refine`, its output is `refine_<workstream>_<date>.md`, and the label item
13 of the earlier list would apply is `needs-refinement`.

That rename prompted a full audit against the November 2020 Scrum Guide, which
is now `docs/TERMINOLOGY.md`. It changes three things about this list:

- Item 6 assigns findings to a **person**, not to a role, because a PM-to-BA
  pipeline is the stage gate Scrum warns against.
- The Sprint Goal, the Definition of Done and the Product Goal are all missing
  from the tool entirely. The Sprint Goal in particular belongs at the top of
  item 2's screen — a daily snapshot that never says whether the Sprint Goal is
  at risk is a status report, not a Scrum artifact.
- `pm ready` rests on a Definition of Ready, which is **not** part of Scrum. The
  capability stays; the framing becomes a team working agreement, and the one
  criterion Scrum does imply — can this be Done inside one Sprint — becomes the
  one that always blocks.

These sit alongside the ten rather than replacing any of them, and the Sprint
Goal is cheap enough that it should ride along with item 2.

## What I would not build

- **A GUI or a web dashboard.** The value here is a terminal habit that starts
  in one second. A dashboard is another place to have to go and look.
- **Anything that writes to Jira unattended.** Scheduled runs stay read-only.
- **Model-generated status claims.** The model drafts language; rules decide
  what is true. Q3_K_M is good at the former and should never be trusted with
  the latter.
