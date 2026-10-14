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
