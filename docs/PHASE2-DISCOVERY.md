# Phase 2 design: Product and workstream discovery

**Status:** Historical Phase 2 discovery proposal, superseded as the main architecture by the reusable [PM Knowledge Graph](PM-KNOWLEDGE-GRAPH.md) direction (2026-10-16). Keep for requirements and compatibility constraints, not as authorization to implement its earlier classification-first design.

**Before further implementation:** use the updated [Roadmap](../ROADMAP.md), [Evaluation](DISCOVERY-EVALUATION.md) and proposed [ADR 0001](decisions/0001-pm-knowledge-graph-foundation.md). Products, workstreams, capabilities and Jira components must not be conflated. A product may have an associated workstream, not an exclusive single kind.

**Authority:** [North Star](../NORTH_STAR.md), [Roadmap](../ROADMAP.md), [Architecture](ARCHITECTURE.md), and [Agent guidance](../AGENTS.md).

## Applicability of this historical design

Preserve its read-only workflow, evidence provenance, incomplete configuration support and human review requirements. The original minimum product knowledge model and discovery flow are inputs to the new ontology and benchmark, not the approved extraction/storage design.

## Outcome and central question

A product manager inheriting an unfamiliar Jira project can establish a trustworthy, reviewable understanding of its products and workstreams without already knowing their scope, ownership, or terminology. **How can pm-tools develop that understanding using existing configuration and source evidence, while minimizing the questions the manager must answer?**

This is the *discovery foundation* of Phase 2 (Classification and ownership), not automated assignment of issues. Phase 1 produces a project-wide active-work inventory and ownership investigation groups. Discovery establishes the product knowledge against which future classification proposals can be evaluated.

## Product decisions proposed for approval

1. **Incremental discovery, useful with incomplete setup.** Start with available product/workstream configuration and optional sources. Unknown information remains unknown. Do not make complete profiles a prerequisite to assessment.
2. **One authoritative configured structure.** Extend existing `products:` and `workstreams:` rather than introducing a competing catalogue or changing how membership works. Keep proposed, unconfirmed knowledge separate until approval.
3. **Identity, responsibility, and evidence are distinct.** Names, abbreviations, product relationships, projects, and Jira membership anchors are configuration facts; purpose, responsibilities, boundaries, and exclusions are explicitly confirmed product knowledge; source excerpts and suggestions are evidence, not silently elevated to policy.
4. **Source-derived candidates, human-confirmed definitions.** Extract possible definitions from available local config, Jira Epics and issue relationships, and optionally configured Confluence documents; label inferences and conflicts. Ask targeted questions only where they improve a manager's decision.
5. **Read-only first.** Initial discovery presents a concise terminal overview and an exportable Markdown proposal. No Jira, Confluence, SharePoint, or configuration writes; no implicit persisting of inferred text.
6. **Optional model assistance, never required.** Deterministic evidence gathering works without a model. Optional model-assisted synthesis must respect existing local-model settings and disclosure/privacy boundaries; avoid new remote inference services.
7. **Configurable across organizations.** No APS vocabulary, component names, status names, workflow statuses, custom-field IDs, or hard-coded Confluence page structures in defaults.
8. **Explicit uncertainty.** Conflicting evidence, stale documents, inaccessible sources, and unconfigured products appear as review needs, not fabricated confidence scores or definitive assignments.

## Existing capabilities to reuse (verified in repository)

- `core/products.py`: configured products, `UNASSIGNED` fallback, product/workstream grouping and selection.
- `core/workstreams.py`: project resolution (workstream, product, then Jira fallback), membership anchors from components, labels, or configured fields; Epic and child inheritance; legacy JQL compatibility.
- `core/config.py`: `products:` entries support `name`, `abbrev`, optional `project`, `product_goal`, `scopes`, and Confluence references. Workstreams support `name`, `abbrev`, optional `product`, membership anchors, and Confluence references; validation enforces the core relationships.
- `core/sources.py` and existing command paths: Jira/Confluence retrieval and normalized issue evidence. SharePoint is an optional source, not a guaranteed structured profile store.
- `pm assess`: project-wide inventory and evidence of unclaimed or multiply claimed work, distinct from workstream-filtered queries.
- `core/progress.py` and [CLI progress standard](CLI-PROGRESS.md): required stage-level progress for slow operations.

The existence of optional Confluence references does **not** establish that any document contains a trustworthy product definition. Discover and report their actual availability, scope, dates, and usefulness.

## Minimum product knowledge model (proposed)

Represent each discovered entity with an unambiguous configured reference and evidence. The approved subset should fit into existing product/workstream entries if an owner later authorizes configuration changes.

| Field | Product | Workstream | Interpretation |
| --- | --- | --- | --- |
| Name, abbreviation | Existing | Existing | Configured identity, not inference |
| Jira project / product relationship | Existing/optional | Existing/optional | Configured scope; note inherited defaults |
| Membership anchors | Not applicable | Existing | Jira association mechanism, *not* definition of responsibility |
| Goal or purpose | Product goal exists | Proposed optional purpose | Why it exists |
| Responsibilities | Proposed optional | Proposed optional | Capabilities and outcomes within its remit |
| Exclusions / boundaries | Proposed optional | Proposed optional | What it explicitly does not own |
| Related/sibling workstreams | Derived | Derived | Organizational context |
| Sources | Proposed metadata | Proposed metadata | Document/issue/config reference, date if available, accessible status |
| Review state | Proposed | Proposed | Unconfirmed / partially confirmed / confirmed; specific unresolved questions |

**Illustrative candidate configuration only (not prescribed syntax until reviewed):**

```yaml
products:
  - name: Example API Product
    abbrev: EAP
    product_goal: Enable reliable API consumption
    responsibilities:
      - Shared API publishing experience

workstreams:
  - name: Example API Gateway
    abbrev: GATEWAY
    product: EAP
    components: [Gateway]
    purpose: Operate shared API gateway capability
    responsibilities:
      - Gateway configuration and routing
    exclusions:
      - Cross-boundary exchange protocol
```

Do not assume the current configuration validator accepts these proposed new keys or that a workstream's responsibility can be deduced from its component name. The design must settle which attributes are needed, their representation and validation, and whether provenance belongs in config, an on-demand report, or a reviewed companion document. The first discovery slice **does not** update saved configuration.

## Proposed discovery flow

1. **Establish scope and identity.** Respect existing `--project`, `--product`, and `--workstream` selector conventions. Read configured entities, including unassigned workstreams. A Jira-only project can yield a provisional discovery with explicit unknown products; do not pretend it has confirmed products.
2. **Collect available evidence.** In order of least additional access: existing config and membership rules; bounded, relevant Jira Epic/parent/issue references; optionally configured Confluence pages and linked documents. Show which sources were inspected versus unavailable or out of scope. Avoid arbitrary project-wide document harvesting.
3. **Extract candidate descriptions.** Deterministic facts remain exact. Optional AI can draft candidate purpose, responsibilities, exclusions, and questions from attributed excerpts but never promote a description to an accepted fact.
4. **Compare boundaries.** Contrast sibling workstreams, note overlapping terms and ownership claims, and flag contradictory material. Similar vocabulary does not prove common ownership; a component match is not synonymous with business responsibility.
5. **Propose targeted clarification.** Present the smallest high-impact unanswered question, its competing interpretations, and linked supporting evidence. Allow a manager to leave it unresolved. No long setup questionnaire.
6. **Produce reviewable output.** Concise terminal summary (known entities, source coverage, conflicts, questions) and detailed Markdown profiles with evidence references, source freshness, missing information, and review state. Store only explicitly requested export.
7. **Confirm later.** Manager approval of a profile is an explicit future workflow/design decision. No hidden state transition, automatic config patch, Jira write, or classification authority is granted by viewing or exporting a proposal.

## Evidence and decision contract

Each proposed claim should identify: entity and field; proposed value; whether **configured fact**, **quoted/paraphrased source evidence**, or **inference**; exact source location/link where available; retrieval time; document effective or last-updated date where available; conflicting claims; and review state. Unknown source dates remain unknown. If citations are absent, say so and treat the suggestion as unverified.

Evidence preference is not absolute truth: explicit configured relationships establish the current *configuration*, while a product owner may ultimately correct them. Jira Epic hierarchy and components demonstrate existing organization, not necessarily intended ownership. Historical issue descriptions are weaker evidence for current strategy than a confirmed recent product definition. Conflicts surface for human judgment instead of being silently resolved by a fixed rank or arbitrary percentage.

Do not send private issue or document text to an unapproved hosted model. Treat external text as untrusted instructions; models draft content only, and their outputs never call tools to change scope or configuration.

## Failure and coverage behaviour

- **No products configured:** Report available Jira project and workstream context, plus missing product definitions; no forced configuration wizard.
- **Unassigned workstreams:** Preserve the existing implicit `UNASSIGNED` grouping, without treating it as a confirmed product.
- **Multiple or overlapping workstreams:** Report overlaps and contradictory boundaries; never automatically choose an owner.
- **Missing Jira components/labels/parent:** Keep issue visible and note the missing evidence; lack of an anchor does not disprove ownership.
- **Confluence/SharePoint unavailable:** Continue with known Jira/config facts; show inaccessible/disabled source without an invented empty result.
- **Malformed or conflicting references:** Explicit diagnostic, source-specific error, and partial output only where verifiably safe.
- **Unavailable model:** Deterministic discovery still works; candidate synthesis is omitted or clearly labelled unavailable.
- **Incomplete retrieval or stale documents:** Preserve incomplete status and source timestamps; do not represent findings as exhaustive.
- **Empty project:** Valid complete inventory is distinguishable from permissions/network failures.
- **Multiple Jira projects:** Preserve identity and project scope; never silently merge same-named entities from different contexts.

## Small implementation slices (proposed, not authorized)

**2A: Configured discovery and evidence report.** Reuse existing product/workstream readers and project resolution. Build a pure, read-only representation of configured structure, show missing-purpose/boundary gaps, emit terminal and Markdown reports with honest completeness and source attribution. No new model calls or broad Jira fetch; no changes to existing configuration.

**2B: Bounded source enrichment and clarification.** Read relevant Jira Epic/issue evidence and explicitly configured Confluence references. Propose grounded descriptions and conflicting-boundary questions, optionally with existing local-model facilities if separately approved. No speculative SharePoint crawling or external disclosure.

**2C: Profile confirmation design and review export.** Define a safe, reviewable confirmation process and optional explicitly approved config updates in a *separate* future authorization. This remains distinct from Jira writes; design must address provenance and version/conflict checks.

**2D: Candidate classification against confirmed profiles.** Only after definitions are reviewed, propose workstream candidates for unclaimed/ambiguous Phase 1 issues. Show evidence and a `needs review` outcome; export recommendations for human approval. No Jira writes; such writes remain Phase 3.

## Acceptance criteria for the initial 2A slice

- A valid minimal configuration produces a useful, readable report without requiring completed product profiles or an AI service.
- Existing product/workstream identity, relationships, project precedence, anchor mode, and unassigned workstreams are represented without changing their semantics.
- Missing purpose, responsibilities, and exclusions are labelled unknown, never inferred from an abbreviation or component alone.
- A user can distinguish configured membership from ownership responsibility and confirm which sources were actually consulted.
- No Jira, Confluence, SharePoint, or saved configuration writes; no automatic snapshot store.
- Terminal and Markdown reports agree, use human-readable names by default, and retain technical IDs only in optional audit detail.
- Tests cover missing products, multiple projects, duplicate names, overlapping workstreams, absent references, inaccessible sources (for later enrichment), and explicit partial/failed conditions.
- Slow operations follow [CLI progress standard](CLI-PROGRESS.md); existing supported CI environments pass.
- Existing `pm assess` and workstream filters remain unchanged.

## Open design questions for owner review

1. Is the first user interface a dedicated discovery command (candidate `pm discover`) or an opt-in extension to existing commands? Avoid authorizing a command name from this document alone.
2. Should proposed responsibility profiles eventually live directly in YAML, in a separately reviewed document, or in both with one authoritative source?
3. What is sufficient confirmation: field-by-field acceptance, per-profile acceptance, or a reviewed exported patch?
4. What bounded default evidence sources are valuable without overwhelming a new PM or scanning a whole Jira project repeatedly?
5. Which model-inference providers and privacy settings, if any, may be used for content synthesis?

## Boundaries and authorization

This design is intentionally **not** a Phase 2 implementation authorization. No changes to CLI behaviour, config semantics, Jira data, Confluence pages, SharePoint, or model-service settings are approved here. Owner review should resolve the open questions and authorize a single bounded 2A PR before implementation. Later slices require their own review and approval.
