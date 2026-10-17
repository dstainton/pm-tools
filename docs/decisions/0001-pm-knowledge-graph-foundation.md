# ADR 0001: Shared PM knowledge graph foundation

**Status:** Proposed, pending explicit owner acceptance in review

**Date:** 2026-10-16

## Context

Recent APS discovery experiments found complete Jira/Confluence evidence but poor semantic results: false product names, zero supported claims for core capabilities and misattributed purposes. Jira components, labels, workstreams and products were treated as interchangeable. Large inference prompts did not resolve those modelling and retrieval defects. The owner wants the knowledge base to support future product management workflows, not just initial discovery.

## Proposed decision

Adopt a **local-first, evidence-first, temporal property-graph and GraphRAG architecture** as the intended common knowledge foundation for pm-tools. Reuse existing collectors, raw evidence, FTS and local models. Preserve original structure, Jira/Confluence labels as separately typed metadata, and exact cited spans; extract source-level claims before assembling product profiles and graph relationships; separate inferred, conflicting, historical and accepted claims.

Neo4j GraphRAG is the leading candidate, **not yet a selected dependency**. Compare Graphiti, LlamaIndex and/or SQLite against an accepted evaluation benchmark before choosing graph infrastructure. Preserve current CLI and configuration semantics unless a separate migration is accepted. No new hosted model, graph service or data disclosure is authorized.

## Alternatives

- Continue patching concept-pair extraction: rejected as the preferred direction because it lacks a domain ontology and reliable semantic evaluation.
- Custom SQLite-only graph model: possible lower operating cost, benchmark before excluding.
- Adopt an entire GraphRAG stack immediately: deferred pending local-model, licensing, deployment and quality validation.

## Consequences

Improved reuse for product discovery, dependencies, roadmap, risk, decisions and reporting. Adds ontology, graph operations, provenance, temporal reconciliation and benchmark maintenance work. Does **not** itself authorize implementation, installation or migration.

## Acceptance

Owner review of this PR can accept the strategic architecture direction. The specific technology stack requires a later reviewed decision after the benchmark.
