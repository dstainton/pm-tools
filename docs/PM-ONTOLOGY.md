# PM knowledge ontology v0.1

**Status:** Phase 2A proposal for owner review. No graph infrastructure, identity promotion or source writes.

## Identity versus roles

An **entity** has a stable opaque ID, one canonical display name, zero or more evidence-backed aliases, and **one or more roles**. Its identity is not determined by a Jira component or an acronym alone. The same real-world offering may have a product role and an associated delivery workstream, without collapsing their distinct responsibilities.

| Role | Meaning | Non-example |
| --- | --- | --- |
| product | Defined offering delivering value to consumers | Jira board |
| service | Operated function, interface or ongoing service | Generic URL value |
| capability | Ability or function a product/service/organization provides | Jira label |
| workstream | Delivery and planning grouping | Product ownership implied by component |
| team | Group accountable for work/operation | Jira project |
| stakeholder | Person, role or organization involved in decisions | Keyword mention |
| initiative | Bounded strategic/delivery endeavour | General topic |
| decision | Recorded choice, rationale and status | Brainstorming possibility |
| source_document | Immutable identified source revision | Inferred summary |
| source_section | Exact span within a source revision | Character window with unmarked omissions |
| jira_issue | Recorded Jira work item | Product definition by itself |
| jira_component | Jira issue classification field value | Product identity by itself |

## Claims, evidence and direction

An **assertion** records `subject_id`, `predicate`, `object_id` or literal value, `polarity`, `modality`, `valid_from`/`valid_to`, `observed_at`, `review_status`, and one or more evidence references pointing to *exact* source revision and span. Keep the raw source quote. A citation without a supporting quote does not establish factual support.

Permitted initial predicates: `provides`, `depends_on`, `part_of`, `used_by`, `owned_by`, `implements`, `tracked_by`, `historical_name`, `replaces`, `contradicts`, `has_purpose`, `has_boundary`. Expand by an explicit versioned schema migration.

- `A part_of B` means **A is contained in B**, not that B is built on A.
- `A depends_on B` means A requires B for a stated capability, not mere textual co-occurrence.
- `A provides B` means A provides a capability or service described by B.
- `A used_by B` means B uses A. Direction is literal, not interchangeable with `depends_on`.
- `historical_name` is evidence-backed terminology over time, not necessarily a renaming of the same product.
- Negation and proposed future capability must remain explicit rather than becoming positive, current-state edges.

Modality: `actual`, `planned`, `proposed`, `historical`, `unknown`. Polarity: `positive`, `negative`. Review: `candidate`, `verified`, `rejected`, `conflicted`, `superseded`. Source observation time must not be confused with business effective time.

## Scope and reconciliation

Canonical identity must respect source project/space permissions, organization scope, history and source revisions. Confluence page ancestry supplies document context, not automatic product hierarchy. Jira issue hierarchy supplies work structure, not automatic service ownership. Conflicting assertions are retained and presented for review; an LLM cannot approve or silently overwrite them.

## First APS reference targets (pending annotation)

Candidate entities for the reference corpus are **APS P2P / Secure Data Exchange**, **APS Platform**, and **Integration Toolkit**. Their exact roles, naming history, boundaries and relationships must be annotated from source passages, not inferred merely from this seed list. Include independent negatives such as `user`, `research`, `operational`, `https` and `represents the upstream service or API`.

## Versioning and compatibility

The ontology is deliberately independent of Neo4j/Graphiti/LlamaIndex storage. This document and the evaluation file contract are versioned together. Acceptance of ontology v0.1 does not modify the existing `products:` and `workstreams:` configuration schema.
