# Discovery and knowledge-graph evaluation

**Status:** Proposed reference benchmark and release gates, 2026-10-16. Targets require owner acceptance.

## Purpose

Prove usefulness and factual support, not simply that a command completed or JSON parsed.

## Reference set

Create a versioned, human-reviewed APS benchmark of approximately 20–30 diverse source documents, including explicit product/capability cards, documents with multiple adjacent entities, Jira Epic descriptions, generic Jira components, ambiguous aliases, conflicting plans, negative statements and superseded decisions. Annotate entity names and multiple roles, expected attributes, exact cited spans, directional relationships, temporal status and expected abstentions. Protect private data. Reserve a holdout set and test on a second, differently organized corpus before general release.

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

## Evaluation order

1. Confirm structured normalization and exact passage reconstruction.
2. Measure retrieval independent of generation.
3. Qualify local models using short, known source sections (including false claims, negative language, uncertainty and schema compliance). Record model version, context budget, token usage if available and errors.
4. Evaluate citation-to-claim factual support, not citation existence alone.
5. Evaluate identity, direction, temporal reconciliation and graph queries.
6. Validate end-to-end product discovery, dependency impact and decision history.
7. Run the same tests after every material change, including regressions and negative cases.

A zero-claim response where evidence unambiguously supports claims is a **recall failure**. Keep raw evaluation runs locally with reproducible settings. Human annotation remains the authority; a second model may assist but not replace validation.

**First authorized implementation slice after approval:** ontology, benchmark format and evaluation runner only. Graph technology selection and extraction implementation follow their gates.
