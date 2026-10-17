# Offline discovery: evidence, identity, and review

This is the supported way to establish a source-linked baseline before
changing products, workstreams, or Jira issue classifications.

## Commands

Fast, no local model call:

```powershell
pm discover --concept-graph --project APS --export
```

Full, bounded model-assisted review:

```powershell
pm discover --concept-graph-model --project APS --concept-graph-max-edges 24 --export
```

The review limit controls the number of local-model inference calls, **not**
the number of discovered candidate pairs. The complete contextual candidate
queue is exported for subsequent human review, including source references and
any explicit directed relationship hints. Raise the limit to 40 only if needed.

`--concept-graph-thinking-compare` remains an evaluation command that sends
the same eight candidates through two requested backend settings. It does not
prove that the server honours its thinking flag. It is not a prerequisite for
normal discovery.

## Index scoped Confluence documents

First populate the offline source index:

```powershell
pm discover --confluence-crawl --index-confluence --project APS
```

The combined command resumes checkpointed inventories within authorized
page-tree scopes and indexes the resulting pages. It reports incomplete
coverage rather than claiming that a partial collection is exhaustive.
A standalone index command prefers a matching existing checkpoint.

When all authorized Confluence scopes are page trees and the installation
has exactly one configured Jira project, these documents are associated
with that project for filtered discovery. For whole-space or multi-project
scopes, no such association is inferred. Inspect the reported coverage.

## Corrected Confluence crawl and recovery

Previously, incomplete page-tree scans repeatedly returned the same 25 results
at CQL offset 1000. Page-tree collection now uses the Confluence Cloud v2
`GET /pages/{id}/descendants` endpoint and persists its opaque pagination
cursor. This includes all descendant depths and is independent of CQL offset
pagination. The collector dispatches by the root's actual content type, for example
`/pages/{id}/descendants` for an APS page and
`/folders/{id}/descendants` for SDX or ITK folder roots. Non-page nodes
are retained in a lightweight hierarchy inventory so completed ancestor
trees can safely cover nested folder scopes. Only actual pages are sent to
body and comment indexing.

Old incomplete page-tree checkpoints and previously completed v3 page-tree
scopes are revalidated once under content-type-aware crawling. All prior
page records and full-text evidence are retained; folder root records are
excluded from page-body indexing. After migration, completed v4 scopes
are not rescanned. Whole-space collection retains the
bounded CQL offset approach.

Repeated identical result pages or a non-advancing cursor fail safely with
`incomplete` status and a specific error rather than advancing indefinitely.
The CLI reports accepted new pages, duplicate records and ancestry metadata
warnings independently of the search offset.

A completed ancestor team tree can also satisfy nested workstream scopes if
its inventory explicitly contains their root pages. A shared Confluence
space alone never authorizes this optimization. Covered child scopes are
shown as complete without fetching the same descendant tree again.

Use the existing collection command after updating the tool:

```powershell
pm update
pm discover --confluence-crawl --index-confluence --project APS
```

Confirm the output reports plausible **new page counts**, `complete`
inventory, and any remaining comment errors separately. A repaired
checkpoint never discards previously indexed source documents.

## Unpublished pages and v1 content 404 responses

The v2 descendants API includes a page `status` field. The crawler stores
this metadata for newly encountered page rows, while the body indexer remains
responsible for verifying published content before adding evidence.

If the v1 page-content endpoint returns 404, the indexer checks the current
v2 page with `body-format=storage`. It indexes that content **only** when
v2 explicitly reports `status=current` and returns a readable storage body.
If no current page exists, it performs a **metadata-only** v2
`get-draft=true` probe. Only an explicit `status=draft` response
counts as a confirmed excluded draft. It never retrieves or indexes the
unpublished draft body. A page that cannot be confirmed current or draft
remains an error and keeps evidence completeness false.

The index output reports confirmed draft exclusions and published v2
fallbacks, including their page IDs and titles. Those results are also
recorded as page status in the local checkpoint table. Confirmed drafts do
not count as missing evidence; unavailable or restricted pages still do.
The migration adds a nullable status column without deleting existing
inventory or full-text records.

Run `pm discover --index-confluence --project APS` after updating
without repeating the completed Confluence crawl. No write requests are
sent to Atlassian.

## Quality controls after the first APS profile evaluation

The initial 40,000-character APS run showed that a single large prompt can
produce no claims from authoritative product documentation, while unrelated
Jira components and Confluence field values can be misidentified as products.
A model's syntactically valid `{"claims":[]}` is **not** evidence that the
source material lacks a product description.

Profile discovery now reserves **candidate profile** status for explicit
published Confluence Product/Workstream/Capability headings and configured
names used as search hints. Jira components remain available as separate
`component_leads` with issue counts, but **component-only names are not sent
to the model**. Generic entries such as `user`, `client`, `research` and
`operational` remain useful for issue filtering, not inferred services.
Field values such as `Service: https://...` no longer become a candidate.

Model-assisted profile extraction selects named definitions before general
planning notes. Where a Confluence page contains multiple capability cards,
the matching card's own content is isolated so the model does not attribute
another product's scope or purpose to the target.

A large selected evidence budget is processed in **multiple focused passes**
(about 10,500 evidence characters per call), rather than a single prompt
that risks exceeding the local model server's actual context window.
Each pass uses the same strict citation/JSON validation and one repair attempt
if necessary. Distinct supported claims are merged, preserving exact cited
sources. The exported report includes the number of inference passes,
empty passes, repairs and validation failures. A review with zero claims
is reported as `no_supported_claims`, not a successful description.

This improves retrieval and attribution, but does not prove the semantic
correctness of a model-generated claim; a human still verifies the cited
passages before authorizing configuration changes. Neither the Jira nor
Confluence evidence stores need to be crawled again.

## Substantial offline source context for one-time inference

Both model-assisted discovery modes now use substantially more of the original
indexed source content. The **default is up to 80,000 source characters and
24 indexed source records per inference call**, rather than just five to eight
excerpts of 500–750 characters. This is a character budget, **not a token
count or a guarantee of what your model server will accept**.

The evidence assembler reads the full previously indexed bodies of published
Confluence pages and Jira issues, selects substantial source windows around
concept mentions (including mentions in different parts of a page), expands
the candidate's original citation set using scoped full-text retrieval, and
retains each document title, timestamp, type and exact source citation.
Comment evidence is only included when already cited; Jira changelog records
are excluded from current-state inference. Source content from another Jira
project is never included.

A long page can exceed the selected per-document allocation; the prompt
marks omitted portions rather than presenting separated windows as one
continuous quotation. Outputs state exactly how many source records and
characters were passed and list every supplied citation. The response still
requires permitted citations and remains an *unconfirmed proposal*.

For a deeper, less time-sensitive first analysis:

```powershell
pm discover --discover-profiles-model --project APS --profile-model-limit 12 --discovery-context-chars 120000 --discovery-context-documents 32 --export
```

For relationship review:

```powershell
pm discover --concept-graph-model --project APS --concept-graph-max-edges 60 --discovery-context-chars 120000 --discovery-context-documents 32 --export
```

Before requesting contexts this large, verify that the *actual local inference
server* is configured with a context window sufficient for the entire prompt,
including the instructions, metadata and response budget. Rough character-to-
token estimates vary by model and language; the CLI does not claim to know the
backend's live context window. Insufficient capacity may produce rejected,
truncated or unreliable responses. The maximum supported context budget is
400,000 characters per relationship/profile review call. Source selection
is capped by the requested document count; additional source documents may
remain unreviewed.

This is **retrieval of more context**, not additional confirmed knowledge,
and it does not change the original indexed database or configuration.

## Independent offline product and workstream profile discovery

Start with the existing local Jira and Confluence evidence index, **without
accepting configured product groups as authoritative**.

```powershell
pm update
pm discover --discover-profiles --project APS --export
```

The deterministic stage derives provisional names from labelled Confluence
content such as `Product:`, `Workstream:` and `Capability 4:`, from Jira
issue components (counted once per issue), and from existing configuration
used only as a *search hint*. It retrieves and ranks independent published
Confluence pages and Jira issue descriptions referencing each name, with
source citations. It does **not** read unpublished drafts, or turn Jira
comments and changelog records into new apparent products. It excludes
component-only singletons. It compares candidates to configured names, flags
kind conflicts, and marks unconfigured names. Every candidate remains
unconfirmed: no product, alias, hierarchy, or component assignment is written.

Inspect all the displayed candidates and review evidence excerpts in
`discovery.md`. By default 40 candidates are retained, including evidence
for each, and totals beyond the limit are explicitly reported. The name
extraction is intentionally conservative: unlabeled products mentioned only
in prose may be absent, and labels may describe features rather than products.

Optionally use the already configured, local inference endpoint:

```powershell
pm discover --discover-profiles-model --project APS --profile-model-limit 6 --export
```

The bounded model stage sees at most five source excerpts per candidate,
returns up to 12 field-level claims using a strict JSON schema, and must
cite an exact provided source for every claim. Valid fields are kind, purpose,
responsibility, boundary, parent and alias. Unknown is acceptable. Malformed
or invalid output gets one repair request and must still pass the validator.
All statements remain unconfirmed. The command does not claim that a Jira
component alone proves ownership, that implementation tasks are permanent
responsibilities, or that a shared dependency proves product membership.

No Jira or Confluence API calls are made, and no source records are changed.
The existing concept graph remains a separate, optional stage until proposed
profiles have been reviewed. Local inference uses existing `model`
configuration and caching; keep the `--profile-model-limit` small on machines
with a smaller local model.

## Evidence-aware discovery and Jira issue grouping

Local discovery retains every indexed record, but no longer treats a Jira
comment or changelog item as an independent issue or product definition.

- **Confluence page and blog content** receives first priority when selecting
  descriptive product/workstream documentation. Confluence comments can
  support, but not outrank, a matching published page.
- **Jira issue descriptions** are next. A Jira issue, its comments and its
  changelog rows count as **one parent issue** when calculating independent
  sources and choosing descriptive leads.
- **Jira comments** can offer supporting relationship evidence. A clearly
  stated relationship in a comment can replace a weaker mention from the
  same issue, but it is not counted as another independent source.
- **Jira changelogs** remain searchable and available to historical taxonomy
  and membership analysis. They no longer create general current-state
  relationship candidates from mere text proximity or unrelated field edits.

The command-line and Markdown discovery report distinguish actual Jira issues
from comments and changelog records. Profile-lead counts describe independent
parent sources, alongside the raw number of matching evidence records. Source
citations remain exact, and neither ranked leads nor relationship candidates
change the confirmed concept registry or configured product ownership.

To inspect the locally stored evidence without re-crawling Jira or Confluence:

```powershell
pm update
pm discover --concept-graph-model --project APS --export
```

The model's bounded review limit is unchanged; the input ordering and grouping
now favour descriptive evidence over supporting history.

## Trust boundaries

1. The configured products and workstreams are **configuration facts**, not
   evidence that a team owns a capability. The tool never silently rewrites
   them from discoveries.
2. Indexed Jira and Confluence text supplies **source observations**. The
   report names the indexed source counts and provides excerpts for potential
   product and workstream definition pages.
3. An alias may be used to *locate* the same project-scoped concept in this
   read-only candidate graph only when unambiguous. A shared acronym cannot
   merge concepts. Candidate aliases are not promoted to confirmed synonyms
   for external searches.
4. Explicit sentence patterns may identify **typed relationship candidates**
   such as `depends_on`, `integrates_with`, `part_of`, or
   `validated_against`. Direction is retained and each candidate carries an
   exact source citation. Co-mentions alone do not prove a relationship.
5. A local model may offer **unconfirmed, source-cited proposals**. It cannot
   confirm concept identity, responsibility, product boundaries, or a
   relationship. Unknown is an acceptable outcome.
6. The report states how many candidates were reviewed and how many remain
   unreviewed, so a bounded model run cannot be mistaken for a complete
   semantic assessment.

## Interpreting the report

- **Unconfirmed typed concept graph**: deterministic, source-supported
  candidates. Not an accepted organizational map.
- **Indexed evidence for product and workstream definitions**: passages worth
  reading, not generated statements of purpose or ownership.
- **Contextual candidate queue**: all project-scoped canonical pairs that
  co-occur in bounded indexed passages, prioritized by explicit relational
  language. Unreviewed items remain visible.
- **Local model review**: source-grounded classifier suggestions, with
  unreviewed count and any schema errors or repair attempts.

If the report has no Confluence evidence, or insufficient text identifying
the actual product goals and responsibilities, that remains a **data coverage
gap**. Re-run the authorized scoped Confluence indexing workflow if needed.
Changing prompts or enabling thinking cannot create missing source material.

## Acceptance criteria

- No duplicate pairs formed by canonical name plus its unambiguous alias.
- Shared acronyms and ordinary words do not create false relationships.
- Typed candidate direction and citations survive both deterministic
  extraction and model review.
- The full offline candidate queue is exported even when inference is bounded.
- Product and workstream definition leads are cited, and unknown
  responsibilities remain unknown until human verification.
- Existing commands remain read-only by default, and CI passes across the
  supported Python and operating system matrix.

For current production terminology, use approved organizational definitions
rather than assuming older Jira component names describe current products.
