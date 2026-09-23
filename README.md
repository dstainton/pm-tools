# pm-tools (`pm`)

A command-line tool that helps a PM stay on top of a backlog and keep
stakeholders informed. One config, several commands, all running against your
own Jira / Confluence / SharePoint and a **local** model — nothing leaves
your laptop.

```
pm init         Create a starter config at ~/.pm/config.yaml
pm products     List, add, remove or check your products
pm workstreams  List, add, remove or check your workstreams
pm today        One bounded daily screen (the habit command)
pm do N         Preview, then write, the numbered action from `pm today`
pm doctor       Verify config, Jira, fields, model, cache
pm report       Weekly state-of-product report (uses the local model)
pm lint         Deterministic Product Backlog checks (no model — pure rules)
pm triage       Queue of things waiting on a decision from you
pm refine       BA queue: draft titles, criteria and estimates
pm review       Without --apply, the old model judgement; with --apply, refine (deprecated)
pm note         Capture a thought offline; file it later
pm coverage     Open issues no workstream claims, plus overlaps and unused components
pm inbox        List, edit, create or drop captured notes
pm metrics      Delivery numbers per product and workstream (no model)
pm release-notes  Done issues since a date or in a fixVersion
pm brief        Meeting prep for one audience, or a debrief
pm publish      Send a Markdown file to Confluence and/or Teams
pm schedule     Register read-only commands on a timer
pm ready        Team working agreement: pass/fail per ticket
pm daily        Daily Scrum movement + work in progress (no model)
pm update       Upgrade pm-tools and migrate the config (never replaces it)
```

Every command except `init` and `update` can be scoped with `--product`
and `--workstream`. Each accepts an abbreviation or the full name,
comma-separated and case-insensitive. The two compose. `--cached` reuses a
stale fetch cache; `--refresh` ignores it. `--out DIR` writes that run's
files under DIR instead of `output.directory` (default `~/.pm/out`).

---

## Quick start

Python 3.9 or newer. You do not clone the repo.

On Windows, from PowerShell:

```powershell
irm https://raw.githubusercontent.com/dstainton/pm-tools/main/install.ps1 | iex
```

On macOS or Linux:

```bash
pipx install git+https://github.com/dstainton/pm-tools.git
pm init
```

`pm init` copies a template to `~/.pm/config.yaml` and stops. Open that file
and fill in the Jira URL, email, API token, project, and your products and
workstreams. Then:

```text
pm doctor
pm today
```

`pm doctor` checks what you typed and does not rewrite the file. `pm today`
is the habit command, from any directory.

You also need a local OpenAI-compatible model server for `pm report`,
`pm refine`, and `pm ready --deep` — see **The local model** below.
`pm today`, `pm lint`, `pm triage`, `pm daily`, `pm doctor`, `pm note`,
`pm coverage`, `pm metrics`, and the fast `pm ready` need no model at all.
`pm release-notes` prints the issue list either way, and drafts prose only
when the model is up.

A later upgrade is `pm update`. It upgrades the program and adds new config
keys. It does not replace `~/.pm/config.yaml`. `pm init --force` is the only
command that replaces that file.

Developing pm-tools itself is a separate path: `pip install -e .` inside a
clone. An editable install does not get `pm update`'s code upgrade; pull
the repository yourself.

---

## Installing as a real command

`pipx` reads `pyproject.toml` and installs two commands that call the same
program:

```toml
[project.scripts]
pm = "pm:main"
pm-tools = "pm:main"
```

Remove it with `pipx uninstall pm-tools`. An older checkout of this repo may
still be installed under the name `pm-helper`; uninstall that with
`pip uninstall pm-helper` if `pm` points at it.

### Optional: a standalone .exe (no Python needed)

To hand `pm` to a teammate who doesn't have Python:

```
pip install pyinstaller
pyinstaller --onefile --name pm pm.py
```

The result is `dist/pm.exe`. Heavier and rebuilt on every code change, so it's
for sharing, not day-to-day dev. For yourself, the editable install is better.

---

## Config: where pm looks, and `pm init`

Because `pm` runs from any folder, it can't assume `config.yaml` is beside you.
It searches, in order, and uses the first it finds:

1. `--config /path/to/config.yaml` if you pass it
2. the `PM_CONFIG` environment variable
3. `config.yaml` in the current folder
4. `~/.pm/config.yaml`  ← the tidy home for it
5. the `config.yaml` shipped next to `pm.py` (the fallback)

**`pm init` sets up option 4 for you** — it copies the bundled template to
`~/.pm/config.yaml` so `pm` finds it automatically from then on:

```
pm init                 # create ~/.pm/config.yaml (won't overwrite)
pm init --force         # replace an existing one
pm init --path FILE     # write somewhere specific instead
```

After `pm init`, open the file and fill in the `<PLACEHOLDERS>`. If the file
already exists, `pm init` leaves it alone. `pm update` upgrades the program
and adds new settings. It does not replace the file. `pm init --force` is
the only command that does.

- **Jira / Confluence:** your Atlassian email and an API token from
  `id.atlassian.com → Security → API tokens`.
- **Jira project:** `jira.project` — the one project holding the work.
- **Custom field IDs:** story points, start date, epic link — see
  **Finding your custom field IDs** below.
- **SharePoint:** leave `enabled: false` until an admin sets up an Azure app.
- **Workstreams:** SDX, APS, ITK are pre-filled; each one is a name, an
  abbreviation and its Jira Component(s). No queries to write.

> **Keeping secrets out of the file:** any value can be written as
> `${ENV:VAR_NAME}` and pm will read it from that environment variable at run
> time. Handy for the API token.

The report's `report_state.json` (the "what changed" memory) is written under
`output.directory` (default `~/.pm/out`), so it stays in one place no matter
which folder you run `pm report` from.

---

## The local model

Only needed for `pm report`, `pm refine`, `pm review` (without `--apply`),
`pm ready --deep`, the filing suggestion in `pm inbox`, and the prose draft
in `pm release-notes`. The issue list in `pm release-notes` is chosen
without the model.

The default config expects a local OpenAI-compatible endpoint at:

```text
http://127.0.0.1:8080/v1/chat/completions
```

and uses the model alias `qwen-local`.

On the Windows Ryzen AI laptop, the bundled PowerShell scripts set up
`llama.cpp` and keep the server bound to localhost:

```powershell
# Small tether-friendly model, about 2.5 GB:
.\setup-windows-qwen-small.ps1
.\setup-windows-qwen-small.ps1 -StartServer

# The model the prompts are written for — Qwen3.8-27B Q3_K_M, about 13.5 GB:
.\setup-windows-qwen-large.ps1
.\setup-windows-qwen-large.ps1 -StartServer
```

Both scripts expose the model as `qwen-local` and start llama.cpp with thinking
**off** (`--reasoning-budget 0`). Qwen3.8 thinks by default; a Q3_K_M run that
is allowed to think will spend its token budget inside `<think>` and give
`pm refine` or `pm review` empty or half-cut JSON. `pm` also sends
`chat_template_kwargs.enable_thinking: false` and a `/no_think` prefix on every
call, so a server started by hand still behaves.

The prompts themselves are short, numbered, and end with a fill-in skeleton or a
worked JSON example — the shape Qwen3.8 Q3_K_M follows. Sampling matches Qwen's
instruct profile (temperature 0.4, `top_p` 0.8, `top_k` 20, `presence_penalty`
1.5), with a cooler `json_temperature` of 0.2 for `pm refine`, `pm review`,
and `pm ready --deep`.

Other OpenAI-compatible local servers can still be used by changing
`model.endpoint` and `model.name`. If you turn thinking back on, set
`model.enable_thinking: true` so `pm` stops sending `/no_think`.

---

## Scoping — `--product` and `--workstream`

Every command runs the whole portfolio by default. Narrow it with `--product`
(`-p`) and/or `--workstream` (`-w`). Both take comma-separated abbreviations
or full names, case-insensitive, and a typo fails with the list of valid
abbreviations.

```
pm lint   --product IP                         # every workstream in Integration Platform
pm lint   --workstream SDX                     # just Secure Data Exchange
pm lint   --workstream "Secure Data Exchange"  # the same stream, by full name
pm ready  -p IP -w sdx,itk                     # two streams inside that product
pm report --product IP                         # one stakeholder snapshot
```

Scoping `pm report` is safe: it updates only the selected workstream's
"what changed" memory.

---

## Products — `pm products`

A Jira project is the team. Components name products and workstreams. A
product sits above workstreams as a name and abbreviation; it does not need
its own Jira project. The workstream list stays flat; each workstream points
at a product with `product: <abbrev>`. A workstream with no product lands in
Unassigned.

```yaml
products:
  - name: "Integration Platform"
    abbrev: "IP"
    project: "APS"

workstreams:
  - name: "Secure Data Exchange"
    abbrev: "SDX"
    product: "IP"
    components: ["Secure Data Exchange"]
```

```
pm products
pm products add --name "Billing Platform" --abbrev BILL --goal "Invoices go out the day the work is done"
pm products remove BILL
pm products check
```

`add` / `remove` edit the config in place, comments and all. You cannot remove
a product that workstreams still name. `pm products check` verifies each
workstream's components exist in the team project (`jira.project`). A product
may set `project:` only when it really lives outside that team project, and
may set `scopes:`; workstreams inherit those unless they override.
`product_goal:` is optional. `pm report` and `pm brief` print that sentence
once under the product heading, and omit it when it is empty.

---

## The daily habit — `pm today` and `pm do`

```
pm today                  # one bounded screen across the portfolio
pm today --product IP
pm do 1 --dry-run         # preview the action numbered this morning
pm do 1                   # confirm once, then write
```

The screen is the same shape every day: Sprint Goal (when Jira's Agile API
exposes one), and under it a line when the sprint has an end date —
"Sprint ends in N days. Not started: K. Blocked: M." That line does not
name an issue or claim one is on the goal path. Then NEEDS YOU, movement
since yesterday, aging in-progress work, and refinement gaps against the
team's ready agreement. Numbered actions are
written to `~/.pm/today.json` so the numbers still mean what they meant when
you walked away.

`pm do N` prints the exact payload, asks once (`--yes` skips the prompt,
`--dry-run` stops after the preview), writes to Jira, and appends a line to
`~/.pm/write-log.jsonl`. Non-interactive runs must pass `--yes` or `--dry-run`.

---

## `pm doctor` and the fetch cache

```
pm doctor
pm doctor --discover-fields
pm doctor --discover-fields --yes
```

One command that names its own fix: config, Jira login, projects, custom-field
IDs, membership (including unclaimed open work), the local model, and the
cache. `--discover-fields` prints a YAML snippet and does not write the
file. `pm doctor --discover-fields --yes` fills `story_points_field`,
`start_date_field`, and `acceptance_criteria_field` only when those values
are blank. It leaves a value you already set, and it does not write
`epic_link_field`.

Repeated fetches are cached under `~/.pm/cache` for five minutes. `pm today`
depends on this to stay fast. `--cached` reuses a hit even if it is stale
(a plane / offline run); `--refresh` talks to Jira again.

---

## Workstreams — `pm workstreams`

A workstream is three lines of config. No JQL, anywhere:

```yaml
- name: "Secure Data Exchange"
  abbrev: "SDX"
  components: ["Secure Data Exchange"]
```

`components` are exact Jira **Component** names, and `jira.project` says which
project to look in (a workstream can override it with its own `project:`).
A workstream can list several Components, and optionally say where its documents
live (`confluence_space`, `confluence_labels`, `sharepoint_query`).

### Adding and removing one

```
pm workstreams                       # what's configured right now
pm workstreams add --name "Billing Platform" --abbrev BIL \
                   --components "Billing Platform"
pm workstreams remove BIL
pm workstreams check                 # does Jira agree with all of this?
pm workstreams check --show-jql      # ...and here are the queries it built
```

`add` and `remove` edit your config file in place, leaving every comment and
every other setting exactly where it was, and refuse to write a file that
wouldn't load. `check` is the one to run after any edit: it confirms the
Component names exist in the project (and suggests close matches when they
don't), counts the epics and directly tagged issues that carry them, and shows
roughly how much work each command would see.

```text
Secure Data Exchange (SDX)
  project: APS
  components: Secure Data Exchange
  epics carrying the component: 4
  issues tagged directly: 1
  report (sprint work): ~11 issue(s)
  roadmap (the epics): ~4 issue(s)
  ...
```

### How membership is decided

The Jira model this assumes is the common one: one project, Epics carrying the
Component that names the workstream, and children that often carry nothing.

```text
APS project
  -> Epic  — carries the Component
       -> Story / Task / Bug  — Component optional
            -> Sub-task       — Component optional
```

So an issue belongs to a workstream when **either**:

1. **it carries one of the workstream's Components itself** — any issue type, at
   any level, including work that hangs off an Epic belonging to nobody or has
   no parent at all; or
2. **it sits under something that does** — anything beneath a workstream Epic
   (Stories, Tasks, Bugs and their nested Sub-tasks), and the Sub-tasks of a
   directly tagged Story or Task.

Both rules are resolved from Jira on each run, with the discovery queries cached
for the duration of the command. Because child work inherits, `pm lint` and
`pm ready` never ask a Story for a Component it doesn't need.

Two knobs, under `membership:`:

| Setting | Default | What it does |
|---------|---------|--------------|
| `epic_types` | `[Epic]` | Issue type(s) that act as the workstream anchor |
| `inherit_from_parent` | `true` | Rule 2 above; set `false` for Components only |
| `child_component_wins` | `false` | When `true`, a child naming its own Component is judged on that alone instead of also counting under its parent's workstream |
| `max_parent_keys` | `500` | Safety valve on how many directly tagged issues get their sub-tasks expanded |

`child_component_wins: false` means a Story tagged `API Platform` under a
`Secure Data Exchange` Epic shows up in **both** — deliberately, so mis-tagged
work is visible somewhere rather than nowhere. Flip it to `true` if you'd rather
the child's own Component be the last word.

### What each command looks at — `scopes:`

Membership says *which work is ours*; a scope says *which of it this command
cares about*. Scopes are plain options, and `pm` writes the query:

```yaml
scopes:
  report:        {sprint: open}
  roadmap:       {status: open}
  lint:          {status: open}
  ready:         {sprint: open, status: open}
  daily_moved:   {updated_within_days: 1}
  daily_wip:     {status: in-progress}
```

| Option | Values |
|--------|--------|
| `status` | `any`, `open`, `done`, `in-progress`, `todo` |
| `sprint` | `any`, `open`, `future`, `none` |
| `assignee` | `any`, `me`, `unassigned`, `assigned` |
| `types` / `exclude_types` | issue type names |
| `labels_any` / `labels_none` | label names |
| `updated_within_days`, `created_within_days`, `due_within_days` | whole days |
| `extra_jql` | escape hatch, if you ever need one |

Each scope also picks the level it applies to, which is fixed: `report`, `ready`
and the daily scopes look at child work, `roadmap` at the workstream Epics,
`lint` and `review` at the Epics plus everything beneath them.

Any workstream can override any scope with its own `scopes:` block — useful when
one stream doesn't use sprints:

```yaml
- name: "Integration Toolkit"
  abbrev: "ITK"
  components: ["Integration Toolkit"]
  scopes:
    report: {sprint: any, status: open}
```

A typo is caught when the config loads, with the valid choices listed, rather
than becoming a confusing Jira error mid-run.

**Backward compatibility:** older configs still work unchanged. A workstream
with no `components:` stays in legacy mode, where each `*_jql` value is a
complete query; `jira_project` and `epic_components` are still read as aliases,
and any `*_jql` value on a Component-based workstream is applied as an extra
filter.

---

## The commands

### `pm workstreams` — the setup itself

Covered in **Workstreams** above: `list` (the default), `add`, `remove`, and
`check` for confirming Jira agrees with your config. `check` exits non-zero when
something is wrong, so it also works as a smoke test in a scheduled job.

### `pm report` — weekly state-of-product report

Gathers in-sprint work, roadmap, decisions, risks and dependencies per
workstream, works out **what changed since last week**, and asks the local model
to write a concise section. Ends with a reference table of real links. Output:
`weekly_report_<date>.md`. Remembers last week in `report_state.json` — keep
that file between runs.

### `pm lint` — Product Backlog checks

**No model. Pure rules**, so you can trust every finding and run it before every
sprint planning.

| Check | Severity | What it catches |
|-------|----------|-----------------|
| `bad-dates` | 🔴 error | Due before start, or due date passed but not done |
| `missing-component` | 🟠 warn | No component set, in a legacy workstream that can't inherit one |
| `missing-parent` | 🟠 warn | Story/task not linked to a parent |
| `missing-acceptance-criteria` | 🟠 warn | No AC found on a story/bug |
| `no-estimate` | 🟠 warn | In-scope story with no story points |
| `stale` | 🟠 warn | "In Progress" but untouched for *N* days |
| `vague-title` | 🔵 review | Title too short or full of vague words |

Output: `lint_report_<date>.md`. Flags: `--severity error` (only hard problems),
`--json` (machine-readable). Every threshold lives in the `lint:` config block.

Decisions stick, so the same finding is not re-decided every week:

```
pm lint --snooze APS-11 --until next-sprint --why "cosmetic, agreed with A. Lee"
pm lint --accept APS-40 --why "standalone spike, no parent by design"
pm lint --assign APS-20 --to dana --why "Dana will refine the AC"
pm lint --all
```

`--assign --to` takes a person, not a role. It hides the finding from the
default lint, lands it in that person's `pm refine` queue, and writes the
Jira assignee after a preview. Memory lives in `state.shared_path` (a synced
folder) when that is set, otherwise `~/.pm`.

> **Lint vs. refine.** `pm lint` uses cheap, reliable heuristics that never cry
> wolf. `pm refine` drafts the missing title, criteria and estimate so the BA
> edits instead of starting from a blank field.

### `pm triage` — waiting on you

Deterministic. No model. Grouped by product, each line with the action that
clears it.

```
pm triage
pm triage --product IP
pm triage --apply 2 --dry-run
pm triage --apply 2 --yes
```

What counts is in the `triage:` block: unassigned in the Sprint, blocked
(status, label, or a blocked-by link), comments that named you, new bugs,
in-sprint items untouched for N days, and overdue work.

### `pm refine` — the BA's queue

Lint finds the gaps. This command drafts a title, acceptance criteria and an
estimate for each one, writes an editable worksheet, and `--apply` sends back
only the fields you left in the file. A deleted field is not written. The
estimate is the median of closed similar stories in the same workstream, not
a model guess.

```
pm refine -w SDX
# edit refine_SDX_<date>.md
pm refine --apply -w SDX
```

`pm review` is deprecated. Without `--apply` it still runs the old judgement
reports. With `--apply` it writes the refine worksheet.

### `pm note` / `pm inbox` — capture now, file later

```
pm note "customer wants an SSO audit export"
pm note -w SDX "check whether cert rotation needs a comms plan"
pm inbox
pm inbox edit 1 --title "Export the SSO audit log" --criteria "Given an admin, when they export, then the file lists every login."
pm inbox create 1
pm inbox drop 1
```

Capture is instant and offline. `pm inbox edit` corrects the title,
workstream, or acceptance criteria in `inbox.json` before create. A stored
edit wins over the model suggestion. Filing still previews the Jira create.

### `pm metrics` — portfolio health

**No model.** Throughput, cycle time (median and 85th percentile), aging work
in progress, sprint scope change, forecast accuracy (points Done vs forecast),
and a plain landing date at the current weekly rate. `pm metrics --sprint`
reports the open sprint: forecast points at the start, points done, points
added after the start, and items carried in.

```
pm metrics --weeks 8
pm metrics --sprint
pm metrics --product IP --json
```

### `pm brief` — meeting prep, and the debrief

Memory is per audience, which is not the same as last week.

```
pm brief --for "Monthly portfolio review"
pm brief --for standup --product IP
pm brief --debrief notes.md --for "Monthly portfolio review"
pm brief --debrief notes.md --apply
```

### `pm publish` and `pm schedule`

Publish where people already read. Enable Confluence, Teams, or both in
`publish:`. Every send is preview → confirm → write-log. Nothing that writes
to Jira (or publishes) runs on a timer.

```
pm report --publish --dry-run
pm publish weekly_report_2026-09-03.md --yes
pm schedule add today --at 08:30
pm schedule add report --weekly fri@16:00
pm schedule list
```

On Windows, `scripts/register-pm-task.ps1` registers Task Scheduler entries.
Elsewhere a `schedule.cron` snippet is written next to the job list.

### `pm ready` — the team's working agreement

One pass/fail verdict per ticket: *is this good to pull into a sprint?* A ticket
is **Ready** only when every **blocking** criterion is met. The header calls
that list a team working agreement. The pass/fail table stays.

```
pm ready              # fast gate — deterministic rules only
pm ready --deep       # also run the model reviews as blocking checks
```

Output: `ready_report_<date>.md` with a percent-ready summary, a **🔴 Not ready**
table naming exactly which criteria each ticket fails, and a **🟢 Ready** list.
Choose which criteria block readiness in the `ready:` config block — available:
`clear-title`, `has-acceptance-criteria`, `has-estimate`, `linked-to-parent`,
`has-component`, `sane-dates`, `too-big-for-a-sprint`. Anything not listed
becomes an advisory note, except `too-big-for-a-sprint`, which does nothing
until you list it. The threshold is `ready.max_points` (default 8). An item
with no estimate does not also fail that rule.

Definition of Done is a printed checklist (`definition_of_done:` on the
config or on a product). `pm report` prints it in the Increment section.
A line may set `label:`, and then `pm ready` warns when a Done item lacks
that label. Lines without a label are reminders only.

### `pm coverage`

Open issues no workstream claims, open issues two or more workstreams claim,
and Jira components in the team project that no workstream names. Exit 1
when unclaimed work exists, so it can sit next to `pm products check` on a
schedule. `--workstream` chooses which projects to inspect; claims use every
workstream in that project.

```
pm coverage
pm schedule add coverage --at 08:45
```

### `pm release-notes`

Done issues since a date or in a fixVersion, grouped by product and
workstream. The model drafts prose when it is up. Otherwise the command
prints the bullet list and says the model was skipped. The model does not
choose which issues are included.

```
pm release-notes --since 2026-08-01
pm release-notes --version 2026.9
```

### `pm daily` — Daily Scrum snapshot

**No model.** The two things the Daily Scrum actually needs, per workstream: what
*moved* since yesterday (real status transitions from the Jira changelog), and
what's *in progress now* and who owns it.

```
pm daily                      # yesterday's movement + today's WIP
pm daily --days 3             # widen the window (e.g. after a weekend)
pm daily --by workstream      # group WIP by workstream instead of by assignee
pm daily --print              # also echo the snapshot to the terminal
```

Output: `daily_<date>.md` under `output.directory` (default `~/.pm/out`). The "moved" list reads each issue's changelog and
shows the transition — e.g. **To Do → In Review by A. Lee (today 09:12)**. If a
ticket hopped several statuses, it collapses to first-from → last-to so you see
the net move at a glance. Scope it like anything else: `pm daily -w SDX`.

The window and the definition of "in progress" come from the `daily_moved` and
`daily_wip` scopes; `--days` overrides the window for one run.

---

## A suggested weekly rhythm

- **Each morning:** `pm today` — what needs you, what moved, what is aging.
- **Before sprint planning:** `pm ready` (or `--deep`) to see what's good to pull
  in and what needs work first. Fix the reds, re-run.
- **Backlog refinement:** `pm lint` for the fast fact-based sweep, then
  `pm refine` to draft the gaps. `pm triage` for the queue waiting on you.
- **Between meetings:** `pm note "..."` — file it from `pm inbox` later.
- **Before a meeting:** `pm brief --for "Monthly portfolio review"`.
- **End of week:** `pm report --publish` for the stakeholder snapshot.
- **Once:** `pm schedule add today --at 08:30` and
  `pm schedule add report --weekly fri@16:00`.

---

## Finding your custom field IDs

Jira stores story points, start date, and the epic link in *custom fields* whose
IDs differ per site. To find yours, open:

```
https://<YOUR_ORG>.atlassian.net/rest/api/3/field
```

Search for "Story Points", "Start date", etc., and copy the `id` (looks like
`customfield_10016`) into the `jira:` block. Current Jira Cloud uses the
`parent` field for hierarchy, including company-managed projects, so leave
`epic_link_field: "parent"` unless your site specifically requires a legacy
custom Epic Link field. Leave an optional custom field blank (`""`) to skip
that check.

---

## Layout

```
pm-tools/
├── pyproject.toml       # packaging — this creates the `pm` and `pm-tools` commands
├── install.ps1          # Windows first install
├── config.yaml          # template config (pm init copies it to ~/.pm)
├── pm.py                # entry point: routes subcommands, applies --workstream
├── core/                # shared plumbing (tested, reused by every command)
│   ├── config.py        #   loads config, expands ${ENV:VAR}, validates it all
│   ├── config_edit.py   #   comment-preserving edits to the config file
│   ├── products.py      #   product lookup, Unassigned, --product filter
│   ├── cache.py         #   local fetch cache (--cached / --refresh)
│   ├── filters.py       #   plain scope options -> JQL
│   ├── workstreams.py   #   Component + parent membership -> JQL
│   ├── sources.py       #   Jira / Confluence / SharePoint fetchers
│   ├── http.py          #   one retry when Jira answers 429
│   ├── writes.py        #   the one path that writes to Jira
│   ├── decisions.py     #   snooze / accept / assign memory
│   ├── metrics.py       #   throughput, cycle time, forecast, sprint snapshot
│   ├── checklist.py     #   Product Goal sentence and Definition of Done
│   ├── output.py        #   places files under output.directory
│   ├── paths.py         #   local ~/.pm vs shared state folder
│   ├── migrations.py    #   config_version steps for pm update
│   ├── model.py         #   the local-model call + robust JSON parsing
│   └── state.py         #   week-to-week memory + diff
├── docs/
│   ├── PLAN.md                # shipped install work through tranche 2
│   ├── FEATURE_PROPOSALS.md   # earlier code-first proposals
│   ├── PORTFOLIO_PROPOSALS.md # the ten features that shipped
│   └── TERMINOLOGY.md         # Scrum Guide vocabulary check
├── setup-windows-qwen-small.ps1
├── setup-windows-qwen-large.ps1
├── tests/               # unit tests + an end-to-end run against a fake Jira
└── commands/
    ├── init.py          # pm init
    ├── products.py      # pm products
    ├── doctor.py        # pm doctor
    ├── today.py         # pm today / pm do
    ├── workstreams.py   # pm workstreams
    ├── report.py        # pm report
    ├── lint.py          # pm lint
    ├── triage.py        # pm triage
    ├── refine.py        # pm refine
    ├── review.py        # pm review (deprecated alias)
    ├── coverage.py      # pm coverage
    ├── inbox.py         # pm note / pm inbox
    ├── metrics.py       # pm metrics
    ├── release_notes.py # pm release-notes
    ├── brief.py         # pm brief
    ├── publish.py       # pm publish
    ├── schedule.py      # pm schedule
    ├── ready.py         # pm ready
    ├── daily.py         # pm daily
    └── update.py        # pm update
```

Run the tests with `python -m unittest discover -s tests` — no Jira, no model and
no network needed; `tests/fake_jira.py` stands in for both.

Each command reads its workstream list from `cfg['_workstreams']`, which `pm.py`
has already narrowed if `--workstream` was given — so a new command gets scoping
for free. Adding one is a small file in `commands/` plus a few lines in `pm.py`.

---

## Roadmap (ideas, not commitments)

`docs/PLAN.md` tranches 0 and 1 shipped in 0.7.0. Tranche 2 shipped in
0.8.0: `pm coverage`, the Sprint Goal risk line, Product Goal,
`too-big-for-a-sprint`, Definition of Done, `pm metrics --sprint`,
`pm release-notes`, and `pm inbox edit`. `config_version` 2 adds
`ready.max_points` and leaves products alone.

`docs/PORTFOLIO_PROPOSALS.md` is the previous plan: the ten features chosen
for a PM running several products and the BA who refines with them. Those
ten have shipped.

- **Products above workstreams** — shipped in 0.4.0.
- **`pm today` / `pm do`** — shipped in 0.4.0; writes landed in 0.5.0.
- **`pm note` / `pm inbox`** — shipped in 0.5.0.
- **`pm triage`** — shipped in 0.5.0.
- **`pm refine`** — shipped in 0.5.0 (`pm review` is a deprecated alias).
- **Findings that remember your decision** — shipped in 0.5.0.
- **`pm brief`** — shipped in 0.6.0.
- **`pm metrics`** — shipped in 0.6.0.
- **`pm publish` / `pm schedule`** — shipped in 0.6.0 (Teams and/or Confluence).
- **`pm doctor`** — shipped in 0.4.0, with the fetch cache.

`docs/FEATURE_PROPOSALS.md` holds the earlier, code-first list of twenty; the
last section of the portfolio document says what happened to each of them.

`docs/TERMINOLOGY.md` checks every word the tool uses against the November 2020
Scrum Guide. The Daily Scrum rename and `missing-parent` shipped in 0.7.0
with no alias. Sprint Goal risk, Definition of Done, Product Goal, and
`too-big-for-a-sprint` shipped in 0.8.0. The risk line does not name an
issue as being on the goal path.

---

## Honest limitations

- **Component names still matter.** `jira.project` and each workstream's
  `components` define the boundary. `pm workstreams check` tells you when a name
  doesn't exist in Jira, and `--show-jql` shows exactly what was built — run it
  after any edit, then confirm one workstream (`--workstream SDX`) looks right
  before expanding.
- **Overlap is allowed by design.** With the default
  `child_component_wins: false`, a child naming a different Component than its
  Epic counts in both workstreams. `pm coverage` lists those issues. Set it
  to `true` for a strict split.
- **Custom field IDs matter.** If story points or start date point at the wrong
  field ID, those checks silently skip. Verify against the field list above.
- **Deterministic vs. inference.** `pm lint` and the fast `pm ready` are rules
  you can trust. `pm report`, `pm review`, `pm ready --deep`, and a
  `pm release-notes` draft use Qwen3.8
  Q3_K_M — read them before acting. A 3-bit quant is smaller and a bit less
  sharp than Q4; keep thinking off and `review.batch_size` at 8 or below.
- **Speed.** `pm lint` is instant. Model command speed depends heavily on the local model and hardware; `--deep` and `review all` make several
  calls, so scope them with `--workstream` when you want a quick pass.

---

## Sources

1. llama.cpp — local inference and OpenAI-compatible server. https://github.com/ggml-org/llama.cpp
2. Qwen model collection. https://huggingface.co/Qwen
3. Atlassian — create and manage API tokens. https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/
4. Jira Cloud REST API — issue search (`/rest/api/3/search/jql`) and fields. https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/
5. Atlassian — the legacy `/rest/api/3/search` endpoint is removed; use `/search/jql` with `nextPageToken`. https://confluence.atlassian.com/jirakb/run-jql-search-query-using-jira-cloud-rest-api-1289424308.html
6. Confluence Cloud REST API — content search (CQL). https://developer.atlassian.com/cloud/confluence/rest/v2/
7. Microsoft Graph — SharePoint sites and drive search. https://learn.microsoft.com/en-us/graph/api/resources/sharepoint
8. Python packaging — entry points / console scripts. https://packaging.python.org/en/latest/specifications/entry-points/
