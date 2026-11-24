# pm-tools Roadmap

This is an outcome-led implementation sequence, **not a calendar or a list of automatically authorized tasks**. The North Star defines why; accepted decisions and architecture constrain how; this document sets direction and dependencies. GitHub issues or direct owner assignments authorize specific implementation work.

## Status and authorization

- **Active:** current phase; its description permits planning, not unrestricted implementation.
- **Next:** intended subsequent phase; do not implement until the owner authorizes a scoped task.
- **Later:** candidate direction, not authorized implementation.
- **Deferred / Rejected:** explicitly excluded until reconsidered by the owner.
- **Current authorized work:** only the owner-assigned issue or explicit request; completion does not authorize automatically moving to another task.

**Current authorized work (2026-11-24):** owner-directed maintenance only: the documentation sync, the CLI bug fixes found by it, the Python 3.9 CI runner, and these status updates. None of it authorizes new Phase 2 implementation. Phase 2 work merged to date is #100 to #106: the ontology and benchmark contract, private benchmark candidate selection, structured evidence normalization, the classifier-first design, and the EmbeddingGemma classification prototype. The next Phase 2 slice needs a separately scoped owner assignment.

## Phase 0: Product governance (Completed)

**Outcome:** A new agent can enter this repository, understand product direction, find the next approved task, and respect the architectural and verification boundaries without relying on previous chat history.

- Establish `NORTH_STAR.md`, `ROADMAP.md`, and `AGENTS.md`.
- Record the existing architecture, not a speculative replacement.
- Establish lightweight durable decision and pull-request conventions.
- Link this guidance from `README.md`.

**Exit:** Documents agree, links work, existing behaviour is unchanged, and the owner has reviewed and accepted the governance layer.

**Exclusions:** No new CLI commands, Jira mutations, factories, schedulers, or code refactors.

## Phase 1: Whole-project backlog assessment (Completed 2026-10-14)

**Outcome:** A PM can understand what they inherited *before* workstream configuration is complete.

**Approved design:** [docs/PHASE1-ASSESSMENT.md](docs/PHASE1-ASSESSMENT.md). Default scope is open issues with completed work summarized separately, no automatic snapshot retention, and both a short terminal view and a full Markdown report. Slices 1A–1D and the closure PR (#43) merged on 2026-10-14, followed the same day by configurable status dispositions (#44) and readable status names (#45). The command is `pm assess`.

- Assess the full relevant Jira project, including issues outside configured workstream membership.
- Inventory by issue type, state, age, hierarchy, and ownership.
- Surface data-quality gaps, stale work, and unclaimed or overlapping membership.
- Distinguish missing data from zero and explain coverage and query limits.
- Produce a reviewable baseline with a prioritized, evidence-backed investigation queue.
- Reuse `pm coverage`, `pm lint`, source adapters, and existing reporting logic where appropriate; avoid duplicate calculations.

**Exit (met):** Tested synthetic scenarios include unclaimed issues, missing components/labels, stale work, partial Jira field configuration, empty results, and paginated retrieval (`tests/test_inventory.py`, `tests/test_assessment.py`, `tests/test_assess_command.py`). Reports explain what was and was not examined.

**Exclusions:** No bulk updates, model-made closure decisions, or strategic priority scores inferred from Jira hygiene.

## Phase 2: Shared PM knowledge foundation (Active; each slice needs an owner-assigned task)

**Outcome:** A reusable, local-first evidence and knowledge graph serves product discovery and future PM intelligence, not just Jira classification.

**Supporting plans:** [Classifier-first Discovery](docs/CLASSIFIER-DISCOVERY.md), [PM Knowledge Graph](docs/PM-KNOWLEDGE-GRAPH.md), [Discovery Evaluation](docs/DISCOVERY-EVALUATION.md), updated [Phase 2 discovery](docs/PHASE2-DISCOVERY.md), and [ADR 0001](docs/decisions/0001-pm-knowledge-graph-foundation.md) (strategic direction accepted; technology not selected).

**Earlier sub-phase labels:** PR titles up to #101 and the "Phase 2A/2B/2C" headings in [Discover](docs/DISCOVER.md) and [Phase 2C evidence](docs/PHASE2C-EVIDENCE.md) use the original discovery design's labels, not the 2A–2E sequence below.

**Existing foundation to retain:** checkpointed Jira/Confluence collection; APS index of 4,381 issues, 8,963 comments, 23,683 changes and 414 Confluence records; SQLite raw evidence and FTS; local model adapter. Recent semantic discovery tests produced false products and unsupported assertions. PR #98 is an unmerged, failing-CI experimental patch and is not the approved direction.

### 2A. Structured source capture and normalization (Active; partly implemented)
- Done: Jira descriptions, labels, components, issue type and parent stored separately from body text, and Confluence storage HTML and labels kept in `discovery_source_structure` (#103).
- Open: a scoped Confluence reindex of legacy flattened pages, Confluence section and table-row evidence units, and the source-fidelity gate.
- Collect all accessible records within explicitly authorized Jira project and Confluence scopes, with paging, checkpoints, counts, and completeness limits.
- Retain original payloads and separately typed descriptions, labels, components, hierarchy, comments, revisions and section structures in local SQLite; no mixed metadata/body strings.
- Segment every accessible source into independently cited evidence units; retain exact source provenance and section context.
- **Gate:** source fidelity, scope completeness and reconstructable spans; no model-based selection during ingestion.

### 2B. Hierarchical classifier-based evidence discovery (Next; initial prototype merged; depends on 2A)
- Run a prompted local broad **multi-label classifier on every evidence unit**, with no deterministic relevance prefilter or keyword quota.
- Route relevant and uncertain units to specialized taxonomy classifiers; allow multi-category routing and abstention rather than forced labels.
- Version taxonomy, prompts and models; cache results against evidence revision and classifier configuration; preserve uncertainty and reasons, not invented calibrated probabilities.
- Start with the local EmbeddingGemma embedding classifier selected in [Classifier-first Discovery](docs/CLASSIFIER-DISCOVERY.md); its prototype (#105, #106) ranks the broad taxonomy by similarity and is not yet evaluated. Compare a generative adjudicator (such as the existing local Qwen adapter) or a trained classifier only after a reviewed validation set shows the need.
- **Gate:** reviewed broad-classifier precision/recall, category confusion and missed-relevance audit; classifier failures cannot silently remove evidence.

### 2C. Classifier-guided extraction and benchmark (Next; depends on 2B)
- Done: [PM Ontology](docs/PM-ONTOLOGY.md) v0.1, the [benchmark format](docs/BENCHMARK-FORMAT.md) and deterministic evaluator (#100), and private candidate selection (#101, #102), filed at the time as "Phase 2A".
- Extract cited entities, responsibilities, boundaries, decisions and typed/temporal relationships from classifier-selected evidence, retaining alternatives and conflicting claims.
- Build and review an APS reference corpus with negative, ambiguous, obsolete and multi-entity cases; measure recall and factual support independently of JSON validity.
- Retain the previous deterministic selector only as a historical experimental baseline, not the main discovery path.
- **Gate:** reproducible source-cited extraction and human-reviewed holdout evaluation.

### 2D. Graph technology qualification and knowledge graph (Later)
- Evaluate SQLite graph-shaped tables against Neo4j GraphRAG, Graphiti and/or LlamaIndex only after classifier-guided retrieval and extraction meet quality gates.
- Reconcile canonical identities with roles and aliases without treating labels, components or co-mentions as proof of identity.
- **Gate:** benchmark-backed choice and separately owner-approved storage ADR; no graph infrastructure installation implicitly authorized.

### 2E. Discovery and guided configuration (Later)
- Provide explainable product/workstream profiles and questions based on accepted graph claims.
- Preserve existing `products:` and `workstreams:` semantics until a separately approved migration.
- **Gate:** reliable performance on APS and a different organization/project; no unapproved writes.

## Phase 3: Classification and ownership (Later)

**Outcome:** Explain proposed Jira work ownership using verified product knowledge and existing issue evidence. Preserve unassigned, ambiguous and conflicting work for human review.

**Dependency:** Phase 1 whole-project inventory and trustworthy Phase 2 graph identity/provenance.

## Phase 4: Guided remediation (Later)

**Outcome:** A PM can repair a large backlog safely in batches.

- Reviewable proposals for missing metadata, hierarchy, duplicate candidates, and out-of-date issues.
- Explicit approval, previews, conflict checks, partial execution, and audit trail.
- Keep closing, deleting, and irreversible actions behind specific human authorization.

**Dependency:** Evidence-backed classification and tested write boundaries.

## Phase 5: Continuous stewardship (Later)

**Outcome:** Backlog health improves over time rather than only during initial cleanup.

- Trend baselines for ownership, age, review state, and readiness, without incentivizing indiscriminate issue closure.
- Integrate actionable exceptions into `pm today` and relevant `pm report` profiles.
- Keep health measures distinct from delivery throughput and product outcomes.

**Dependency:** Consistent inventory, accepted graph facts and snapshot semantics.

## Future graph-enabled PM capabilities (not authorized)

- **Prioritization:** Facilitate defensible trade-offs and show assumptions, not invented numerical certainty.
- **User and stakeholder evidence:** Trace needs, feedback, and decisions to planned work.
- **Strategy and outcomes:** Connect product goals and measurable results to work without treating delivery metrics as outcomes.
- **Dependencies and forecasting:** Make cross-team commitments and scenarios visible with documented uncertainty.
- **Risk and decision integration:** Improve read-only support for existing register formats without assuming undocumented Confluence database-row APIs.

Order and scope of these opportunities require deliberate owner review after the backlog-recovery foundation.

## How this roadmap changes

Propose the motivation, affected users, alternatives, dependencies, and implications in a PR or issue. The owner approves material changes. An agent may report an opportunity or recommend a new phase, but cannot mark it Active or implement it unilaterally. Do not mark exit criteria complete without verified evidence.
