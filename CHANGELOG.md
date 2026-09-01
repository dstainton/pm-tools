# Changelog

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
