# Changelog

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
