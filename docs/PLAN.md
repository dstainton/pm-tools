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
   same `main`.
3. **User data lives in `~/.pm`.** Config, cache, `today.json`, the write
   log, and `schedule.json` go there. Nothing has been installed yet, so
   this is a choice for the first install, not a migration.
4. **First install creates a new config. It does not upgrade one.** Nobody
   has run the tool. There is no live `~/.pm/config.yaml` to preserve, and
   no old config shape to keep working. Template changes before the first
   real install can break the old file format freely.
5. **Compatibility starts at first install.** The config `pm init` writes
   is the baseline. After that, `pm update` upgrades the code and adds new
   config keys. It never replaces the file and never calls `pm init --force`.
6. **`pm init` is create-only.** If `~/.pm/config.yaml` already exists it
   leaves the file alone and tells you to run `pm update`. `--force` is the
   only replace path, and it must say so.
7. **New commands wait until install and update are real.** Output location,
   exit codes, and config validation come before `pm coverage`, release
   notes, or a Definition of Done. Renames that would have needed aliases
   (`standup` → `daily`, `missing-epic` → `missing-parent`) can just happen
   before first install. Aliases are for changes made after someone has
   installed.

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

The install documented in `README.md` and `INSTALL.md` is the developer
install (`pip install -e .` from a clone). That is not the first-install
path below. A new user should not have to clone the repo or fix PATH.

---

## First install

This is the whole path for someone who has never run pm-tools. Python 3.9+
is the only prerequisite. No clone, no model, no Jira edits inside the repo.

### What you run

On Windows, from PowerShell:

```powershell
irm https://raw.githubusercontent.com/dstainton/pm-tools/main/install.ps1 | iex
```

On macOS or Linux:

```bash
pipx install git+https://github.com/dstainton/pm-tools.git
pm init
```

The Windows script is that same pair of commands, plus installing pipx and
putting it on PATH if it is missing. It installs from GitHub, not from a
local folder. It runs `pm init` only when `~/.pm/config.yaml` does not
exist. It does not download a model.

Either way the install ends with a `pm` command that works in a new
terminal, and a config file that did not exist before.

### What `pm init` does

`pm init` copies the bundled template to `~/.pm/config.yaml` and stops. It
does not talk to Jira, does not start a model, and does not open an editor.
The copy is a starting file: placeholders for the Jira URL, email, and API
token, plus the sample product and workstreams so the shape is visible.

If the file already exists, `pm init` prints the path and exits without
writing. First install is the only time the template is copied in full.

### What you fill in

Open `~/.pm/config.yaml` and replace the placeholders:

- `jira.base_url`, `jira.email`, `jira.api_token`, `jira.project`
- the `products:` and `workstreams:` entries, so they name your portfolio
  instead of the samples

A token can be `${ENV:SOME_VAR}` instead of a literal. Confluence,
SharePoint, and Teams stay disabled until you want them. The local model
stays at its default endpoint; you do not need it for `pm today`, `pm lint`,
`pm triage`, `pm doctor`, or `pm note`.

### What you run next

```text
pm doctor
```

Doctor checks the config, the Jira login, the project, the custom field
IDs, and that each workstream's components exist. When it fails, the line
says what to fix. It does not rewrite the file.

Then:

```text
pm today
```

That is the first real use. Model setup (`setup-windows-qwen-small.ps1` or
the large script) is a later, optional step for `pm report`, `pm refine`,
and `pm ready --deep`. Those scripts assume `pm` is already on PATH. They
do not install it.

### What first install does not do

- It does not run `pm update`. There is no previous version to upgrade.
- It does not migrate an old config. There isn't one.
- It does not keep `pm-helper` working. The package name changes before
  anyone installs.
- It does not write sample products into a file you already edited.

After this install, the file in `~/.pm/config.yaml` is the one `pm update`
must keep. That is the moment backward compatibility starts.

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

### 0.2 Build the first-install path

The steps are in **First install** above. This is what to add so those
steps work.

`install.ps1` at the repo root:

1. Require Python 3.9+.
2. Install pipx for the user if `pipx` is not on PATH, then `pipx ensurepath`.
3. `pipx install git+https://github.com/dstainton/pm-tools.git` (the
   published repo, not the script's folder). A `-FromPath` switch can
   install `.` for someone testing a branch.
4. Run `pm init` only when `~/.pm/config.yaml` does not exist.
5. Print two lines: open that file and fill in the Jira placeholders, then
   run `pm doctor`.

It does not download a model.

`INSTALL.md` and the README quick start become the First install section,
plus the optional model section. Delete the hand-copy paragraph. Development
stays a labeled side path: `pip install -e .` inside a clone. Editable
installs do not get `pm update`'s code upgrade; you `git pull` yourself.

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
several migrations and a file can jump more than one step.

The template `pm init` copies already contains:

```yaml
config_version: 1
```

Version 1 is the first-install shape. There is no migration from older
shapes. Legacy `*_jql` workstreams, a missing `products:` block, and the
current 0.6.0 file format do not need to keep working, because nobody has
installed. Change the template to the shape you want first-time users to
get. Delete support for the shapes you no longer want instead of migrating
them.

`core/migrations.py` ships as an empty list at version 1. The walker is
real, so the next release can append a migration, but the first install
does not run one. A user file whose `config_version` is already equal to
the template's is left byte-for-byte alone.

The first time a key is added after someone has installed, that change is
a migration: insert the key only when absent, leave every existing value
alone, bump `config_version`. `output.directory` can be in the version-1
template directly, since no installed config is pointing `report_state.json`
at the current directory yet.

### 0.4 Tests for tranche 0

No network. Extend the existing unittest style.

- `pm init` writes `~/.pm/config.yaml` with `config_version` equal to the
  template, and a second `pm init` does not change the file.
- `pm update` on that fresh file prints that the config is current and
  leaves the bytes alone, including the token the test wrote into it.
- A fixture one version behind gains only the new key from a sample
  migration, and keeps the token, products, workstreams, and a comment.
- The sample migration does not insert the template's sample product.
- Running the migration twice leaves the file unchanged the second time.
- A result that fails validation is not written.
- `pm update` refuses a path inside the package directory.
- `pm init` on an existing file mentions `pm update`.
- CLI help lists `update`. Both script names are in `pyproject.toml`.

---

## Tranche 1 — make the current tools solid

Do this after `pm update` exists. Anything that changes the template before
the first real install goes straight into the version-1 file `pm init`
copies. Anything that changes the template after that is a migration.

### 1.1 Reports land in one place

Today `commands/report.py`, `lint.py`, `ready.py`, `standup.py`, `refine.py`,
`metrics.py`, and `brief.py` write `<name>_<date>.md` into the current
directory. `output.state_file` defaults to `report_state.json` in that same
directory, which is why the README tells people to always run from `~/.pm`.

Put `output.directory: "~/.pm/out"` in the first-install template. Relative
`output.file` and `output.state_file` resolve under that directory.
`--out PATH` on a command overrides the directory for one run. No warning
about the old current-directory default, because first install never writes
that default.

### 1.2 Exit codes the gates can use

`pm doctor`, `pm workstreams check`, and `pm products check` already exit 1
on failure. `pm lint` and `pm ready` do not.

```text
pm lint --fail-on error
pm ready --fail-under 80
```

Default stays exit 0 so a quick look does not fail a shell. `pm schedule
add` can take the flags as extra arguments for the safe commands.

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

### 1.5 Vocabulary, renamed before anyone installs

Do this before the first install, in the template and the commands, with
no aliases:

| Remove | Use instead |
|--------|-------------|
| `pm standup` | `pm daily` |
| `standup:` and `standup_moved` / `standup_wip` | `daily:`, `daily_moved`, `daily_wip` |
| `missing-epic`, `linked-to-epic` | `missing-parent`, `linked-to-parent` |

Report titles say "Daily Scrum" and "Product Backlog". Do not rename
`workstream`. A rename made after the first install keeps the old name
working for one release; that rule does not apply yet.

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

1. Tranche 0.1 and 0.2 together: rename, `install.ps1`, and rewrite the
   README quick start so a new user never clones the repo.
2. Shape the version-1 template while nobody has installed: output
   directory, `pm daily`, `missing-parent`, and any other renames.
3. Tranche 0.3 and 0.4: `config_version: 1` in that template, an empty
   migration list, `pm update`, doctor notice, tests. This ships with the
   first install, ready for the next release.
4. Tranche 1.2 through 1.4 and 1.6: exit codes, load-time defaults,
   discover-fields write-if-blank, small fixes.
5. Tranche 1.7: CI.
6. Tranche 2 after the first install. New config keys from here on are
   migrations. `pm coverage` and the Sprint Goal line first.

The first install is package 0.7.0 with `config_version: 1`. Later releases
bump `config_version` only when a migration ships.

---

## Done when

- A new Windows user can install with the `install.ps1` one-liner and end
  on `pm doctor` without cloning the repo.
- `pipx install git+https://github.com/dstainton/pm-tools.git` produces
  both `pm` and `pm-tools`.
- `pm init` on a machine with no config creates `~/.pm/config.yaml` at
  `config_version` 1, including `output.directory`.
- `pm init` a second time does not change that file.
- `pm update` on that fresh file reports the config current and does not
  rewrite it.
- A later sample migration adds a missing key and leaves the token,
  products, and workstreams alone.
- `pm doctor` on a config whose version is behind exits non-zero and
  prints `pm update`.
- `pm today` runs from any directory, and a new config writes
  `report_state.json` under `~/.pm`.
- `python -m unittest discover -s tests` passes with no network.
