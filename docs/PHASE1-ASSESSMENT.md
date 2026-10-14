# Phase 1 design: Whole-project backlog assessment

**Status:** Approved design choices recorded 2026-10-14. Implementation not yet authorized.

**Authority:** [North Star](../NORTH_STAR.md) and [Roadmap](../ROADMAP.md). The source code and existing CLI remain unchanged until a bounded implementation task is approved.

## Outcome

A product manager can assess an inherited Jira project even when issues lack components, labels, estimates, or configured workstream membership. The assessment makes its coverage and uncertainties explicit, provides an actionable investigation queue, and never changes Jira.

## Approved product decisions

1. **Scope: open.** All non-completed issues in the selected Jira project(s), including items outside configured workstreams. Completed work is summarized separately where reliable data is available; it is not part of the open-work assessment population. Jira status categories and configured conventions should determine completion, not arbitrary English status names. Show explicit project keys and query scope.
2. **Retention: none.** No automatic history or dated local snapshot store in Phase 1. An on-demand current report may be exported, but is not silently persisted as a history database. Trends and longitudinal comparisons remain Phase 4.
3. **Output: both.** Concise, actionable terminal summary plus a full Markdown assessment report with linked issue evidence and completeness information. The command must not overwhelm the terminal with an undifferentiated issue dump.

## Proposed report model

- **Scope and completeness:** project(s), query, retrieval time, issue counts, truncation/error state, and unavailable fields.
- **Inventory:** open issues by type, Jira status category, age bands, and workstream coverage; separate high-level completed-work summary when supported.
- **Ownership:** unclaimed, multiply claimed, missing Jira components, and unassigned people as distinct conditions.
- **Hierarchy:** missing or ambiguous parent/Epic relationships appropriate to the issue type.
- **Currency:** age since creation and last Jira update, explicitly *not* a claim of meaningful recent human review.
- **Quality:** deterministic rule findings calibrated to work maturity and configured conventions. Missing estimate is not equivalent to zero points.
- **Delivery attention:** blocked, overdue, and unexpectedly stalled active work.
- **Investigation queue:** a short ranked list of review categories, each with rationale, affected counts, and drill-down links. Review order is not a product-value priority.

No composite backlog-health score or model-generated issue priority score in Phase 1.

## Technical approach

Reuse `core/sources.py` for Jira search, `core/workstreams.py` for membership, and existing coverage/lint analysis where semantically appropriate. A pure, independently testable assessment analysis module may be introduced in a later slice. Avoid a second Jira client and duplicate normalization pipelines.

The existing `sources.search_issues()` uses `nextPageToken` pagination but defaults to `jira.max_results` (often 100) unless `max_items=0` is specified. `sources.fetch_jira_detailed()` currently delegates to this capped default when no `max_results` is supplied. `commands/coverage.py` uses that default when listing open issues. Do not equate a successful capped request with complete retrieval.

The initial inventory must use project-based discovery rather than a workstream-filtered JQL, and report a trustworthy completeness state. A missing or inaccessible project is an explicit error, not an empty backlog.

## Retrieval contract (Slice 1A)

Design and implement a reusable, read-only, project-wide open-issue inventory operation. It must report:

- project key(s), effective JQL and query selection rationale;
- retrieval start/completion time and count of returned unique issues;
- completeness status: `complete`, `partial`, or `failed`, with reason;
- absence/availability of requested fields where determinable;
- consistent handling of permissions, network failures, pagination limits, duplicate keys and unexpected empty pages.

The retrieval API must not silently truncate at `jira.max_results`. Where an underlying source cannot prove completeness, say so rather than claim full coverage. Respect explicit user/project scope and Jira permissions.

Do not change existing `search_issues` default semantics globally unless tests demonstrate compatibility across callers. Prefer an explicit unlimited mode or separate wrapper for assessment to avoid accidental expensive scans in everyday commands.

## Phase 1 planned slices

- **1A: Complete inventory and completeness contract.** Read-only retrieval, metadata, and focused tests. No `pm assess` command or report.
- **1B: Deterministic analysis.** Pure functions for scope, age, hierarchy, metadata gaps, and ownership; exercise synthetic fixtures.
- **1C: `pm assess` and presentation.** Concise terminal plus detailed Markdown output with accurate source links.
- **1D: Investigation queue and end-to-end hardening.** Prioritized evidence-backed review groupings and broad regression coverage.

Authorization of this design does not authorize any of the implementation slices.

## Acceptance tests for Phase 1

- More than 100 matching open issues are retrieved without silent truncation.
- Open issues without labels, components, estimates, or workstream membership remain in scope.
- No configured workstreams is a supported case.
- Empty complete results differ from failed or partial retrieval.
- Duplicate pages/keys and interrupted pagination do not produce misleading counts or completeness.
- Missing field configuration is visible; unknown values are not represented as zero.
- Tested age calculations use a fixed clock and representative issue types.
- Terminal and Markdown views use identical underlying facts.
- No Jira writes or model calls.
- Existing tests and supported CI operating systems pass.

## Proposed first implementation issue: Phase 1A

**Title:** Build complete open-issue Jira inventory with explicit retrieval completeness

**Problem:** Existing callers can silently hit a configured search result cap; a new PM cannot trust an assessment based on an incomplete inventory.

**In scope:** Inspect current Jira search and detailed-issue normalization; implement a reusable, explicitly uncapped read-only query for open issues in a named configured project; return normalized issue data plus completeness metadata; add deterministic unit tests covering pagination, caps, errors, duplicates, empty pages, and missing fields.

**Out of scope:** New `pm assess` CLI command, report formatting, classification, issue ranking, historical snapshots, model calls, data mutation, broad source-layer rewrites, and unrelated `pm coverage` behaviour changes.

**Acceptance:** Full-project open scan can safely exceed 100 results; every run supplies effective scope, count, and completeness/reason; failures cannot masquerade as empty projects; all relevant tests and the full available CI matrix pass.

**Implementation guardrail:** No speculative new persistence service, queue, or model. If Jira's API does not expose a reliable completeness signal, document the limitation and adjust the result status rather than inventing one.
