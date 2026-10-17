# Discovery and knowledge-graph evaluation

**Status:** Updated for owner-selected hierarchical classifier-first discovery, 2026-10-17. Targets remain proposed until accepted. Targets require owner acceptance.

## Purpose

Prove usefulness and factual support, not simply that a command completed or JSON parsed.

## Reference set

Create a versioned, human-reviewed APS benchmark of approximately 20–30 diverse source documents, including label-rich Jira issues and labelled Confluence pages, misleading and missing labels, explicit product/capability cards, documents with multiple adjacent entities, Jira Epic descriptions, generic Jira components, ambiguous aliases, conflicting plans, negative statements and superseded decisions. Annotate entity names and multiple roles, expected attributes, exact cited spans, directional relationships, temporal status and expected abstentions. Protect private data. Reserve a holdout set and test on a second, differently organized corpus before general release.

## Proposed quality gates

| Measure | Initial target |
| --- | --- |
| Parsing/source fidelity | 100% of reference-critical headings, table/field boundaries and spans |
| Entity recall | At least 90% on labelled entities |
| False identities | Zero among curated explicit negative cases |
| Retrieval recall@10 | At least 90% of required source spans |
| Factual support | At least 95% of accepted model claims backed by exact cited spans |
| Relationship direction and negation | 100% on explicit reference cases |
| Accepted claim provenance and schema | 100% valid, resolvable and scoped |
| APS core workstreams and capabilities | All agreed reference cases covered |
| Temporal conflict handling | No unmarked contradictions or supersession errors in curated cases |

These are **project proposals**, not universal industry standards.

## Classifier-first evaluation principles

No deterministic relevance prefilter may exclude evidence before broad classification. Every in-scope evidence unit is sent to the broad multi-label classifier or explicitly counted as a processing failure. Specialist routing is based on broad classification, including uncertain and multi-label cases. Score and report false negatives at each routing level; sample items assigned `other` or `uncertain` for missed relevance. Separate relevance, evidence strength, source authority and temporal applicability; an uncalibrated model score is not a probability that a claim is true. Cache results using content revision, taxonomy/prompt version and model identity. Keep classification independent of subsequent grounded claim extraction.

Human-reviewed reference cases measure broad/specialist category precision and recall, routing recall, abstention quality, category confusion, negative cases, exact citation support and temporal errors. Report source coverage and failures, not just model scores. The earlier `discovery_benchmark_select` method is a historical deterministic baseline and must not control candidate routing.

## Evaluation order

1. Confirm structured normalization, Jira/Confluence label preservation, and exact passage reconstruction.
2. Qualify broad multi-label classification against every evidence unit and reviewed category annotations. Measure recall, false positives and uncertain/other audit samples.
3. Qualify specialist classifier routing and source relevance on short, known sections (including negative language, historical material, uncertainty and schema compliance). Record model version, taxonomy/prompt version, context budget, token usage if available and errors.
4. Evaluate citation-to-claim factual support, not citation existence alone.
5. Evaluate identity, direction, temporal reconciliation and graph queries.
6. Validate end-to-end product discovery, dependency impact and decision history.
7. Run the same tests after every material change, including regressions and negative cases.

A zero-claim response where evidence unambiguously supports claims is a **recall failure**. Keep raw evaluation runs locally with reproducible settings. Human annotation remains the authority; a second model may assist but not replace validation.

**First authorized implementation slice after approval:** ontology, benchmark format and evaluation runner only. Graph technology selection and extraction implementation follow their gates.

## Phase 2A implementation artifacts

The initial ontology and benchmark implementation are at [PM Ontology](PM-ONTOLOGY.md) and [Benchmark Format](BENCHMARK-FORMAT.md). The evaluator is `python -m core.discovery_benchmark evaluate --reference ... --predictions ...`; it validates reviewer status and provenance, reports exact-match entity/claim precision and recall, and counts missing predictions as false negatives. It is **not** an LLM judge and cannot establish semantic entailment or retrieval quality on its own.

No sensitive APS corpus or purportedly human-reviewed annotations is committed in this phase. Reference annotation and owner acceptance are the remaining Phase 2A gates before selecting or installing graph infrastructure.
