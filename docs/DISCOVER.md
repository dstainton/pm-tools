# Phase 2A: Configured discovery

Run `pm discover` to inspect local product and workstream configuration without calling Jira, Confluence, SharePoint, or a model.

```text
pm discover
pm discover --project APS
pm discover --product PLATFORM
pm discover --workstream GW
pm discover --export
pm discover --export --out C:\\reports
```

The ordinary command prints a compact account of configured products, workstreams, membership anchors, and resolved project scope. No file is produced unless `--export` is supplied. Export writes `discovery.md` to the configured output folder (or `--out`).

A workstream's Jira component, label, or custom field is a membership rule, **not evidence that the workstream is responsible** for the work described by an issue. Purpose, responsibilities, and boundaries are labelled *unknown* rather than inferred from names. Product goals are displayed only when configured. The implicit `UNASSIGNED` grouping is not a confirmed product.

This first slice reads **configuration only**. It does not test configured Confluence references or assert that sources are fresh or accessible; it does not classify issues or update configuration. Retrieval, synthesis, confirmation, and classification are separately proposed in [the Phase 2 design](PHASE2-DISCOVERY.md).

## Phase 2B: Optional source evidence

`pm discover --enrich` explicitly requests a **bounded, read-only** source check. It retrieves up to eight Jira Epics for each selected workstream with a configured membership anchor and attempts to read each product/workstream's explicitly configured Confluence page ID. The results are examples, not complete membership coverage or verified responsibilities. The command does not invoke a model or infer purpose, responsibilities, or boundaries. Retrieval errors are reported as unavailable, never as empty evidence.

```text
pm discover --enrich
pm discover --enrich --export
```

The Markdown export shows available page titles, IDs, update timestamps, short evidence excerpts, sampled Epic identifiers and summaries, and source failures. Source content is untrusted data. Workstream-purpose clarification and human confirmation are future, separately reviewed steps. This first evidence increment does not search for arbitrary Confluence pages by name, follow attachments, or crawl SharePoint.

## Phase 2B: Clarification queue

Use `pm discover --questions` to print up to five targeted questions about missing product goals and unconfirmed workstream responsibilities or exclusions. Combine with `--enrich` for Jira Epic and configured Confluence references, and with `--export` for a reviewable Markdown queue:

```text
pm discover --enrich --questions --export
```

Questions are deterministic and **not answered automatically**. They do not infer responsibilities from component names or Epic titles, or update configuration. The queue is a bounded set of prompts, not an exhaustive review or model-generated profile.

## Phase 2B: Evidence-grounded candidate profiles

Run `pm discover --enrich --propose --export` to explicitly invoke the configured model on bounded source evidence. This can take several model calls. It drafts **unconfirmed** candidate product goals and workstream purpose, responsibilities, or exclusions.

The model sees no more than five retrieved evidence items per entity, drawn from configured Confluence page excerpts and sampled Jira Epic titles. A product may use evidence from its selected workstreams. No more than five entities are considered in one run. The model must cite input evidence tags in every proposal, and unknown tags are rejected. **A matching tag is not a guarantee the sentence is supported**: review both the proposal and the cited excerpt before accepting any claim. No document crawling, profile confirmation, Jira writes, or configuration changes occur. `--propose` requires `--enrich`; neither is the default.

## Discovery inventory foundation

Use `pm discover --inventory --export` to enumerate **page metadata** inside configured Confluence scopes. Existing `confluence.team_page_id` or `confluence.root_page_id` creates a page-tree scope, including that page and all descendants. Configured product/workstream page IDs also form page-tree scopes. The default space is used only when no narrower page boundary is configured. Explicit `confluence.scopes` can contain `{type: space, space_key: POSM}` or `{type: page_tree, page_id: 12345, space_key: POSM}`. This is opt-in and does not invoke a model. It uses the existing fetch cache, pages through results, retains page identifiers, titles, dates and ancestors, and reports coverage as complete, partial, unavailable, or unconfigured. Each scope has a **100-search-row safety cap** in this first increment; if more pages exist, the result is explicitly **truncated**, never called comprehensive. This cap will be made resumable before full index-based discovery is considered complete.

The inventory does **not** fetch or rank every page body yet, and makes no inferred product assignments. It does not silently treat a Jira project or space name as proof of ownership. Further increments will add resumable full-space traversal, content extraction, passage indexing, local relevance ranking, and evidence synthesis.

### Intended URL-first onboarding

The longer-term goal is to accept Confluence space or starting-page URLs and Jira project URLs, extract identifiers and allowed scope, inventory the accessible data, propose product/workstream mappings and membership configuration, then ask for human confirmation before saving configuration. URL parsing, connection authorization, and configuration generation are **not** included in this inventory increment.

## Phase 2C Jira inventory and refresh (opt-in)

Run `pm discover --jira-inventory --export` to inventory all accessible issues in configured Jira projects, including closed issues and custom issue types. Jira results are persisted in a local SQLite database at the configured local state directory (`discovery_jira.sqlite`), with transactional pagination checkpoints. A large crawl may take several executions: continue running the same command until coverage is complete. No model is required.

After the initial crawl completes, use `pm discover --jira-refresh --export` to retrieve newly updated issues using a two-day overlap window. An incomplete query does not advance the refresh watermark or modify stored issues. This is a current-state refresh, **not** a changelog, comment history, or deletion/permission-loss reconciliation. The latter remain part of issue #60.

The discovery output distinguishes complete, partial, unavailable, and unconfigured source coverage. A complete source snapshot does not establish product ownership or a full history of field changes. Both commands are read-only with respect to Jira and do not alter operational product/workstream configuration.

### Jira historical comments

After the initial inventory, run `pm discover --jira-comments --export` to collect accessible Jira issue comments into local SQLite. Each invocation processes a bounded set of issues, with transactional per-issue pagination checkpoints, preserving Jira comment IDs, authors, original structured bodies, and created/updated timestamps. Repeat until coverage is complete. A missing comment endpoint or permission error is recorded as incomplete coverage. Comment data is not treated as accepted product policy or proof of ownership. The current collector captures a baseline snapshot, not yet continuous comment edits/deletions.

### Jira inventory reconciliation

Run `pm discover --jira-reconcile --export` after completing the baseline. This performs a complete fresh search of each configured Jira project and compares issue IDs against the local inventory. An issue no longer returned is flagged as **absent from the accessible project search**, not deleted. It may have been moved, made inaccessible, or removed. The command never deletes locally retained evidence, never uses partial results to establish absence, and does not assert that permissions are unchanged. It is a bounded-by-server-pagination read-only reconciliation rather than a substitute for historical changelog evidence.

### Jira project configuration observations

Use `pm discover --jira-structure --export` to inspect available project issue types, their reported hierarchy levels (when supplied by Jira), components and versions. Missing optional metadata is reported as unavailable rather than guessed. This is descriptive, read-only Jira configuration evidence. It does not infer ownership from component names or assume Initiatives are available in every Jira tenant.

### Historical collection progress

`pm discover --jira-history --export` and `pm discover --jira-comments --export` automatically work through all remaining issues, resuming from the persisted SQLite checkpoints. Interactive terminals show live processed/remaining counts, an approximate processing rate and ETA. Interrupted runs can be restarted safely. Use `--jira-limit 100` to cap the number of issues attempted in one invocation (for testing or constrained runs). Collection pauses when an entire batch fails to reduce repeated requests to inaccessible sources. Output redirected to a log uses periodic non-interactive progress notices.

### Offline evidence search (Jira)

Once Jira inventory, history and comment collection have finished, run `pm discover --index-jira`. This reads only the existing local SQLite database and builds an FTS5 index of Jira summaries, descriptions, directly assigned components and labels, comments, and recorded field changes. It makes **no Jira requests** and does not require a model. Re-running updates changed documents and leaves unchanged entries alone.

Search with `pm discover --search-evidence '"APS P2P"' --export` or `pm discover --search-evidence 'gateway'`. Use `--project APS` to filter by project. Each match includes a stable Jira issue/comment/changelog identifier and distinguishes issue content, comments and historical change observations. Search results are evidence, not confirmed ownership or taxonomy. SQLite FTS5 supports quoted phrases, token prefixes and Boolean searches; malformed FTS expressions produce an error rather than being silently reinterpreted.

This initial index covers collected **Jira** evidence only. Confluence page content, historical source reconciliation, richer field filters, document heading extraction and temporal taxonomy remain separate increments under #58.

### Concept-aware search, first increment

The offline concept registry (`core.discovery_concepts`) maintains independent candidate and confirmed concept names and source-cited aliases, including abbreviated and historical names. A term can expand search only when both the concept and that specific alias have been **explicitly confirmed** and the lookup matches the configured project scope. The query `pm discover --search-concept 'APS P2P' --project APS` searches the exact phrase and any confirmed, scoped aliases, citing the alias evidence on each result. Without confirmed aliases, it retrieves only the exact phrase. It never automatically equates similarly spelled terms or treats all occurrences as the same organization-specific concept. All source evidence remains unmodified.

This PR intentionally provides **registry storage and deterministic lookup**, not automatic candidate discovery, confirmation UI, cross-project alias reasoning, or model-assisted disambiguation. Registration and promotion use the Python API until a human-review workflow exists. Do not treat this registry as product configuration or assume aliases in the APS example are globally applicable.

### Automatic alias candidates (first increment)

Run `pm discover --alias-candidates --project APS --export` after `--index-jira`. The local, deterministic candidate miner uses Schwartz–Hearst-style backward character alignment to recognize explicit abbreviation definitions such as `Secure Data Exchange (SDX)` in indexed issue titles and bodies, preserves source citations and project scope, and stages results as **unconfirmed** concepts/aliases for review. It does not invoke Jira, Confluence or an LLM; it does not auto-confirm relationships or modify organization configuration. Only confirmed aliases affect `--search-concept` results. This narrowly scoped first pass does not infer renames from co-occurrence, identify `P2P` as equivalent to `APS P2P`, or establish authoritative product naming decisions.

### Confluence content indexing (initial scoped increment)

Run `pm discover --index-confluence` after configuring authorized Confluence scopes. The command lists pages within the configured space or page tree, retrieves those page bodies, removes storage-format markup, and indexes their text alongside the existing Jira evidence in local SQLite FTS5. Each indexed page retains its original Confluence page ID and is searchable using `--search-evidence`. Alias candidate extraction can also examine indexed Confluence page text; pass no Jira `--project` filter unless it matches the intended Confluence space key.

**Coverage:** This first increment inherits the Confluence metadata inventory's 100-search-row per-scope limit. If additional pages exist, the command reports incomplete coverage and does not claim full ingestion. Failed pages are itemized. No Confluence changes are written. Resumable uncapped collection and richer page/heading attribution remain open tasks under #58.

Native Confluence expansion in this PR: space-scoped blog posts are indexed alongside regular pages, and page/blog labels are searchable. Blog pagination has its own per-space cap and explicit incomplete coverage. Page-tree scopes remain page-only and are **not** broadened to a whole space for blog discovery. Attachments are excluded. Comments, live docs, whiteboards, and databases need separate supported API paths or metadata adapters and are not yet retrieved by this PR; they must not be reported as completely indexed.

Native Confluence comments are retrieved only for pages and blog posts inside previously authorized inventory scopes. Comment bodies are indexed with parent-linked citations (`confluence:<parent-id>#comment-<comment-id>`). Each parent has a bounded 100-comment scan in this increment, and over-limit or inaccessible comments make ingestion incomplete rather than silently claiming coverage. Attachments remain out of scope. Live docs, whiteboards, databases and resumable uncapped traversal remain future increments.

### Checkpointed Confluence page inventory

Run `pm discover --confluence-crawl` repeatedly to resume a read-only, scope-bound inventory of regular Confluence pages. Each invocation processes at most 100 search rows per configured scope, stores progress in the local discovery SQLite database, and resumes the next offset on a later run. This is a work-bounded increment, **not a permanent 100-row coverage ceiling**. Each scope is identified by its resolved space and page-tree root. A changed scope creates a separate checkpoint; unrelated pages cannot be silently pulled in. Collection errors report incomplete status. This first iteration stores page metadata; it does **not yet feed the checkpointed inventory into `--index-confluence`**, which remains separately bounded. Blog posts, comments, and modern native content types will be integrated into the checkpointed collector in later increments.

### Index pages from checkpointed Confluence inventory

`pm discover --index-confluence` now uses the saved `--confluence-crawl` page inventory, including pages beyond the former 100-row inventory cap. Complete coverage is claimed only when every configured checkpoint is complete and indexing of pages, bounded comments, and blogs succeeds. Run `--confluence-crawl` again for incomplete page scopes before relying on the index for comprehensive discovery. Blog and comment retrieval still have their separate 100-row caps; those are subsequent collection improvements. Page bodies are fetched read-only from the authorized page IDs and retain Confluence citations.

### Terminology candidate clustering

Run `pm discover --concept-clusters --project APS --export` after `--alias-candidates`. The deterministic offline clustering groups candidate definitions only when their canonical names agree after conservative case, whitespace, punctuation, and program/programme spelling normalization within a source scope. Different names sharing an acronym are **not merged**; conflicting abbreviation meanings are explicitly marked ambiguous, with all source citations retained. Confirmed and candidate states remain distinct, and this report does not claim product ownership, formal renames, or contextual equivalence from mere co-occurrence. It is the first explainable grouping stage, not model-assisted semantic clustering.

### Contextual terminology relationship proposals

`pm discover --term-relationships --project APS --export` scans previously indexed Jira and Confluence text for explicit, sentence-bounded wording such as `APS P2P (formerly SDX)`, `X renamed to Y`, and `X replaces Y`. It returns cited, unconfirmed relationships with verbatim evidence excerpts, counts, and original project scope. Co-occurrence alone never implies equivalence. The tool does not automatically adopt a rename or update any confirmed alias mapping. Results are candidates for human review, not semantic similarity scores. The discovery summary distinguishes this offline evidence analysis from live API retrieval.

### Candidate terminology evidence evaluation

Run `pm discover --evaluate-terms --project APS --export` to generate conservative terminology pairs from explicit rename/replacement claims and competing acronym expansions in the local indexed registry. For each pair, a bounded offline scan retrieves passages mentioning both terms, preserves Jira/Confluence citations, and flags explicit claims, possible distinctions, and co-occurrence. Contradictory claims yield `conflicting_evidence`. All classifications are **unconfirmed evidence triage**, not semantic equivalence or automated name adoption. A local language-model classification stage and broader candidate generation from historical references remain future work. The default caps are 100 pairs and 8 evidence passages per pair.

### Contextual evidence dossiers

`--evaluate-terms` additionally proposes term/code comparisons from repeated mentions within at least two independent indexed documents when one term already belongs to the candidate concept registry. This can surface transitions without explicit `formerly` wording, but **co-mentions are not proof of equivalence**. Dossiers keep a single passage per source citation, preserve dates and source types, and can include single-term context; assessment remains unconfirmed. Candidate selection and evidence retrieval are bounded, and indexed content may be incomplete or stale.

### Typed candidate concept graph

Run `pm discover --concept-graph --project APS --export`. This first, deterministic graph stage reads the offline candidate concept registry and indexed Jira/Confluence documents. It preserves source-backed identity aliases and detects explicit, directed relationship statements such as `ITK depends on SDX`, `X integrates with Y`, `X is part of Y`, and `X is delivered by Y`, alongside cited historical-name and replacement claims. Each edge is **unconfirmed**. Incidental co-occurrence produces no typed edge. The CLI shows up to 100 identities and edges with complete totals reported separately; no approved mappings or configuration are changed. Broad semantic interpretation, model classification and full-corpus relationship discovery are not yet implemented.

### Optional local-model graph review

Run `pm discover --concept-graph-model --project APS --export` to review cited
candidate edges with the **existing** `model:` configuration in
`~/.pm-tools/config.yaml`. There is no separate model setup. The reviewer
calls `core.model.call_model`, sharing the existing endpoint, model ID,
authentication, timeout, JSON sampling, non-thinking settings, run budget, and
model cache. It reviews up to 20 candidate edges and requests structured
relationship proposals grounded in the supplied citations. All classifications
remain unconfirmed; invalid responses are marked unresolved and no confirmed
concept registry or product configuration changes. The configured inference
endpoint should remain local, as with other pm-tools model operations. This
stage classifies existing explicit graph candidates; it does not yet discover
new relationships from unstructured narrative.
