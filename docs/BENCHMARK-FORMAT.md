# Phase 2A benchmark format and review protocol

**Status:** Proposed; no private APS source content has been committed or human-labelled in this slice.

## Files

Use UTF-8 JSON files with `schema_version: 1`:
- **Reference file:** `{"schema_version":1,"cases":[...]}`
- **Predictions:** `{"schema_version":1,"predictions":[...]}`

Every reference case must have a unique `case_id`, `split` (`development` or `holdout`), `source` (project, citation, revision, span start/end, exact source quote), and optional source-scoped `jira_labels` or `confluence_labels` arrays, and `expected` with `entities` and `claims` arrays. Entities are objects with `id`, `name`, and a nonempty list of `roles`. Claims are objects with `subject_id`, `predicate`, `object` (ID or string), `polarity`, `modality`, and `evidence_quote`. Optional `explanation` clarifies negative cases. `reviewed_by` and `reviewed_at` must be present and nonempty for an authoritative case; unreviewed demonstrations are marked `illustrative_only:true` and are **never scored**.

Prediction entries contain `case_id`, `entities`, and `claims` in the same form, with claims also carrying `citation`. Predictions may leave arrays empty; abstentions must not be hidden.

Add reference cases where labels correctly improve document retrieval and others where labels alone are misleading. Preserve their originating source and never score a label value as a source-backed product identity without additional evidence.

## Validation

The first runner is deterministic and intentionally conservative. It checks identities/roles and exact-match normalized claim tuples for precision and recall, reference coverage and whether the returned `citation` matches the provided source. It **cannot** decide semantic entailment by itself: human review of cited spans remains a separate acceptance gate. Do not label a reference as human-reviewed unless someone actually reviewed it.

Do not put credentials or private internal source extracts in a public repository. Keep actual APS benchmark text in a locally protected file or explicitly approved restricted test data store. The included example is wholly synthetic and illustrative.

## Run

```powershell
python -m core.discovery_benchmark evaluate --reference path/to/reviewed.json --predictions path/to/predictions.json
```

The command returns an error for malformed inputs, missing cases, unknown IDs, unreviewed reference material, or invented citation IDs. It reports entity precision/recall, claim precision/recall and case coverage, without pretending automated tuple matching proves groundedness.

## Approval sequence

1. Owner approves this schema and ontology.
2. Curate APS cases with source revision and exact spans (20–30 documents), including explicit negative examples.
3. Hand-review labels and lock the holdout partition.
4. Run local model qualification on small sections before retrieval tuning.
5. Extend evaluator to retrieval@10, span entailment, direction/negation and temporal contradictions, using reviewed annotations.
6. Compare graph stacks against the *same frozen benchmark*.

See [Discovery Evaluation](DISCOVERY-EVALUATION.md), [PM Ontology](PM-ONTOLOGY.md) and [Roadmap](../ROADMAP.md).
