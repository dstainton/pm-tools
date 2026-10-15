# Phase 2C: Source evidence contract

**Status:** First implementation increment. The collectors, FTS5 index, time-series taxonomy, and optional model stage are NOT implemented by this document or the initial evidence normalization module.

## Separation of concerns

1. **Source inventory:** Exhaustively enumerate the explicitly authorized Confluence page subtree or space, and configured Jira projects, including *all* accessible issues (closed and historical included). Report exact coverage and incompleteness.
2. **Evidence records:** Preserve raw observations and version/fetch metadata separately from derived interpretations. The code in `core/discovery_records.py` establishes initial non-authoritative normalized records.
3. **Local index:** Incrementally store passages and metadata in SQLite; use FTS5 BM25 as the deterministic retrieval baseline. Search must work with no model.
4. **Taxonomy:** Model concepts, aliases, candidates, assertions, source citations, and dated observations. No product responsibility can be inferred merely from a Jira component or label.
5. **Optional interpretation:** Model analysis must use an explicit effective context-window budget, include response/system/safety reservation, and record evidence coverage. No LLM prerequisite for inventory or indexing.

## Jira contract

- Project boundaries come from configured Jira scopes, *not* only selected Epics or workstreams.
- Do not filter to active/open statuses. Include all accessible statuses and issue types, including bugs, tasks, stories, sub-tasks, Epics, and configurable higher-level types such as Initiatives when a site supports them.
- Preserve native issue type ID, type name, reported hierarchy level (when available), parent key, links, workflow status and status category. Resolve hierarchy using site/project configuration when available, not fixed issue-type names.
- `labels_direct` and `components_direct` are observed fields assigned on that issue. Parent or linked issue context must be stored separately, explicitly as inferred or inherited context, and never copied into those fields.
- Index issue summaries, descriptions, acceptance criteria where present, relevant comments, versions, and available field changelogs. Retain date/author/provenance to distinguish created, updated, resolved, and historically observed usage. History retrieval is permission- and API-dependent, and missing portions must be reported.
- Components may mean products, technical subsystems, or teams; labels may mean workstreams, releases, or something else. Only confirmed organizational conventions can promote these to operational classifications.

## Confluence contract

- Enforce configured subtree/space boundaries and capture ancestor hierarchy, title, headings, labels, links, provenance, and historical/archived signals.
- Document type and authority are observed or reviewable classifications, never inferred solely from location or recency.
- Preserve authored/effective timestamps separately from modification timestamps. A recently edited document containing a legacy term must not itself establish that the term is current.

## Temporal taxonomy

Persist term occurrences with source, authored time where knowable, extraction time, section/field, and historical-versus-current classification. Normalize monthly/quarterly term rates against document/issue volume, distinguishing first observed, last observed, emerging, stable, declining, dormant, and explicitly superseded terms. Frequency changes produce *candidates*, not definitive name changes. Keep both predecessors and successors searchable.

## Operational behaviour

Checkpoint long crawls; on resume, verify canonical source scope and cursor validity. Avoid duplicate evidence IDs and accurately report truncated, inaccessible, and unprocessed records. No source or configuration writes. Record cross-source links with citations and treat them as evidence, not proof of business ownership.

## Initial acceptance

The normalization contract preserves Jira's configured issue type and hierarchy level without requiring Initiatives, keeps directly assigned labels/components apart from parent context, retains closed status values, and represents Confluence hierarchy without treating space membership as ownership. Later PRs implement exhaustive collection, persistence, temporal trend analysis, and optional model-based evaluation.

See [tracking issue #58](https://github.com/dstainton/pm-tools/issues/58).
