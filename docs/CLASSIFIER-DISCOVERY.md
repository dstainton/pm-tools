# Classifier-first discovery architecture

**Decision:** Owner-selected direction, 2026-10-17. **Status:** Design documentation; implementation requires a separately scoped task. This supersedes deterministic relevance filtering and benchmark candidate sampling as the main discovery path.

## Goal and boundaries

Build reusable local-first discovery of products, services, workstreams, capabilities, decisions and relationships from Jira and Confluence, without knowing their names in advance. Deterministic code is appropriate for *faithful collection, normalization, segmentation, persistence and verification*, not for judging relevance or deciding which source to classify. Preserve read-only source-system behaviour, private local data and human acceptance of final product knowledge.

## Pipeline

1. **Collect complete authorized source scopes.** Walk all configured Jira projects and explicitly selected Confluence page trees/spaces with pagination and resumable checkpoints. Track inaccessible, failed, deleted, truncated and uncollected records. Completeness refers only to the configured and permitted scope, not an entire installation. Maintain raw source payloads, identifiers, versions and timestamps.
2. **Normalize without mixing fields.** In local SQLite store Jira issue descriptions, summaries, types, statuses, components, labels, parents, linked issues, comments, histories and timestamps as independently typed values. Confluence pages/blogs preserve storage representation, headings, sections, tables, hierarchy, labels, comments, revisions and timestamps. Do not append labels/components to body text or claim a metadata field is a textual assertion. Keep original raw payloads alongside normalized views.
3. **Create evidence units.** Prefer meaningful section and field boundaries. Independently addressable units include Jira descriptions and comments, Confluence sections/table rows and comments, and discrete history/decision observations. Preserve parent context, exact quote, offsets/source structure, revision and stable source citation; split oversized sections only at meaningful boundaries. No keyword relevance gating.
4. **Broad multi-label classifier.** Send **every in-scope evidence unit** to a prompted local classifier, beginning with the configured local EmbeddingGemma embedding classifier. Initial general taxonomy: organizational structure; capabilities; architecture/integrations; governance/standards; delivery/operations; relationships/dependencies; decisions/lifecycle; other/uncertain. Categories are not mutually exclusive. Allow abstention, multiple labels and explicit processing errors. The taxonomy is versioned and extendable across organizations; APS aliases are optional contextual hints, not hardcoded answers.
5. **Specialist classifiers.** Route based on broad labels, allowing overlapping categories and conservative routes for uncertainty. Specialists distinguish, for example, product vs workstream vs team, capability vs requirement, explicit ownership vs co-mention, and decided vs proposed vs historical/superseded. Assess relevance, evidence strength, source authority and temporal applicability separately. Never interpret a raw model score as a calibrated truth probability.
6. **Evidence-based extraction.** On relevant classifier output, extract entity candidates and directional, negated and time-aware claims with exact cited evidence. Keep conflicts and unsupported/uncertain cases visible; no model output silently becomes an approved configuration fact. Graph storage and guided configuration come *after* evaluation gates.

## Classifier contract

For generative classifiers, classification output must be machine-validated JSON with unit ID, model/taxonomy/prompt versions, zero or more category labels, optional ranking scores, explicit abstention/uncertainty, rationale grounded in supplied evidence and execution status. Use strict schema validation and a bounded model repair turn for malformed JSON; repeated failure remains a recorded error, not an inferred `other` label. Separate original evidence from model-generated explanations. Do not silently prune candidates based on rigid keyword matches, field lengths or labels.

Avoid inventing calibrated confidence. Scores are useful for within-run ranking only until measured against human annotations. Preserve a route for uncertain and `other` examples and periodically evaluate a sample to detect missed categories. Output must explain both routed and missed records.

## Local runtime and repeatability

- Cache classification by unit content digest, model identifier/quantization, taxonomy version, prompt version and inference settings; only changed units or classifier definitions are rerun.
- Schedule work in bounded batches for low-memory Windows hardware; store progress, errors, time/token consumption where available, and resumable checkpoints. The initial pipeline should operate without a GPU and without remote inference.
- On source changes, invalidate affected evidence units and their classifications. Historical observations must not be silently rewritten.
- First prototype: use a local embedding classifier with independently embedded taxonomy descriptions. Compare a trained classifier or Qwen adjudicator only if measured error rates justify it. Do not ask EmbeddingGemma to generate text or JSON.

## Evaluation and acceptance

Begin with a representative, **human-reviewed** sample from the complete corpus, not a heuristic sample declared ground truth. Cover rich and empty Jira descriptions, comments, source labels, multi-topic sections, explicit capability boundaries, historical plans, conflicting decisions and incidental mentions. Measure broad multi-label recall/precision, specialist routing recall, abstention and errors, false negatives sampled from `other`/uncertain, extraction support and temporal correctness. Preserve development and holdout splits. A valid JSON response is not a correct classification. Do not promote model proposals to verified product knowledge without review.

The original deterministic benchmark selector and its historical v1/v2/v3 output remain useful as regression context only. Their failure to find suitable Jira excerpts after metadata normalization is a reason to replace *selection logic*, not to re-mix descriptions with components and labels.

## Decisions explicitly not made

No GraphRAG/Neo4j framework selection, trained classifier, threshold calibration, source-system writes, production deployment, corpus export or automatic configuration mutation is authorized by this design. The initial implementation milestone is **complete structured local evidence + broad multi-label classification and audit report**; specialist routing and extraction follow demonstrated quality.


## Initial EmbeddingGemma NPU implementation (2026-10-17)

`classification:` is independent from the existing `model:` chat configuration:

```yaml
classification:
  endpoint: http://127.0.0.1:13305/v1/embeddings
  model: embed-gemma-300m-FLM
  task: clustering
  taxonomy_version: pm-broad-v1
  batch_size: 8
  timeout: 240
```

Google's [EmbeddingGemma 300M model card](https://ai.google.dev/gemma/docs/embeddinggemma/model_card) specifies `task: classification | query: {content}` for standard classification and `task: clustering | query: {content}` for clustering. For **custom, domain-specific labels**, Google's later [embedding guidance](https://ai.google.dev/gemma/docs/embeddinggemma/inference-embeddinggemma-with-sentence-transformers) recommends clustering prompts for prototype similarity rather than assuming the standard classification task generalizes to arbitrary category names. Both document taxonomy prototypes and evidence units receive the *same* selected prefix. The initial default is therefore `clustering`; `classification` remains a configurable experiment.

EmbeddingGemma is an **encoder**. It returns vectors, not text, explanation or JSON decisions. The first implementation classifies by cosine similarity to embedded category descriptions, retains all category rankings and identifies the top two as **exploratory routing suggestions only**. These similarities are not probabilities, and top-two does **not** mean verified multi-label membership. Uncertain/other audit and calibrated specialist routing remain future work.

Lemonade's [embedding endpoint](https://lemonade-server.ai/docs/api/openai/) supports the FLM recipe and `POST /v1/embeddings`. Runtime defaults keep it on local loopback. Example smoke run after `pm update`:

```powershell
& "$env:LOCALAPPDATA\pipx\pipx\venvs\pm-tools\Scripts\python.exe" -m core.discovery_embedding_classifier --db "$env:USERPROFILE\.pm-tools\discovery_jira.sqlite" --project APS --limit 20
```

Run without `--limit` after validating the local model and performance. Pass `--config path/to/config.yaml` to apply your YAML `classification:` overrides. The classifier consumes the current indexed observations, including title-only Jira issues, without keyword exclusion. Existing legacy Confluence flattening and missing structure are not fixed by this model feature: the separate scoped source reindex remains necessary. The prototype retains per-source citations and cache keys in the SQLite index; it does not extract authoritative claims or create a graph.


### Lemonade FLM request compatibility

Lemonade FLM returned one 768-dimensional vector in a warm single-input request, but timed out on a request containing all eight taxonomy descriptions. The classifier now submits one scalar input per HTTP call (including each taxonomy prototype), rather than a list, to avoid unsupported or slow FLM batching. An initial cold model load was observed at about 133 seconds, so the configured per-request timeout is 240 seconds. This is a compatibility workaround, not proof that batching is unsupported on all Lemonade versions. Prototype embeddings are currently recomputed at the start of runs with uncached evidence; persistent prototype vector caching remains follow-up work.
