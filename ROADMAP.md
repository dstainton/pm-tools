# pm-tools Roadmap

This is an outcome-led implementation sequence, **not a calendar or a list of automatically authorized tasks**. The North Star defines why; accepted decisions and architecture constrain how; this document sets direction and dependencies. GitHub issues or direct owner assignments authorize specific implementation work.

## Status and authorization

- **Active:** current phase; its description permits planning, not unrestricted implementation.
- **Next:** intended subsequent phase; do not implement until the owner authorizes a scoped task.
- **Later:** candidate direction, not authorized implementation.
- **Deferred / Rejected:** explicitly excluded until reconsidered by the owner.
- **Current authorized work:** only the owner-assigned issue or explicit request; completion does not authorize automatically moving to another task.

**Current authorized slice (2026-10-16):** documentation alignment for the reusable PM knowledge graph and evaluation roadmap only. No graph infrastructure, indexing redesign, installation or feature implementation is authorized by this documentation update. The historical Phase 1 closure statement below describes an earlier plan and requires separate status verification.

## Phase 0: Product governance (Completed)

**Outcome:** A new agent can enter this repository, understand product direction, find the next approved task, and respect the architectural and verification boundaries without relying on previous chat history.

- Establish `NORTH_STAR.md`, `ROADMAP.md`, and `AGENTS.md`.
- Record the existing architecture, not a speculative replacement.
- Establish lightweight durable decision and pull-request conventions.
- Link this guidance from `README.md`.

**Exit:** Documents agree, links work, existing behaviour is unchanged, and the owner has reviewed and accepted the governance layer.

**Exclusions:** No new CLI commands, Jira mutations, factories, schedulers, or code refactors.

## Phase 1: Whole-project backlog assessment (1A–1D merged; closure in review)

**Outcome:** A PM can understand what they inherited *before* workstream configuration is complete.

**Approved design:** [docs/PHASE1-ASSESSMENT.md](docs/PHASE1-ASSESSMENT.md). Default scope is open issues with completed work summarized separately, no automatic snapshot retention, and both a short terminal view and a full Markdown report. Implementation slices 1A–1D have been merged. The final closure PR completes the separately labelled approximate completed-work summary, transparent queue distribution, and acceptance review.

- Assess the full relevant Jira project, including issues outside configured workstream membership.
- Inventory by issue type, state, age, hierarchy, and ownership.
- Surface data-quality gaps, stale work, and unclaimed or overlapping membership.
- Distinguish missing data from zero and explain coverage and query limits.
- Produce a reviewable baseline with a prioritized, evidence-backed investigation queue.
- Reuse `pm coverage`, `pm lint`, source adapters, and existing reporting logic where appropriate; avoid duplicate calculations.

**Exit, subject to final closure PR CI and owner acceptance:** Tested synthetic scenarios include unclaimed issues, missing components/labels, stale work, partial Jira field configuration, empty results, and paginated retrieval. Reports explain what was and was not examined.

**Exclusions:** No bulk updates, model-made closure decisions, or strategic priority scores inferred from Jira hygiene.

## Phase 2: Shared PM knowledge foundation (Current planning; implementation not authorized)

**Outcome:** A reusable, local-first evidence and knowledge graph serves product discovery and future PM intelligence, not just Jira classification.

**Supporting plans:** [PM Knowledge Graph](docs/PM-KNOWLEDGE-GRAPH.md), [Discovery Evaluation](docs/DISCOVERY-EVALUATION.md), updated [Phase 2 discovery](docs/PHASE2-DISCOVERY.md), and [proposed decision ADR 0001](docs/decisions/0001-pm-knowledge-graph-foundation.md).

**Existing foundation to retain:** checkpointed Jira/Confluence collection; APS index of 4,381 issues, 8,963 comments, 23,683 changes and 414 Confluence records; SQLite raw evidence and FTS; local model adapter. Recent semantic discovery tests produced false products and unsupported assertions. PR #98 is an unmerged, failing-CI experimental patch and is not the approved direction.

### 2A. Domain model, benchmark and evaluation (Next)
- Define products, services, capabilities, workstreams, teams, initiatives, decisions, Jira components, source records and typed/temporal claims as separate concepts. Multiple roles may apply to a single entity.
- Build a frozen, human-reviewed APS reference corpus and negative cases, with withheld evaluation samples and accuracy gates.
- Qualify the local model on known, small source sections before attempting large-scale extraction.
- **Gate:** accepted ontology, provenance contract and evaluation plan.

### 2B. Structured evidence normalization (Next; depends on 2A)
- Preserve Confluence headings, tables, section boundaries and context; never flatten adjacent capability definitions into one ambiguous string.
- Keep Jira description, components, labels, comments and historical changes separately typed.
- Maintain source references, access scope, observed/effective dates and retrievable exact spans.
- **Gate:** benchmark-critical spans reproduce correctly without cross-project leakage.

### 2C. Graph technology qualification (Next; depends on 2A)
- Evaluate Neo4j GraphRAG as leading candidate, comparing Graphiti, LlamaIndex and/or a constrained SQLite baseline.
- Assess local/offline operations, licensing, Python/Windows packaging, temporal facts, incremental updates, retrieval and local model interoperability.
- **Gate:** an explicitly owner-approved technology ADR; naming a candidate is not installation authorization.

### 2D. Source-level fact extraction and knowledge graph (Later)
- Extract cited, typed, directional and temporal claims from well-scoped source sections; verify specific evidence spans, record conflicts and abstentions.
- Reconcile canonical identities with roles and aliases, without treating Jira components or co-mentions as proof of product identity.
- **Gate:** benchmark measures show evidence recall, claim support, directed relationships and temporal correctness meet agreed targets.

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
