# Historical benchmark format and review protocol

**Status:** Existing evaluation format retained for compatibility. The [Classifier-first Discovery](CLASSIFIER-DISCOVERY.md) design supersedes deterministic candidate selection as the main source-discovery approach. No private APS source content should be committed or labelled as reviewed without actual review.

## Files

Use UTF-8 JSON files with `schema_version: 1`:
- **Reference file:** `{"schema_version":1,"cases":[...]}`
- **Predictions:** `{"schema_version":1,"predictions":[...]}`

Every reference case must have a unique `case_id`, `split` (`development` or `holdout`), `source` (project, citation, revision, span start/end, exact source quote), and `expected` with `entities` and `claims` arrays. Entities are objects with `id`, `name`, and a nonempty list of `roles`. Claims are objects with `subject_id`, `predicate`, `object` (ID or string), `polarity`, `modality`, and `evidence_quote`. The `source` object may include `jira_labels` and/or `confluence_labels` arrays of nonempty strings, retained separately from the quoted content. Missing label arrays mean not supplied, not necessarily unlabelled. Optional `explanation` clarifies negative cases. `reviewed_by` and `reviewed_at` must be present and nonempty for an authoritative case; unreviewed demonstrations are marked `illustrative_only:true` and are **never scored**.

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

## Private APS candidate selection (legacy experimental baseline)

Use the already populated local index to select up to 26 diverse source excerpts for annotation without another crawl:

```powershell
python -m core.discovery_benchmark_select --db "$env:USERPROFILE\.pm-tools\discovery_jira.sqlite" --project APS --output "$env:USERPROFILE\.pm-tools\benchmark\aps-candidates.json" --target 26
```

This creates a **private, unreviewed selection manifest**, not an accepted benchmark. It samples capability definitions, APS P2P, APS Platform, Integration Toolkit, dependencies and negative/ambiguous cases, deduplicates by citation, and records exact offsets into the *current indexed body*, its digest, Jira labels when the raw issue inventory contains them, and a source quote. It does **not** infer answers or mark anyone as reviewer. Confluence content labels are not stored in the current flattened FTS schema; the manifest explicitly marks their availability as `not_indexed` instead of inventing them. Capturing them is part of the subsequent structured-source work.

The selection is deterministic but heuristic, and its excerpts inherit limitations of the currently flattened index. Verify each source against the original document when annotating. A short source or an index with fewer matching documents yields fewer than 26 cases without artificial padding. The tool refuses to overwrite an existing review pack. Keep this JSON private and off the public repository; the existing `core.discovery_benchmark` evaluator deliberately rejects its illustrative, unreviewed cases.

Human reviewers subsequently choose source spans, add exact annotations, assign development/holdout splits, and record reviewed identity and date before any accepted accuracy claims.


## Balanced sampling revision

The selector now reserves roughly one-third of the target for Jira issues and two-thirds for Confluence content, ranking the two sources independently and filling unused quota only within the same source. It prioritizes substantive responsibilities, purpose, dependency and boundary language over repeated keywords and applies a penalty to archived, questionnaire and assessment material. It reports both requested quotas and achieved source counts; it never invents Jira examples to fill a shortfall.

**Label limitation:** Jira labels can be recovered as structured metadata from the local raw issue inventory. The current Confluence index merges page labels into flattened text, so exact Confluence label attribution cannot be reconstructed safely from the existing index. The selector reports `not_indexed`. Preserving Confluence labels separately requires a later source-normalization update and reindex from already authorized content; this revision does not recrawl Confluence or guess labels.

The previous private candidate pack remains a valid historical sample, but should not be used as the balanced benchmark. Generate a **new output filename** because the selector refuses to overwrite an existing pack:

```powershell
& "$env:LOCALAPPDATA\pipx\pipx\venvs\pm-tools\Scripts\python.exe" -m core.discovery_benchmark_select --db "$env:USERPROFILE\.pm-tools\discovery_jira.sqlite" --project APS --output "$env:USERPROFILE\.pm-tools\benchmark\aps-candidates-v2.json" --target 26
```


## Structured evidence normalization

The evidence index now stores source-specific structured metadata separately from indexed body text in `discovery_source_structure`. For Jira issue observations, the index body contains only the description, and the original ADF, labels, components, issue type and parent are retained separately. Raw Jira payloads already captured locally support offline reindexing without another Jira API crawl. An issue with no description must not be treated as a positive source-supported capability case merely because its labels or components contain keywords.

Confluence indexing retains the fetched storage HTML and page labels in the structured store, no longer concatenating labels into prose. Existing flattened Confluence observations cannot be safely separated into text and tags without access to the original storage response: a subsequent scoped reindex of already authorized pages is necessary. This PR does not pretend to reconstruct lost Confluence label provenance offline. The candidate selector labels existing flattened observations as `legacy_flattened` until reindexed. A separate labels FTS index preserves label-based search without adding metadata tokens to the body.
