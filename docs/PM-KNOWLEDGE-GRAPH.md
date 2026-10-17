# PM knowledge graph: proposed architecture

**Status:** Long-term knowledge-graph direction. Discovery now follows [Classifier-first Discovery](CLASSIFIER-DISCOVERY.md), selected 2026-10-17. Graph implementation and technology selection remain unapproved.

**Goal:** Build a reusable, local-first, provenance-rich knowledge foundation for product discovery, roadmap and dependency analysis, decision histories, risks, interest-holder mapping, impact assessments and reporting.

## Why

APS ingestion collected 4,381 Jira issues, 8,963 comments, 23,683 changelog records and 414 Confluence evidence records. Source collection is working, but the recent semantic discovery experiment identified `https`, `user` and generic Jira components as products; it returned zero claims for well-documented capabilities while producing unsupported claims for fragments. More prompt context alone did not fix underlying problems.

**Keep:** Jira/Confluence collectors, checkpointing, raw SQLite store, FTS search, local inference adapter, existing CLI read/write boundaries.

**Redesign:** source normalization, entity identification, domain model, evidence retrieval, claim verification, graph construction and semantic evaluation. Do not accept existing model candidates as established facts. PR #98 is experimental and remains unmerged pending redesign.

## Layered architecture

1. **Collection:** Existing, scoped source adapters and incremental checkpoints.
2. **Structured evidence:** Original document/issue fields; Confluence section and table boundaries; Jira labels and Confluence content labels as distinct indexed metadata; author/source identity, timestamps, content hash, permissions, citations and stable source spans.
3. **Hierarchical classification:** All in-scope evidence units go to a local broad multi-label classifier without deterministic relevance filtering; specialist classifiers then examine relevant and uncertain branches, with versioned taxonomies and explicit errors/abstentions.
4. **Entities:** Product, service, capability, workstream, team, Jira component, Jira label, Confluence label, initiative, issue, decision, interest-holder and source. A product can also have an associated workstream; these are not mutually exclusive kinds.
5. **Source-level claims:** Subject, predicate, object, negation, temporal validity, source span and uncertainty. Distinguish planned, operational, deprecated, contradicted and unknown.
6. **Reconciliation and temporal property graph:** Resolve aliases carefully, track identity through time, conflicts, superseded decisions and graph edge provenance.
7. **Evidence retrieval and GraphRAG:** Downstream graph queries, graph traversals and cited synthesis after classifier-based evidence discovery and validated extraction. Lexical search may support browsing or graph queries, but must not prefilter initial classifier ingestion.
8. **PM features:** Discovery, assessment, classification, dependency/roadmap impacts, decision support, risk, interest-holder analysis, reporting and stewardship.

Important predicates include `provides`, `part_of`, `depends_on`, `used_by`, `owned_by`, `implements`, `replaces`, `historical_name` and `contradicts`. The direction and semantics must be defined, not inferred from co-occurrence.

## Core safety requirements

- Jira and Confluence remain authoritative for their own stored records. The graph is a derived and reviewable knowledge layer.
- Exact cited passages must support each accepted assertion. A valid citation string or JSON object alone is not proof.
- Do not convert a Jira component, workstream label or planning note into a product or delivered capability by default.
- Keep source timestamps distinct from effective dates and supersession.
- Inferences remain unconfirmed until approved, and contradictions are surfaced instead of silently resolved.
- The system is local-first, respects document authorization scope, treats retrieved text as untrusted data and never sends private content to unapproved services.
- Writes to Jira, Confluence and configuration remain separate, previewed and explicitly approved.

## Technology qualification

**Candidate for later qualification, not selected:** Neo4j GraphRAG with a Neo4j property graph. **Alternatives:** Graphiti for temporal/incremental knowledge, LlamaIndex property-graph capabilities and a limited SQLite baseline. Microsoft GraphRAG is an architectural reference.

Evaluate with the *same frozen corpus*: quality, local-model integration, temporal validity, hybrid search, incremental refresh, provenance, licensing, packaging/Windows support and operating complexity. Keep graph store and retrieval interfaces replaceable. No hosted inference or graph service without separate approval. A future accepted ADR must authorize the concrete stack.

## First demonstrable PM questions

1. Which products, capabilities and workstreams exist, and which source sections support them?
2. What deliverables and outcomes could be affected if token exchange or another external dependency changes?
3. Which later decision superseded an earlier approach, and which questions remain unresolved?

**Prerequisite:** [Discovery Evaluation](DISCOVERY-EVALUATION.md) and the ontology must be accepted before wide indexing or graph migration.
