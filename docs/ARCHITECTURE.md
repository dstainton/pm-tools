# Architecture baseline

This describes the present repository at a high level. It is not authorization to introduce a replacement architecture.

## Current shape

- `pm.py`: CLI entry point, argument parsing, and command routing.
- `commands/`: user-facing workflows such as `today`, `triage`, `lint`, `ready`, `refine`, `coverage`, `metrics`, `report`, and `brief`.
- `core/`: shared Jira and Confluence access, workstream membership and filters, issue normalization, deterministic metrics, register gathering, rendering, and configuration functions.
- `tests/`: automated regression and behaviour tests.
- `docs/`: user guidance, prompt/query customization, and now the baseline governance documents.

Consult the implementation before assuming precise ownership of a particular function; module boundaries can evolve.

## Existing design boundaries

### Scope and data completeness

`core/workstreams.py` determines configured workstream membership through anchors, Epics, component rules, and associated issue selectors. `commands/coverage.py` scans open issues to identify unclaimed and overlapping work, and unreferenced components.

Workstream-filtered views can omit the very legacy issues a new PM needs to discover. A whole-project assessment must therefore record its scan scope explicitly and must not treat workstream-filtered results as a complete inventory.

### Facts, models, and reporting

`commands/lint.py`, `commands/ready.py`, and `core/metrics.py` provide deterministic checks and arithmetic. `commands/review.py`, `commands/refine.py`, and some report paths use model-assisted text analysis or generation. Preserve the distinction between source facts, numerical results, and model suggestions.

Report and metric renderers are shared by multiple command paths. A change to shared terminology, fiscal labels, or data fields requires a review of all affected entry points and tests.

### External systems and changes

Jira is a source of work-item records; Confluence and SharePoint are optional document sources. Register gathering currently works primarily with Confluence page hierarchies; native Confluence database rows are not equivalent to child pages.

CLI operations should remain read-only by default. Existing approved-write workflows must preserve preview and confirmation semantics. Any proposed bulk write process requires additional conflict checks and an auditable review plan.

### Local model and configuration

The tool supports local-model workflows and user-specific Jira fields, filters, Confluence configuration, and saved state. Do not assume Jira custom-field IDs or workstream definitions are portable between installations. A valid field identifier alone does not prove that it holds useful data for that team.

## Proposed knowledge graph target, not the current architecture

See [PM Knowledge Graph](PM-KNOWLEDGE-GRAPH.md), [Discovery Evaluation](DISCOVERY-EVALUATION.md) and proposed [ADR 0001](decisions/0001-pm-knowledge-graph-foundation.md). The intended shared knowledge infrastructure will preserve structured evidence, extract source-level claims, reconcile identities/time/contradictions and support GraphRAG for future PM commands. Neo4j GraphRAG is a candidate, not an installed or accepted service.

The current offline index flattens Confluence section boundaries and combines Jira metadata with issue description text. Current entity discovery also mistakes generic Jira components for product identities. Those are known experimental limitations, not desired invariants. Retain existing stable collectors and CLI contracts while the redesign is planned. The current product/relationship graph is not an accepted source of truth.

## Guidelines for evolution

1. Reuse existing retrieval and normalization before building new adapters.
2. Prefer a consistent inventory and explicit coverage metadata when introducing assessment features.
3. Keep calculations independent of text-generation prompts.
4. Keep a new feature's data model and migration as small as possible.
5. Validate existing command compatibility on Python versions and operating systems exercised by CI.
6. Record architecture changes in a reviewed decision if they materially change boundaries.

This file should be updated when verified implementation changes make this baseline inaccurate.
