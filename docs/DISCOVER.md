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
