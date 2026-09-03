# Product Manager Helper (`pm`)

A small command-line tool that helps a PM stay on top of a backlog and keep
directors informed. One config, several commands, all running against your own
Jira / Confluence / SharePoint and a **local** model — nothing leaves your
laptop.

```
pm init         Create a starter config at ~/.pm/config.yaml
pm workstreams  List, add, remove or check your workstreams
pm report       Weekly state-of-product report (uses the local model)
pm lint         Deterministic backlog quality checks (no model — pure rules)
pm review       Model-based judgement checks (title clarity, AC quality)
pm ready        Definition-of-Ready gate: pass/fail per ticket
pm standup      Daily movement + work-in-progress snapshot (no model)
```

Every command (except `init`) can be scoped to one or more workstreams with
`--workstream`.

---

## Quick start

```
# 1. Install once, from inside this folder. Turns `python pm.py` into `pm`.
pip install -e .

# 2. Create your config in the standard spot, then fill it in.
pm init
#   → opens nothing; it just copies a template to ~/.pm/config.yaml.
#   Edit that file: Jira URL, email, API token, project, and your workstreams.

# 3. Confirm Jira agrees with what you typed.
pm workstreams check

# 4. Run from anywhere — no python, no file path.
pm lint --workstream SDX
```

You also need **Python 3.9+** and, for the model-backed commands (`report`,
`review`, `ready --deep`), a local OpenAI-compatible model server — see
**The local model** below. `pm lint`, `pm standup`, and the fast `pm ready` need
no model at all.

---

## Installing as a real command

The friction of typing `python pm.py …` goes away once you install the project.
`pip` reads `pyproject.toml`, sees this:

```toml
[project.scripts]
pm = "pm:main"
```

…and drops a small `pm` launcher onto your PATH. From inside the `pm_helper`
folder:

```
pip install -e .
```

The `-e` means **editable**: pip links to your files in place, so every edit to
the code or config takes effect immediately — no reinstalling. Remove it any
time with `pip uninstall pm-helper`.

### Windows: if `pm` isn't found after install

`pip` puts the launcher in your Python **Scripts** folder. If that folder isn't
on PATH you'll see `pm: command not found`. Two fixes:

- **Best — use pipx**, which handles PATH for you and isolates the tool:
  ```
  python -m pip install --user pipx
  python -m pipx ensurepath        # then reopen your terminal
  pipx install -e .                # run from the pm_helper folder
  ```
- **Or add Scripts to PATH manually.** Find the folder with:
  ```
  python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
  ```
  Add it to PATH (System Settings → Environment Variables) and reopen the
  terminal.

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

After `pm init`, open the file and fill in the `<PLACEHOLDERS>`. If you already
have `~/.pm/config.yaml`, upgrading the package does **not** overwrite it; copy
new config sections into your existing file instead.

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

The report's `report_state.json` (the "what changed" memory) is written to the
folder you run `pm report` from. Pick a home — e.g. always run it from `~/.pm` —
so the week-to-week history stays in one place.

---

## The local model

Only needed for `pm report`, `pm review`, and `pm ready --deep`.

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
`pm review` empty or half-cut JSON. `pm` also sends
`chat_template_kwargs.enable_thinking: false` and a `/no_think` prefix on every
call, so a server started by hand still behaves.

The prompts themselves are short, numbered, and end with a fill-in skeleton or a
worked JSON example — the shape Qwen3.8 Q3_K_M follows. Sampling matches Qwen's
instruct profile (temperature 0.4, `top_p` 0.8, `top_k` 20, `presence_penalty`
1.5), with a cooler `json_temperature` of 0.2 for `pm review`.

Other OpenAI-compatible local servers can still be used by changing
`model.endpoint` and `model.name`. If you turn thinking back on, set
`model.enable_thinking: true` so `pm` stops sending `/no_think`.

---

## Scoping to a workstream — `--workstream`

Every command runs all workstreams by default. To focus on one (or a few), add
`--workstream` (short form `-w`) with comma-separated abbreviations,
case-insensitive:

```
pm lint   --workstream SDX          # just Secure Data Exchange
pm ready  -w sdx,itk                 # two of them
pm report --workstream APS           # one director snapshot
```

A typo fails loudly with the list of valid names. Scoping `pm report` is safe:
it updates only the selected workstream's "what changed" memory.

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
  standup_moved: {updated_within_days: 1}
  standup_wip:   {status: in-progress}
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
and the standup scopes look at child work, `roadmap` at the workstream Epics,
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

### `pm lint` — backlog quality checks

**No model. Pure rules**, so you can trust every finding and run it before every
sprint planning.

| Check | Severity | What it catches |
|-------|----------|-----------------|
| `bad-dates` | 🔴 error | Due before start, or due date passed but not done |
| `missing-component` | 🟠 warn | No component set, in a legacy workstream that can't inherit one |
| `missing-epic` | 🟠 warn | Story/task not linked to an epic or parent |
| `missing-acceptance-criteria` | 🟠 warn | No AC found on a story/bug |
| `no-estimate` | 🟠 warn | In-scope story with no story points |
| `stale` | 🟠 warn | "In Progress" but untouched for *N* days |
| `vague-title` | 🔵 review | Title too short or full of vague words |

Output: `lint_report_<date>.md`. Flags: `--severity error` (only hard problems),
`--json` (machine-readable). Every threshold lives in the `lint:` config block.

> **Lint vs. review.** `pm lint` uses cheap, reliable heuristics that never cry
> wolf but won't catch subtler cases. For real judgement, use `pm review`.

### `pm review` — model-based judgement checks

The smart cousins of the lint heuristics. These ask the **local model** to make
calls rules can't, and every finding is a **suggestion for your judgement**:

```
pm review titles      # flag ambiguous titles + a suggested rewrite
pm review criteria    # flag weak/missing AC + what to add
pm review all         # both (default)
```

Output: `review_titles_<date>.md` and/or `review_criteria_<date>.md`, each with
the model's reasoning. Issues go to the model in batches (`review.batch_size`);
a misfiring batch is skipped and noted, never crashing the run.

### `pm ready` — Definition-of-Ready gate

One pass/fail verdict per ticket: *is this good to pull into a sprint?* A ticket
is **Ready** only when every **blocking** criterion is met.

```
pm ready              # fast gate — deterministic rules only
pm ready --deep       # also run the model reviews as blocking checks
```

Output: `ready_report_<date>.md` with a percent-ready summary, a **🔴 Not ready**
table naming exactly which criteria each ticket fails, and a **🟢 Ready** list.
Choose which criteria block readiness in the `ready:` config block — available:
`clear-title`, `has-acceptance-criteria`, `has-estimate`, `linked-to-epic`,
`has-component`, `sane-dates`. Anything not listed becomes an advisory note.

### `pm standup` — daily movement snapshot

**No model.** The two things a standup actually needs, per workstream: what
*moved* since yesterday (real status transitions from the Jira changelog), and
what's *in progress now* and who owns it.

```
pm standup                    # yesterday's movement + today's WIP
pm standup --days 3           # widen the window (e.g. after a weekend)
pm standup --by workstream    # group WIP by workstream instead of by assignee
pm standup --print            # also echo the snapshot to the terminal
```

Output: `standup_<date>.md`. The "moved" list reads each issue's changelog and
shows the transition — e.g. **To Do → In Review by A. Lee (today 09:12)**. If a
ticket hopped several statuses, it collapses to first-from → last-to so you see
the net move at a glance. Scope it like anything else: `pm standup -w SDX`.

The window and the definition of "in progress" come from the `standup_moved` and
`standup_wip` scopes; `--days` overrides the window for one run.

---

## A suggested weekly rhythm

- **Each morning:** `pm standup` — what moved yesterday, what's in flight today.
- **Before sprint planning:** `pm ready` (or `--deep`) to see what's good to pull
  in and what needs work first. Fix the reds, re-run.
- **Backlog refinement:** `pm lint` for the fast fact-based sweep, then
  `pm review` when you want the model's eyes on titles and acceptance criteria.
- **End of week:** `pm report` for the director snapshot.

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
pm_helper/
├── pyproject.toml       # packaging — this is what creates the `pm` command
├── config.yaml          # template config (pm init copies it to ~/.pm)
├── pm.py                # entry point: routes subcommands, applies --workstream
├── core/                # shared plumbing (tested, reused by every command)
│   ├── config.py        #   loads config, expands ${ENV:VAR}, validates it all
│   ├── filters.py       #   plain scope options -> JQL
│   ├── workstreams.py   #   Component + parent membership -> JQL
│   ├── sources.py       #   Jira / Confluence / SharePoint fetchers
│   ├── model.py         #   the local-model call + robust JSON parsing
│   └── state.py         #   week-to-week memory + diff
├── docs/
│   └── FEATURE_PROPOSALS.md   # what's next, and why
├── setup-windows-qwen-small.ps1
├── setup-windows-qwen-large.ps1
├── tests/               # unit tests + an end-to-end run against a fake Jira
└── commands/
    ├── init.py          # pm init
    ├── workstreams.py   # pm workstreams
    ├── report.py        # pm report
    ├── lint.py          # pm lint
    ├── review.py        # pm review
    ├── ready.py         # pm ready
    └── standup.py       # pm standup
```

Run the tests with `python -m unittest discover -s tests` — no Jira, no model and
no network needed; `tests/fake_jira.py` stands in for both.

Each command reads its workstream list from `cfg['_workstreams']`, which `pm.py`
has already narrowed if `--workstream` was given — so a new command gets scoping
for free. Adding one is a small file in `commands/` plus a few lines in `pm.py`.

---

## Roadmap (ideas, not commitments)

`docs/PORTFOLIO_PROPOSALS.md` is the current plan: the next ten features, chosen
for a PM running several products and the BA who refines with them.

- **Products above workstreams** — a portfolio layer, `--product` everywhere.
- **`pm today`** — one bounded screen, with a numbered action list.
- **`pm capture` / `pm inbox`** — three seconds to file an idea, decide later.
- **`pm triage`** — what is waiting on a decision from you, with the action.
- **`pm refine`** — the BA's queue, with drafted titles, criteria and estimates.
- **Findings that remember your decision** — snooze, accept, or hand to the BA.
- **`pm brief`** — meeting prep and debrief, with per-audience memory.
- **`pm metrics`** — throughput, cycle time, aging work and a plain forecast.
- **`pm publish` / `pm schedule`** — the weekly update goes out without you.
- **`pm doctor`** — verify the whole setup, and a cache that makes it all fast.

`docs/FEATURE_PROPOSALS.md` holds the earlier, code-first list of twenty; the
last section of the portfolio document says what happened to each of them.

`docs/TERMINOLOGY.md` checks every word the tool uses against the November 2020
Scrum Guide — what to rename, what to keep in Jira's vocabulary on purpose, and
the three Scrum concepts `pm` has no notion of yet (Sprint Goal, Definition of
Done, Product Goal).

---

## Honest limitations

- **Component names still matter.** `jira.project` and each workstream's
  `components` define the boundary. `pm workstreams check` tells you when a name
  doesn't exist in Jira, and `--show-jql` shows exactly what was built — run it
  after any edit, then confirm one workstream (`--workstream SDX`) looks right
  before expanding.
- **Overlap is allowed by design.** With the default
  `child_component_wins: false`, a child naming a different Component than its
  Epic counts in both workstreams. Set it to `true` for a strict split.
- **Custom field IDs matter.** If story points or start date point at the wrong
  field ID, those checks silently skip. Verify against the field list above.
- **Deterministic vs. inference.** `pm lint` and the fast `pm ready` are rules
  you can trust. `pm report`, `pm review`, and `pm ready --deep` use Qwen3.8
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
