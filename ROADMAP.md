# pm-tools Roadmap

This is an outcome-led implementation sequence, **not a calendar or a list of automatically authorized tasks**. The North Star defines why; accepted decisions and architecture constrain how; this document sets direction and dependencies. GitHub issues or direct owner assignments authorize specific implementation work.

## Status and authorization

- **Active:** current phase; its description permits planning, not unrestricted implementation.
- **Next:** intended subsequent phase; do not implement until the owner authorizes a scoped task.
- **Later:** candidate direction, not authorized implementation.
- **Deferred / Rejected:** explicitly excluded until reconsidered by the owner.
- **Current authorized work:** only the owner-assigned issue or explicit request; completion does not authorize automatically moving to another task.

**Current authorized slice:** Phase 1 closure and verification only, as explicitly requested. No Phase 2 implementation is authorized. Following owner review and merge of the closure PR, stop until new authorization.

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

## Phase 2: Classification and ownership (Later)

**Discovery design proposal (not approved for implementation):** [docs/PHASE2-DISCOVERY.md](docs/PHASE2-DISCOVERY.md). The proposed first slice establishes product and workstream knowledge before issue classification. Owner review and scoped authorization are required before any code changes.

**Outcome:** Unclaimed and ambiguously owned work can be reviewed efficiently.

- Explain candidate workstream assignments using Epic relationships, existing configuration, fields, and optionally model-assisted content analysis.
- Distinguish workstream membership from Jira components and informal labels.
- Preserve uncertainty and a `needs review` outcome.
- Export recommendations for human review before writes.

**Dependency:** Trustworthy Phase 1 inventory and source provenance.

## Phase 3: Guided remediation (Later)

**Outcome:** A PM can repair a large backlog safely in batches.

- Reviewable proposals for missing metadata, hierarchy, duplicate candidates, and out-of-date issues.
- Explicit approval, previews, conflict checks, partial execution, and audit trail.
- Keep closing, deleting, and irreversible actions behind specific human authorization.

**Dependency:** Evidence-backed classification and tested write boundaries.

## Phase 4: Continuous stewardship (Later)

**Outcome:** Backlog health improves over time rather than only during initial cleanup.

- Trend baselines for ownership, age, review state, and readiness, without incentivizing indiscriminate issue closure.
- Integrate actionable exceptions into `pm today` and relevant `pm report` profiles.
- Keep health measures distinct from delivery throughput and product outcomes.

**Dependency:** Consistent inventory and snapshot semantics.

## Future opportunities (not authorized)

- **Prioritization:** Facilitate defensible trade-offs and show assumptions, not invented numerical certainty.
- **User and stakeholder evidence:** Trace needs, feedback, and decisions to planned work.
- **Strategy and outcomes:** Connect product goals and measurable results to work without treating delivery metrics as outcomes.
- **Dependencies and forecasting:** Make cross-team commitments and scenarios visible with documented uncertainty.
- **Risk and decision integration:** Improve read-only support for existing register formats without assuming undocumented Confluence database-row APIs.

Order and scope of these opportunities require deliberate owner review after the backlog-recovery foundation.

## How this roadmap changes

Propose the motivation, affected users, alternatives, dependencies, and implications in a PR or issue. The owner approves material changes. An agent may report an opportunity or recommend a new phase, but cannot mark it Active or implement it unilaterally. Do not mark exit criteria complete without verified evidence.
