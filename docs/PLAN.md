# Plan: pm-tools rename, install, update, and the next tool work

Written after reading the repo at 0.6.0 (`pm-helper` on GitHub as
`dstainton/pm-tools`). This is the plan for the next body of work. It does
not replace `docs/PORTFOLIO_PROPOSALS.md` or `docs/FEATURE_PROPOSALS.md`;
those describe what was proposed and what already shipped.

The portfolio list of ten is built (0.4.0 through 0.6.0). The gap now is
identity, setup, and a few holes in the tools that are already there.

---

## Decisions this plan settles

1. **The product name is `pm-tools`.** That is the distribution name in
   `pyproject.toml`, the name in the README title, and the name the Windows
   setup scripts print. It matches the GitHub repo.
2. **The daily command stays `pm`.** Schedules, docs, tests, and the habit
   all use that short word. A second console script, `pm-tools`, calls the
   same `main`. Either name works; nothing in `~/.pm` has to move.
3. **User data stays in `~/.pm`.** Config, cache, `today.json`, the write
   log, and `schedule.json` already live there. Renaming that directory is
   a migration of user data and is out of scope.
4. **`pm update` is the upgrade path.** It upgrades the installed code, then
   upgrades the user's config. It never replaces the file, never copies
   sample products, workstreams, or credentials into a live file, and never
   calls `pm init --force`.
5. **`pm init` stays create-only.** If `~/.pm/config.yaml` exists it leaves
   the file alone and tells the user to run `pm update`. `--force` remains
   the only way to replace a config, and it must say so in the prompt.
6. **New commands wait until the existing ones are trustworthy.** Output
   location, exit codes, config validation, and config migration come before
   `pm coverage`, release notes, or a Definition of Done.

---

## Where things stand

| Thing | Today |
|-------|--------|
| Repo | `github.com/dstainton/pm-tools` |
| Package name | `pm-helper` in `pyproject.toml` |
| Command | `pm` only (`pm = "pm:main"`) |
| Docs and scripts | Say `pm_helper` and "Product Manager Helper" |
| Install | `pip install -e .` from a clone, then `pm init` |
| PATH | Documented as a Windows problem; pipx is a footnote |
| Model setup | `setup-windows-qwen-*.ps1` also runs `pip install -e .` |
| Update | No command. `INSTALL.md` says to hand-copy new YAML sections |
| Config version | None. `pm init` copies the template and refuses to overwrite |
| Live config edits | `core/config_edit.py` inserts or removes list entries and keeps comments. Used by `pm products` and `pm workstreams` only |
| Commands | init, products, workstreams, today, do, doctor, report, lint, triage, refine, review (deprecated alias), note, inbox, metrics, brief, publish, schedule, ready, standup |
| Tests | `python -m unittest discover -s tests`. No network. No CI workflow |

`pm doctor --discover-fields` prints field IDs and does not write them.
`pm lint` and `pm ready` always exit 0. Reports and `report_state.json` are
written in the current directory. Sprint Goal text is already shown on
`pm today` when Jira Agile returns it (`core/sources.py`
`fetch_active_sprints`). The tool does not say whether that goal is at risk,
and products have no Product Goal.

---

## Tranche 0 — name, install, and `pm update`

This tranche is the work the request asked for first. It should land as its
own change, before tool features.

### 0.1 Rename the product

Touch the identity strings. Do not rename the Python package layout
(`pm.py`, `core/`, `commands/`) in this tranche; import paths are stable and
a folder rename is not what "matches the repo" requires.

| Location | Change |
|----------|--------|
| `pyproject.toml` | `name = "pm-tools"`. Description says pm-tools. Scripts: `pm = "pm:main"` and `pm-tools = "pm:main"`. Comment uninstall line becomes `pip uninstall pm-tools` (and notes that an older editable install may still be named `pm-helper`) |
| `README.md`, `INSTALL.md`, `config.yaml` header, `pm.py` description | Product name pm-tools. Folder references say the repo name, not `pm_helper` |
| `setup-windows-qwen-small.ps1`, `setup-windows-qwen-large.ps1` | Printed name and User-Agent say `pm-tools`. Stop installing the CLI from these scripts (see 0.2) |
| `CHANGELOG.md` | New section for the release that does this. Do not rewrite history |

Search for `pm-helper` and `pm_helper` and update the ones that name the
product. Leave historical changelog sentences that describe the old package
name as they were.

### 0.2 One install path

The supported install is pipx, so `pm` is on PATH and the tool's dependencies
stay out of the system Python.

From a clone, for someone who will run the tool:

```text
pipx install .
pm init
pm doctor
```

From GitHub, with no clone:

```text
pipx install git+https://github.com/dstainton/pm-tools.git
pm init
pm doctor
```

Development stays a separate, labeled path: `pip install -e .` inside the
clone. The README should say that editable mode does not get `pm update`'s
code upgrade (see 0.3); you `git pull` yourself.

Add `install.ps1` at the repo root for the Windows laptop, because that is
who the Qwen scripts are for. It should:

1. Require Python 3.9+.
2. Install pipx for the user if `pipx` is not on PATH, then `pipx ensurepath`.
3. `pipx install` the directory that contains `pyproject.toml` (the script's
   own folder).
4. Run `pm init` only when `~/.pm/config.yaml` does not exist.
5. Print the next two lines: fill in the config, then `pm doctor`.

It should not download a model. Model setup stays in the Qwen scripts, and
those scripts should assume `pm` is already installed.

`INSTALL.md` becomes this short path plus the model section. Delete the
paragraph that tells an existing user to copy `products:`, `cache:`, and the
rest by hand. That job moves to `pm update`.

### 0.3 `pm update`

New command in `commands/update.py`, routed from `pm.py` the same way as
`init`: it must run even when the config is old or incomplete, so it does
not go through `load_config` until after a migration has been written and
validated.

```text
pm update                 # upgrade code, then upgrade config
pm update --code-only     # leave the config file byte-for-byte
pm update --config-only   # migrate config using the template already installed
pm update --dry-run       # print what would change; write nothing
```

`pm doctor` gains one line: if `config_version` is behind the installed
template, it prints `run pm update` and exits non-zero. It does not edit
the file.

#### Code upgrade

Detect how this process was installed, from the package metadata
(`importlib.metadata`) and from `__file__`:

| Install | What `pm update` runs |
|---------|------------------------|
| pipx, package name `pm-tools` | `pipx upgrade pm-tools` |
| Non-editable pip install whose direct URL is the GitHub repo | `python -m pip install --upgrade` that same URL, in the environment that is running `pm` |
| Editable install (`pip show` location is a checkout) | Do not pull and do not reinstall. Print that this is a checkout and the code update is `git pull` in that directory. Then still offer the config migration against the template sitting next to the code |
| Anything else | Stop with the exact command it would have run, and do not guess |

A failed code upgrade stops the command before any config write. Config
migration uses the template from the code that is running after a successful
upgrade, or the current tree in `--config-only` and editable mode.

#### Which file is the user's config

`pm update` edits one file:

1. `--config`, if passed.
2. `$PM_CONFIG`, if set.
3. Otherwise `~/.pm/config.yaml`.

It does **not** follow the normal discovery order. Discovery prefers
`./config.yaml`, and inside a clone that file is the template. Updating that
file would rewrite the repo. If the resolved user file does not exist,
`pm update` says to run `pm init` and exits. If the resolved path is inside
the installed package directory, it refuses.

#### Config upgrade rules

These are invariants. Tests should fail if any of them breaks.

1. **Never replace the file.** No `shutil.copyfile` of the template over a
   live config. `init --force` is not called.
2. **Never change a value that is already set.** Credentials, URLs, project
   keys, products, workstreams, tuned lint thresholds, scopes the user
   overrode, and `state.shared_path` stay as written.
3. **Add a missing key.** New settings appear with the template's default
   and a short comment, inserted before the next top-level key so the rest
   of the file does not move.
4. **Do not paste samples into a live file.** The template's Integration
   Platform product and SDX / APS / ITK workstreams are examples for
   `pm init` only. A migration that finds no `products:` inserts an empty
   `products:` list and a comment, not the sample product. A migration never
   inserts workstream entries.
5. **Renames copy, they do not delete, for one release.** If a future key is
   renamed, write the new key only when it is absent, using the old value,
   and keep reading the old key. Say so in the changelog.
6. **Comments and unrelated lines stay.** Build on `core/config_edit.py`
   (line edits of top-level blocks), not a YAML dump.
7. **Validate before replace.** Parse the result, run `core.config.validate`,
   and write only if that passes. Write to a temp file beside the target,
   then replace. If validation fails, the original file is untouched and the
   command exits with the validation message.
8. **Idempotent.** A second `pm update` against an already-current file
   prints that the config is current and does not rewrite it.
9. **Secrets stay out of the preview.** `--dry-run` redacts values under
   keys named `api_token`, `client_secret`, and `webhook`.

#### `config_version`

An integer, independent of the package version, so one release can ship
several migrations and an old file can jump more than one step.

The template gains, near the top:

```yaml
config_version: 1
```

A user file with no `config_version` is version 0. Version 0 is the shape
already shipped in 0.6.0: optional `products`, `cache`, `today`, `state`,
`triage`, `metrics`, `publish`, `membership`, and `scopes`, plus legacy
workstreams that still use `*_jql`.

Migration 0 → 1 does only this:

- Insert `config_version: 1` if absent.
- For each of `cache`, `today`, `state`, `triage`, `metrics`, `publish`,
  `review`, `ready`, `standup`, `membership`, `scopes`: if that top-level
  key is absent, insert the default block from a small table in
  `core/migrations.py` (the same values as today's template, without the
  sample portfolio).
- If `products:` is absent, insert an empty list. Do not invent a product
  for existing workstreams; Unassigned already covers them.
- Leave `workstreams:`, `jira:`, `confluence:`, `sharepoint:`, `lint:`,
  `model:`, and `output:` alone, including keys the user deleted on purpose.

Later migrations append to a list. `pm update` walks from the file's version
to the template's version. The template's `config_version` is the source of
truth for "current".

`output.directory` is **not** part of migration 0 → 1. Changing where reports
land is tranche 1, and it must not silently move `report_state.json` for
someone who has been running `pm report` from one folder. When that setting
arrives, the migration adds it only if absent, and doctor warns when
`output.state_file` is still a relative path.

### 0.4 Tests for tranche 0

No network. Extend the existing unittest style.

- A version-0 fixture copied from an old-shaped config (no `products:`, no
  `cache:`, with a real `jira.api_token` and two workstreams) migrates to
  version 1, gains the missing blocks, and keeps the token, the workstreams,
  and a comment that was in the file.
- The same fixture does not gain "Integration Platform" or "SDX".
- Running the migration twice leaves the file unchanged the second time.
- A file that fails validation after a deliberately broken migration step is
  not replaced.
- `pm update` refuses a path inside the package directory.
- `pm init` on an existing file does not change it and mentions `pm update`.
- CLI help lists `update`. Both script names are in `pyproject.toml`.

---

## Tranche 1 — make the current tools solid

Do this after `pm update` exists, so each new config key has a migration.

### 1.1 Reports land in one place

Today `commands/report.py`, `lint.py`, `ready.py`, `standup.py`, `refine.py`,
`metrics.py`, and `brief.py` write `<name>_<date>.md` into the current
directory. `output.state_file` defaults to `report_state.json` in that same
directory, which is why the README tells people to always run from `~/.pm`.

Add `output.directory`, default `~/.pm/out` for new configs only. Relative
`output.file` and `output.state_file` resolve under that directory.
`--out PATH` on a command overrides the directory for one run. Existing
configs keep their relative `state_file` until the user changes it; `pm
doctor` names that as a warning, not a rewrite.

### 1.2 Exit codes the gates can use

`pm doctor`, `pm workstreams check`, and `pm products check` already exit 1
on failure. `pm lint` and `pm ready` do not.

```text
pm lint --fail-on error
pm ready --fail-under 80
```

Default stays exit 0, so current scheduled jobs do not start failing.
`pm schedule add` can later take the flags as extra arguments for the safe
commands; do not change the default job args in this step.

### 1.3 Config load fills defaults and names the missing piece

`core/config.py` validates products, workstreams, membership, and scopes.
A missing `output.file` or `model.timeout` still raises `KeyError` mid-command.
After load, fill documented defaults for `model`, `output`, `lint`, `ready`,
`cache`, `today`, `triage`, and `metrics` when the key is absent, and reject
unknown types (a string where a mapping is required) with the key name.
Filling a default in memory is not a write. The file changes only in
`pm update`.

### 1.4 Field IDs, written only when blank

`pm doctor --discover-fields` keeps printing the snippet. Add `--yes` to
write, through the same comment-preserving editor, and only into
`story_points_field`, `start_date_field`, or `acceptance_criteria_field`
when the current value is empty. A non-empty value is never replaced.
Preview without `--yes`. This is a Jira-aware edit, so it stays on doctor
rather than on `pm update`.

### 1.5 Vocabulary aliases from `docs/TERMINOLOGY.md`

One release of overlap, no broken configs:

| Now | Add | Keep reading |
|-----|-----|----------------|
| `pm standup` | `pm daily` as the name in help | `standup` as a silent alias |
| `standup:` and `standup_moved` / `standup_wip` | `daily:`, `daily_moved`, `daily_wip` accepted | old keys |
| `missing-epic`, `linked-to-epic` | `missing-parent`, `linked-to-parent` in new output | old names in `lint.required_fields` and `ready.blocking_criteria` |

Report titles say "Daily Scrum" and "Product Backlog". Do not rename
`workstream`.

### 1.6 Small fixes, batched with the tests that cover them

From the still-open list in `docs/FEATURE_PROPOSALS.md`:

- Escape the SharePoint search term in `core/sources.py` `fetch_sharepoint`.
- `pm lint` stale check should use the last status change in the changelog
  when a changelog is already available, and fall back to `updated` when it
  is not.
- Split `lint.vague_title_terms` so `refactor` and `test` flag only when
  they are the whole title, not when they appear inside a specific one.
- `commands/report.py` should keep the reference tag on items that dropped
  out of the week.
- `--workstream` and `--product` accept the full name, case-insensitively,
  as well as the abbreviation.
- On HTTP 429, honor `Retry-After` once, then fail with the rate-limit
  message. Do not add a thread pool in this tranche.

Confluence v1 search stays until Atlassian removes it. Track it in the
changelog note, do not migrate it here.

### 1.7 CI

Add a GitHub Actions workflow that runs
`python -m unittest discover -s tests` on Python 3.9 and 3.13, plus one
Windows job. The suite already needs no network and no model. No lint job
until the repo has a linter config.

---

## Tranche 2 — gaps in the tools

These are the deferred items that still match the PM and the person refining
with them. Each one is a small command or a section on a command that
already exists. None of them write to Jira on their own.

### 2.1 `pm coverage`

Membership is easy to get wrong once products and workstreams are a command
to add. Doctor already counts unclaimed open work. `pm coverage` lists it:

- open issues no workstream claims
- open issues two or more workstreams claim
- Jira components in the team project that no workstream names

No new config. The queries are the negation of the membership clauses in
`core/workstreams.py`. Exit 1 when unclaimed work exists, so it can be
scheduled next to `pm products check`.

### 2.2 Sprint Goal risk on `pm today`

The goal string is already printed. Under it, add a deterministic line when
the active sprint has an end date: not-started items in that sprint, blocked
items, and days left. Jira does not link issues to the goal text, so the
line must not claim a specific issue is "on the goal path". Wording:
"Sprint ends in N days. Not started: K. Blocked: M."

### 2.3 Product Goal

Optional `product_goal:` on a product. `pm products add` grows a
`--goal` flag. `pm report` and `pm brief` print that sentence once under
the product heading. Empty means the section is omitted. Migration adds
nothing to existing products.

### 2.4 Ready agreement: size, and a checklist that is honest

`pm ready` stays. Two changes:

- New blocking criterion `too-big-for-a-sprint`, off unless listed in
  `ready.blocking_criteria`. Threshold is `ready.max_points` (default 8).
  An item with no estimate does not also fail this rule; `has-estimate`
  already covers that.
- Header text calls the result a team working agreement, matching
  `docs/TERMINOLOGY.md`. The pass/fail table stays, because that is what
  the refinement queue needs.

Definition of Done is a printed checklist, not a fake verifier. Optional
`definition_of_done:` list on the config or on a product. `pm report`
prints it next to the Increment section. A line may set `label:` and then
`pm ready` can warn when a Done item lacks that label. Lines without a
label are reminders only. Do not add a `pm done` command.

### 2.5 This sprint, on `pm metrics`

`pm metrics --sprint` reports the open sprint: forecast points at start,
points done, points added after start, items carried in. The changelog
fetch that metrics already uses is enough. This replaces a separate
`pm sprint-review` command.

### 2.6 `pm release-notes`

Read-only. Done issues since a date or in a `fixVersion`, grouped by
product and workstream. The model drafts prose when it is up; otherwise the
command prints the bullet list and says the model was skipped. Same pattern
as report: the model does not decide which issues are included.

```text
pm release-notes --since 2026-08-01
pm release-notes --version 2026.9
```

### 2.7 `pm inbox edit`

`docs/PORTFOLIO_PROPOSALS.md` shows `pm inbox edit N`. The command has
list, create, and drop. Add edit so a title, workstream, or acceptance
criteria can be corrected before create. Edit writes `inbox.json` only.

### 2.8 Leave for later

Do not build these in the tranches above:

- `pm duplicates` and a standalone `pm risks` register. Brief and the
  Confluence labels already cover the weekly case. Revisit if a real week
  of use shows the brief inventing risks.
- `pm inbox` model suggestions are already there; do not add a second
  capture command.
- Deeper parent walks (`membership.parent_depth`), label/fixVersion
  membership, and a keyring secret backend. Worth doing when a second team
  does not use Components. `${ENV:VAR}` remains the supported way to keep
  the token out of the file.
- A GUI, a dashboard, unattended Jira writes, and model-written claims
  about what is true. The portfolio doc already rules these out.
- Moving `~/.pm` to `~/.pm-tools`.

---

## Order of work

1. Tranche 0.1 and 0.2 together: rename, pipx install docs, `install.ps1`,
   Qwen scripts no longer install the CLI.
2. Tranche 0.3 and 0.4: `config_version`, migrations, `pm update`, doctor
   notice, tests.
3. Tranche 1.1 through 1.4: output directory, exit codes, load-time
   defaults, discover-fields write-if-blank. Each new key gets a migration
   and a test that an existing value survives.
4. Tranche 1.5 and 1.6: aliases and the small fixes.
5. Tranche 1.7: CI, once the tests cover the migrations.
6. Tranche 2 in the order listed. `pm coverage` and the Sprint Goal line
   first, because they change the daily screen without a new habit.

Package version for the tranche 0 release: 0.7.0. Tranche 1 can be 0.8.0.
Tranche 2 can be 0.9.0 or split if release notes land later. `config_version`
moves only when a migration ships.

---

## Done when

- `pipx install` of this repo produces both `pm` and `pm-tools`.
- `pm init` on a machine with no config creates `~/.pm/config.yaml`.
- `pm init` a second time does not change that file.
- `pm update --dry-run` on a version-0 file shows added blocks and the same
  token, products, and workstreams.
- `pm update` a second time reports the config current and the file hash
  is unchanged.
- `pm doctor` on a stale config exits non-zero and prints `pm update`.
- `pm today` still runs from any directory after the output-directory
  change, and `report_state.json` for a new config is under `~/.pm`.
- `python -m unittest discover -s tests` passes with no network.
