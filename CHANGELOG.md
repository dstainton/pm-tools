# Changelog

## 0.5.0 - 2026-09-03

### Jira writes

- One write path: preview the payload, confirm once (`--yes` skips the
  prompt, `--dry-run` stops after preview), send, append a line to
  `~/.pm/write-log.jsonl`. Nothing on this path runs on a schedule.
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
  so the PM and the BA see the same queues), otherwise `~/.pm`. Cache,
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
  (default `~/.pm/cache`) for `cache.ttl_seconds` (default 300). `--cached`
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
- Numbered actions are written to `today.state_file` (default `~/.pm/today.json`).
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
