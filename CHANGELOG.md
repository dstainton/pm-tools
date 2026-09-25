# Changelog

## 0.12.0 - 2026-09-25

- The weekly report is organised by Epic. Citations are Jira keys and page
  titles. Confluence pages changed in the same window are included, and a
  decision log, risk register, or ADR list can be configured as a register.
- Prompts, queries, and team conventions are configurable. Defaults stay in
  the tool, so an unconfigured install behaves as before. See
  `docs/CUSTOMISING.md`.
- `pm update` installs the new program and then runs the config migration
  in a new process, so the steps that shipped with that program are applied
  on the same run.
- `pm report`, `pm brief`, `pm release-notes`, `pm metrics`, and `pm warm`
  take `--audience pm|leadership|partner`. Each audience has its own file
  and memory. `pages.scope: space` reads every changed page in a workstream
  space; set `pages.scope: labelled` to keep the previous label filter
  (`config_version` 6, applied by `pm update`).
- A product may set `confluence_space`. SharePoint files are listed by title
  in Documentation changed and Sources. `pm warm` runs review, page
  summaries (including changed register entries), the report, then the inbox.
- The shipped model is Ollama at `http://127.0.0.1:11434/v1/chat/completions`
  with `qwen3:4b` (about 2.5 GB). A 32 GB machine is pointed at a 27B
  model when one is being served. An endpoint or name you already set is
  left alone, including the previous llama.cpp default.
- Confluence can live in one space. `confluence.space` and `root_title`
  (or `root_page_id`) name the team page. A product or workstream may set
  `confluence_page` or `confluence_page_id` so reads stay under that folder.
  A register may set `under` when the same title exists in more than one
  folder, and `split: label` to file each entry by the product or workstream
  abbreviation on its labels. A page that matches more than one register is
  listed once: on the workstream, then the product, then the portfolio. A
  workstream `confluence_space` with no page still reads the whole space.
  `pm setup --section confluence` writes the shared space and folder titles
  when they are blank. `pm doctor` checks those folders. `pm products add`
  and `pm workstreams add` take `--confluence-page`. `pm update` does not
  insert these keys.
- Several teams can share one Confluence space. `confluence.team_page` (or
  `team_page_id`) names your team's top page, and `confluence.space` takes
  the space name as well as its key. Under the team page, a page or folder
  whose title names a product or workstream is used without any setting,
  for example "Secure Data Exchange (SDX)"; `confluence_page: false` turns
  that off for one entry. A workstream folder is looked for inside its
  product folder first. `pm report` lists product-folder pages under the
  product and pages in no folder once, as team pages. A register with no
  `under` looks in its own folder, then the product folder, then directly
  under the team page. `pm setup` writes `team_page`
  (`--confluence-team-page`; `--confluence-root` still works) and shows the
  folders it found. `pm doctor` shows the space key, the team page, and how
  each folder was found, and warns when a workstream reads the whole shared
  space.
- `pm setup` probes the local servers in `local_models.endpoints`, lists
  the models each one is serving, and recommends one that fits installed
  RAM (`config_version` 7). When none answer, it can install Ollama or
  Lemonade Server after you type `yes`. `model.api_key` is an optional
  bearer token for that server. `pm update` inserts `local_models:` only
  when the block is missing.

## 0.11.0 - 2026-09-24

- `pm setup` fills a blank config one step at a time and will not replace a
  value that is already set. `pm init` remains the hand-edited path.
- `pm today` gives one number per issue. An ended Sprint is an alert, not
  the current Sprint Goal. A suggested due date uses the Sprint end.
  `pm do` says when the numbered list was written.
- `pm today --all` is the triage queue. `pm triage` says so.
- Issue links use the key as the link text. Lint severity is a word.
  `--plain` and `NO_COLOR` drop glyphs and terminal links.
- `pm report` and `pm brief` take `--since` and `--sprint`. A named window
  does not move the last-run memory. Confluence pages use a `pages:` budget
  (`config_version` 5) instead of the 180-character issue detail cap.
- `pm show KEY` prints one issue. `pm mcp` is a read-only stdio server and
  stays off until `--yes-i-understand`.
- Landing dates need three finished items in the window. `pm doctor` keeps
  the status word when a config path is long.

## 0.10.1 - 2026-09-23

- `pm today` shows each Sprint Goal once. Jira's board search returns every
  board whose filter mentions the project, so the same active sprint was
  printed once per board.
- The sprint name is on its own line. Each numbered goal is on its own line,
  and a wrapped line starts under the first word. The indent includes the
  space after the number, so the continuation is not one column short.
- Issue keys on that screen are links when stdout is a terminal. Windows
  Terminal, which hosts PowerShell, opens the Jira issue from the key. A
  pipe stays plain text.

## 0.10.0 - 2026-09-23

- `pm report`, `pm brief`, `pm daily`, and `pm release-notes` read Jira
  comments inside the window that command already uses. The whole thread
  is not kept. `pm report` uses the time of the last report, or 7 days on
  the first run and when an older state file has no timestamp. `pm brief`
  uses the last time that audience was briefed. `pm daily` uses `--days`.
  `pm release-notes` uses `--since`, or the newest few comments when only
  a fixVersion is given. `pm triage` quotes the comment that named you.
- Caps, in the `comments` block: 3 comments per issue, 25 issues per
  workstream, 240 characters each, and 6000 characters of comment text in
  one model section. `comments.enabled: false` turns that fetch off for
  report, brief, daily, and release notes. `pm triage` still reads
  comments so it can notice a mention. `pm lint`, `pm ready`, `pm review`,
  `pm refine`, `pm metrics`, and `pm coverage` stay on the ticket fields
  they already use.
- `config_version` 4. `pm update` inserts the `comments` block when it is
  missing. A value you already set, including `enabled: false`, is not
  replaced.

## 0.9.1 - 2026-09-23

- `pm update` reinstalls a pipx install from git. `pipx upgrade` was leaving
  the old 0.9.0 files in place when the version number did not change, so
  the Teams-webhook fix never reached `pm products`.
- Windows `install.ps1` reinstalls with `pipx install --force` when pm-tools
  is already installed, for the same reason.

## 0.9.0 - 2026-09-23

### Tranche 3

- Windows `install.ps1` runs the `pm.exe` pipx installed, not whatever `pm`
  is first on PATH. An older `pm.exe` in Python's Scripts folder, left by
  `pm-helper`, is removed.
- A `${ENV:VAR}` inside a block with `enabled: false` may be unset. The
  Teams webhook in the template no longer stops `pm products` when
  `PM_TEAMS_WEBHOOK` is not set. Turning Teams on still requires it.
- `pm metrics` classifies Done and in-flight from the project's status
  category, using the status id on the changelog. A workflow named Complete
  or Shipped counts. The old English name lists remain only when the status
  list cannot be loaded. Sprint scope change matches sprint ids, so Sprint
  42 no longer matches Sprint 421.
- Blocked is configuration. `blocked.statuses` and `blocked.labels` match
  exactly. The default is a status named Blocked and a label named blocked.
  `Unblocked` does not count. `pm workstreams check` warns when a configured
  status is not a status on the project.
- `pm triage` treats an `@mention` as the account id on the comment, and
  falls back to a whole-word name match. A link counts as blocked-by only
  in that direction, not when this issue is the one doing the blocking.
- `pm brief` loads risk pages by the Confluence label, not by the word
  "risk" in the title.
- `pm lint` flags a title that is too short or that is only a vague word.
  It no longer flags a clear title because it contains "fix". Acceptance
  criteria count when the field is filled, or the description has an
  acceptance-criteria heading or a Given/When/Then scenario. The word
  "when" on its own does not. Both findings point at `pm review`.
- Model replies are cached under the fetch cache, keyed on the prompt.
  `--cached` and `--refresh` apply. A second `pm inbox` on an unchanged
  inbox does not call the model. `model.total_timeout` caps a whole run.
  A multi-call command prints the call count and an estimate from the
  round trip `pm doctor` last measured.
- `pm warm` fills that cache. It is read-only. `pm schedule add warm --at
  07:00` runs it on the scheduler that already ships. There is no
  background service.

### Config

- User data lives in `~/.pm-tools`: the config, the cache, output files,
  `today.json`, the write log, and `schedule.json`. The Windows setup
  scripts keep llama.cpp and the model files there too. Nothing was
  installed under `~/.pm`, so there is no move.
- `config_version` 3. `pm update` inserts `blocked.statuses`,
  `blocked.labels`, `model.total_timeout`, and `cache.model_ttl_seconds`
  when those keys are missing. A value you already set is not replaced.
  Products and workstreams are left alone.

## 0.8.0 - 2026-09-23

### Tranche 2

- `pm coverage` lists open issues no workstream claims, open issues two or
  more workstreams claim, and Jira components no workstream names. It exits
  1 when unclaimed work exists. `pm schedule add coverage` is allowed.
- `pm today` adds a Sprint Goal risk line when the active sprint has an end
  date: "Sprint ends in N days. Not started: K. Blocked: M." It does not
  name an issue as being on the goal path.
- Optional `product_goal:` on a product. `pm products add --goal` sets it.
  `pm report` and `pm brief` print the sentence under the product heading.
  Empty means the line is omitted. The migration does not add it to existing
  products.
- `ready.blocking_criteria` may include `too-big-for-a-sprint`. It is off
  unless listed. The threshold is `ready.max_points` (default 8). An item
  with no estimate does not also fail that rule.
- `pm ready` calls the result a team working agreement. The pass/fail table
  stays.
- Optional `definition_of_done:` on the config or on a product. `pm report`
  prints it in the Increment section. A line may set `label:`, and then
  `pm ready` warns when a Done item lacks that label. Other lines are
  reminders. There is no `pm done` command.
- `pm metrics --sprint` reports forecast points at the start, points done,
  points added after the start, and items carried in.
- `pm release-notes --since DATE` and `--version NAME` list done issues,
  grouped by product and workstream. The model drafts prose when it is up
  and does not choose the issues. Otherwise the command says the model was
  skipped.
- `pm inbox edit N` corrects the title, workstream, or acceptance criteria
  in `inbox.json` before create. Stored edits win over the model suggestion.

### Config

- `config_version` 2. `pm update` inserts `ready.max_points: 8` when that
  key is missing and leaves the token, products, and workstreams alone.
  A `max_points` you already set is not replaced.

## 0.7.0 - 2026-09-22

### pm-tools

- The package name is `pm-tools`. The daily command is still `pm`. `pm-tools`
  calls the same program.
- First install is `install.ps1` on Windows, or `pipx install` of the GitHub
  repo elsewhere, then `pm init`. The Qwen setup scripts no longer install
  the CLI.
- `pm update` upgrades the installed program, then migrates `~/.pm-tools/config.yaml`.
  It never replaces that file. `config_version: 1` is the shape `pm init`
  writes. There is no migration from older shapes, because this is the first
  install.
- `pm init` on an existing file leaves it alone and points at `pm update`.
  `pm init --force` is the only replace path.

### The first config

- Reports, lint, ready, daily, refine, metrics, and brief files go to
  `output.directory` (`~/.pm-tools/out`), including `report_state.json`.
- `pm daily` replaces `pm standup`. Scopes are `daily_moved` and `daily_wip`.
- Lint says `missing-parent`. The ready criterion is `linked-to-parent`.
- `pm lint --fail-on` and `pm ready --fail-under` exit non-zero. The default
  is still success. `pm schedule add` can pass those flags through.
- Missing config sections are filled in memory. A section of the wrong type
  is named when the file loads.
- `pm doctor` fails when `config_version` is behind the installed template.
  `pm doctor --discover-fields --yes` writes a field ID only when that ID
  is blank.
- `--workstream` and `--product` accept the full name as well as the abbreviation.
- SharePoint search queries escape apostrophes. A Jira 429 waits for
  `Retry-After` and tries once more.
- Commands print UTF-8, so a Windows console on cp1252 does not stop at an
  arrow or a warning mark.
- Help and the README name `--out`, full product and workstream names, and
  what `pm review` and `pm doctor --discover-fields --yes` actually do.
- Stale in-progress items use the last status change when a changelog is
  present. `refactor` and `test` are vague only as a whole title.
- Items that drop out of the weekly report keep their reference tag.
- Confluence search is still the v1 content API.

## 0.6.0 - 2026-09-03

### `pm metrics`

- Deterministic delivery numbers per product and workstream: throughput,
  cycle time (median / 85th percentile), aging WIP, sprint scope change,
  forecast accuracy, and a plain landing date.
- `--weeks` and `--json`. The weekly report appends the same table.

### `pm brief`

- Prep is one page per audience, with memory of the last time you met
  *that* audience. Decisions needed and recent risks sit under each product.
- `--debrief notes.md` extracts decisions and actions. `--apply` creates
  the action tickets after a preview.

### `pm publish` and `pm schedule`

- Confluence and/or Teams, via `publish:` (enable one, the other, or both).
  `pm report --publish` and `pm publish FILE` use the shared write path.
- `pm schedule add` only accepts read-only commands. Windows gets a Task
  Scheduler shim; elsewhere a crontab snippet is written.

## 0.5.0 - 2026-09-03

### Jira writes

- One write path: preview the payload, confirm once (`--yes` skips the
  prompt, `--dry-run` stops after preview), send, append a line to
  `~/.pm-tools/write-log.jsonl`. Nothing on this path runs on a schedule.
- Non-interactive runs (tests, scripts, a missing TTY) must pass `--yes`
  or `--dry-run`. A hang waiting for input is refused.
- `pm do N` now writes after that confirmation.

### Decisions stick

- `pm lint --snooze KEY --until … --why "…"` hides a finding until a date
  (`YYYY-MM-DD`, `14d`, `2w`, or `next-sprint`).
- `pm lint --accept KEY --why "…"` hides it until `--all`.
- `pm lint --assign KEY --to <person> --why "…"` hides it from the default
  lint, lands it in that person's refine queue, and writes the Jira
  assignee. A person, not a role.
- Memory lives in `state.shared_path` when that is set (a synced folder
  so the PM and the BA see the same queues), otherwise `~/.pm-tools`. Cache,
  write-log and `today.json` stay local.

### `pm triage`

- Deterministic "waiting on me" queue, grouped by product, numbered
  actions. `--apply N` uses the shared write path.
- Tunable in `triage:`: unassigned in the Sprint, blocked (status / label
  / blocked-by link), mentions, new bugs, untouched in-sprint work, overdue.

### `pm refine`

- Drafts titles and acceptance criteria (model, batches of 8) and a
  median estimate from closed similar stories. Writes `refine_<ws>_<date>.md`.
- `--apply` parses the file and writes only the fields you left. A deleted
  field is not written.
- `pm review` is a deprecated alias for one release.

### `pm note` / `pm inbox`

- Capture is instant and offline. `pm inbox` lists with a model filing
  suggestion. `pm inbox create N` / `drop N`. Create uses the write path.

### Team project

- A Jira project is the team; components name products and workstreams.
  `pm products check` verifies components in `jira.project`, not a
  one-project-per-product mapping.

## 0.4.0 - 2026-09-03

### Products above workstreams

- New `products:` block. A product is a name, an abbreviation, and optional
  defaults (Jira project, scopes). Each workstream may set `product: <abbrev>`.
  A workstream with no product lands in an implicit Unassigned product, so
  existing configs keep working.
- `pm products` — `list`, `add`, `remove`, `check`. Same comment-preserving
  edit as `pm workstreams`. Removing a product that workstreams still name is
  refused.
- `--product` / `-p` on every config-driven command, and it composes with
  `--workstream`. A typo fails with the list of valid names.
- Workstream `project` now inherits from its product, then `jira.project`.
  Product `scopes:` sit between the global block and the workstream override.
- Weekly report gains a portfolio summary, then a section per product, then
  per workstream. Lint / ready / standup summary tables gain a Product column.
- Bundled template wraps SDX, APS and ITK in product "Integration Platform"
  (`IP`). The product abbrev is not `APS` — that already names a workstream.

### Fetch cache and `pm doctor`

- Jira searches (and approximate counts) are cached under `cache.path`
  (default `~/.pm-tools/cache`) for `cache.ttl_seconds` (default 300). `--cached`
  reuses a hit even if it is stale; `--refresh` ignores the cache. The two
  flags cannot be combined.
- `pm doctor` verifies config, Jira credentials, every project in play,
  custom-field IDs, membership counts (including unclaimed open work), the
  local model (thinking off), and the cache. `--discover-fields` lists
  likely field IDs and prints a YAML snippet; it does not write the file.

### `pm today` and `pm do`

- `pm today` is the habit command: Sprint Goal (when the Agile API is there),
  a capped NEEDS YOU list, movement since yesterday, aging in-progress work,
  and refinement gaps against the team's ready agreement.
- Numbered actions are written to `today.state_file` (default `~/.pm-tools/today.json`).
- `pm do N` prints the exact Jira payload that action would send, then stops.
  Writes are not enabled in this release.

## 0.3.1 - 2026-09-03

### Prompts and sampling for Qwen3.8-27B Q3_K_M

- Report and review prompts rewritten for Qwen3.8 in instruct (non-thinking)
  mode: short numbered rules, a fill-in heading skeleton, and one worked JSON
  example. Format goes last so a 3-bit quant does not lose it.
- Every model call turns thinking off (`chat_template_kwargs.enable_thinking:
  false` plus a `/no_think` prefix). Leftover `<think>` blocks are stripped
  before JSON is parsed.
- Default sampling matches Qwen's instruct profile, with a cooler
  `json_temperature` of 0.2 for `pm review`. `review.batch_size` dropped from
  15 to 8; report material is capped so the prompt stays short.
- `setup-windows-qwen-large.ps1` now downloads Qwen3.8-27B Q3_K_M and starts
  llama.cpp with `--jinja --reasoning-budget 0`. The small-model script uses
  the same thinking-off flags.

## 0.3.0 - 2026-09-03

### Jira Cloud search API (breaking, upstream)

- Every Jira fetch now uses `/rest/api/3/search/jql` with `nextPageToken`
  paging. Atlassian has removed the `/rest/api/3/search` endpoint the previous
  versions called, so no command worked against a live Jira Cloud site.
- Item fetches page instead of stopping at `max_results`. `jira.max_results` is
  now the cap on how much one query pulls back, with `jira.page_size` per
  request.
- Searches are sent as POST, so a long generated query cannot exceed the URL
  length limit.
- Added `approximate-count`, `myself`, project component and per-issue changelog
  calls, used by `pm workstreams check`.

### Workstreams without JQL

- A workstream is now `name`, `abbrev` and `components`. `jira.project` names the
  project once for all of them.
- Membership is resolved from Jira in two parts: an issue's **own** Component,
  and inheritance from its parent. This adds cases the previous `parentEpic`
  scope missed — a Story tagged directly under an Epic belonging to no
  workstream, the Sub-tasks of such a Story, an issue with no parent at all, and
  a workstream with no tagged Epic, which used to be skipped entirely.
- New `membership:` block: `epic_types`, `inherit_from_parent`,
  `child_component_wins`, `max_parent_keys`.
- New `scopes:` block replaces the six `*_jql` strings per workstream with plain
  options (`status`, `sprint`, `assignee`, `types`, `exclude_types`,
  `labels_any`, `labels_none`, day windows, and `extra_jql` as an escape hatch).
  Overridable globally or per workstream.
- Confluence queries are built from `confluence_space` and `confluence_labels`.
- Config is validated when it loads: unknown options, mistyped values, duplicate
  abbreviations and workstreams with no way to be found all fail with the fix
  named.
- Legacy configs are unchanged in behaviour: `jira_project`/`epic_components`
  are read as aliases, `*_jql` values still work (as an extra filter on a
  Component-based workstream, or as the whole query without one).

### New command

- `pm workstreams` — `list`, `add`, `remove`, `check`. `add` and `remove` rewrite
  the config in place, preserving comments, and refuse to write a file that
  would not load. `check` verifies Component names against the project,
  suggests close matches for typos, counts what each scope resolves to, and
  prints the generated JQL with `--show-jql`. Exits non-zero on problems.

### Fixes

- `pm report` crashed with `AttributeError` before its first fetch: a local
  variable shadowed the `workstreams` module.
- `pm standup` falls back to the per-issue changelog endpoint on sites that do
  not expand changelogs on search, instead of reporting no movement.

### Tests

- 99 tests, no network required. `tests/fake_jira.py` stands in for Jira and the
  local model, answering searches by evaluating the generated JQL against an
  in-memory backlog, so membership resolution is asserted for real.
- End-to-end coverage of every command through the CLI, including paging,
  component inheritance, `child_component_wins`, config editing and the
  Definition-of-Ready gate.

### Docs

- `docs/FEATURE_PROPOSALS.md`: what the tool does, what was broken, and a
  prioritised list of proposed features.

## 0.2.0 - 2026-08-24

### Jira workstream inheritance

- Added Epic-component workstream scoping for a shared Jira project.
- Workstreams can now declare `jira_project` and `epic_components`.
- `pm` resolves matching Epics once per workstream and uses `parentEpic` to
  include Stories, Tasks, Bugs, and nested Sub-tasks without copying Components
  to every child issue.
- `jira_jql`, `roadmap_jql`, `lint_jql`, `review_jql`, `ready_jql`, and standup
  JQL are now interpreted as additional filters when Epic-component mode is in
  use.
- Legacy direct-JQL workstreams remain supported unchanged.

### Command behaviour

- `report`: sprint scope is Epic descendants; roadmap scope is the Epics.
- `lint` and `review`: scope includes workstream Epics and their descendants.
- `ready` and `standup`: scope includes Epic descendants.
- Child issues no longer receive `missing-component` findings when their
  workstream is inherited from the Epic.

### Local model setup

- Default model endpoint changed to llama.cpp on `127.0.0.1:8080` with alias
  `qwen-local`.
- Added Windows setup scripts for a small Qwen3-4B Q4_K_M model and the larger
  Qwen3.8-27B Q4_K_M model.

### Tests

- Added unit coverage for JQL resolution, Epic caching, pagination, legacy JQL,
  standup substitutions, and inherited-component lint/readiness behaviour.
