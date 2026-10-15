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
