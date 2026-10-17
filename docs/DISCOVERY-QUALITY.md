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
