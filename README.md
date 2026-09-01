# Product Manager Helper (`pm`)

A small command-line tool that helps a PM stay on top of a backlog and keep
directors informed. One config, several commands, all running against your own
Jira / Confluence / SharePoint and a **local** model — nothing leaves your
laptop.

```
pm init       Create a starter config at ~/.pm/config.yaml
pm report     Weekly state-of-product report (uses the local model)
pm lint       Deterministic backlog quality checks (no model — pure rules)
pm review     Model-based judgement checks (title clarity, AC quality)
pm ready      Definition-of-Ready gate: pass/fail per ticket
pm standup    Daily movement + work-in-progress snapshot (no model)
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
#   Edit that file: Jira URL, email, API token, and your workstreams.

# 3. Run from anywhere — no python, no file path.
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
- **Custom field IDs:** story points, start date, epic link — see
  **Finding your custom field IDs** below.
- **SharePoint:** leave `enabled: false` until an admin sets up an Azure app.
- **Workstreams:** SDX, APS, ITK are pre-filled with their query lines.

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

# Larger 27B model for use when bandwidth is not constrained:
.\setup-windows-qwen-large.ps1
.\setup-windows-qwen-large.ps1 -StartServer
```

Both scripts expose the model as `qwen-local`, so `pm` does not need a config
change when you switch between the small and large model. Other
OpenAI-compatible local servers can still be used by changing `model.endpoint`
and `model.name`.

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

### Jira workstream inheritance

The bundled config models all three workstreams inside the **APS Jira project**:

```text
APS project
  -> Epic / feature / work package
       -> Component identifies workstream
            -> Stories / Tasks / Bugs
                 -> Sub-tasks
```

The Component belongs on the **Epic**. Child work does not need the same
Component duplicated onto every Story or Task.

Each workstream declares the Jira project and the Component name(s) that define
its Epics:

```yaml
- name: "Secure Data Exchange"
  abbrev: "SDX"
  jira_project: "APS"
  epic_components: ["Secure Data Exchange"]
  jira_jql: 'sprint in openSprints()'
  roadmap_jql: 'statusCategory != Done'
  lint_jql: 'statusCategory != Done'
```

For this form of workstream, the `*_jql` values are **additional filters**, not
complete queries. `pm` first discovers the matching Epics, then builds the
appropriate Jira scope:

- normal report, ready, and standup: descendants of those Epics
- roadmap: the workstream Epics themselves
- lint and review: the Epics plus their descendants

Jira's `parentEpic` query is used so nested Sub-tasks are included along with
Stories and Tasks. The Epic list is cached for the duration of each command.

If your Jira Component names differ from the values in `config.yaml`, edit
`epic_components` to match Jira exactly. A workstream can list more than one
Component.

**Backward compatibility:** a workstream that omits `jira_project` and
`epic_components` remains in legacy mode, where each `*_jql` value is treated
as a complete JQL query exactly as in earlier versions.

---

## The commands

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
| `missing-component` | 🟠 warn | No component set when the workstream does not inherit it from the Epic |
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
pm standup --by workstream    # group WIP by workstream instead of by owner
pm standup --print            # also echo the snapshot to the terminal
```

Output: `standup_<date>.md`. The "moved" list reads each issue's changelog and
shows the transition — e.g. **To Do → In Review by A. Lee (today 09:12)**. If a
ticket hopped several statuses, it collapses to first-from → last-to so you see
the net move at a glance. Scope it like anything else: `pm standup -w SDX`.

Per workstream you can set `standup_moved_jql` (use `{days}` for the window)
and `standup_wip_jql`. In Epic-component mode these are additional filters over
child work beneath the workstream Epics.

---

## A suggested weekly rhythm

- **Each morning:** `pm standup` — what moved yesterday, what's in flight today.
- **Before sprint planning:** `pm ready` (or `--deep`) to see what's good to pull
  in and what needs work first. Fix the reds, re-run.
- **Backlog grooming:** `pm lint` for the fast fact-based sweep, then `pm review`
  when you want the model's eyes on titles and acceptance criteria.
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
│   ├── config.py        #   loads config, expands ${ENV:VAR}, validates workstreams
│   ├── workstreams.py   #   resolves Epic Component inheritance into JQL
│   ├── sources.py       #   Jira / Confluence / SharePoint fetchers
│   ├── model.py         #   the local-model call + robust JSON parsing
│   └── state.py         #   week-to-week memory + diff
├── setup-windows-qwen-small.ps1
├── setup-windows-qwen-large.ps1
└── commands/
    ├── init.py          # pm init
    ├── report.py        # pm report
    ├── lint.py          # pm lint
    ├── review.py        # pm review
    ├── ready.py         # pm ready
    └── standup.py       # pm standup
```

Each command reads its workstream list from `cfg['_workstreams']`, which `pm.py`
has already narrowed if `--workstream` was given — so a new command gets scoping
for free. Adding one is a small file in `commands/` plus a few lines in `pm.py`.

---

## Roadmap (ideas, not commitments)

- `pm duplicates` — model-flagged likely duplicate tickets.
- `pm release-notes` — draft notes from tickets marked Done since last release.

---

## Honest limitations

- **Component names and filters still matter.** In Jira, `jira_project` and
  `epic_components` define the workstream boundary; the JQL strings then narrow
  that inherited scope. Start with one workstream (`--workstream SDX`), confirm
  the resolved items look right, then expand.
- **Custom field IDs matter.** If story points or start date point at the wrong
  field ID, those checks silently skip. Verify against the field list above.
- **Deterministic vs. inference.** `pm lint` and the fast `pm ready` are rules
  you can trust. `pm report`, `pm review`, and `pm ready --deep` use the model —
  read them before acting. Quantized local models save memory but may be less sharp than larger models.
- **Speed.** `pm lint` is instant. Model command speed depends heavily on the local model and hardware; `--deep` and `review all` make several
  calls, so scope them with `--workstream` when you want a quick pass.

---

## Sources

1. llama.cpp — local inference and OpenAI-compatible server. https://github.com/ggml-org/llama.cpp
2. Qwen model collection. https://huggingface.co/Qwen
3. Atlassian — create and manage API tokens. https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/
4. Jira Cloud REST API — search (JQL) and fields. https://developer.atlassian.com/cloud/jira/platform/rest/v3/
5. Confluence Cloud REST API — content search (CQL). https://developer.atlassian.com/cloud/confluence/rest/v2/
6. Microsoft Graph — SharePoint sites and drive search. https://learn.microsoft.com/en-us/graph/api/resources/sharepoint
7. Python packaging — entry points / console scripts. https://packaging.python.org/en/latest/specifications/entry-points/
