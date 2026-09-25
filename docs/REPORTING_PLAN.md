# Tranche 5 — reports by Epic, Confluence as a source, and three audiences

A plan for making every narrative report more useful to the person reading
it: a product manager, leadership, or a partner outside the company.

Nothing here is built. This is a plan. It is written to be implemented step
by step by someone (or some model) who has not read the rest of the code, so
it names files, functions, data shapes, prompts, and tests explicitly. Where
the plan says "exactly", follow it exactly. Where it gives a default, the
default can change later without changing the design.

Vocabulary follows `docs/TERMINOLOGY.md`: config keys and Jira fields use
Jira's word (Epic, Story, Component, assignee); prose uses Scrum's word
(Sprint, Sprint Goal, Product Goal, Definition of Done, stakeholders).
`workstream` stays `workstream`.

---

## Contents

- Part 1 — What the reports do today (findings, with evidence)
- Part 2 — The rules this plan keeps
- Part 3 — The new report shape
- Part 4 — Confluence as a source
- Part 5 — Audiences: pm, leadership, partner
- Part 6 — Every report, per audience
- Part 7 — What the model is asked, and what it costs
- Part 8 — Implementation steps, in order
- Part 9 — Config and migration (`config_version` 6)
- Part 10 — Tests and fixtures
- Part 11 — Not in this plan, and choices worth revisiting
- Appendix A — Pitfalls for the implementer
- Appendix B — Exact prompts

---

## Part 1 — What the reports do today

Findings below come from running `pm report` against the stand-in Jira in
`tests/fake_jira.py` with the end-to-end fixture in
`tests/test_cli_end_to_end.py`, and from reading the code paths named.

### 1.1 The reference table is a second set of IDs for things that already have one

`sources.fetch_jira` tags every Jira item `SDX-J1`, `SDX-J2`, …;
`fetch_confluence` tags pages `SDX-C1`; `fetch_sharepoint` tags `SDX-S1`. The
model cites those tags, and `commands/report.py::build_report` prints a
table at the end mapping each tag to a link. The live run printed:

```
| SDX-J1 | Jira | APS-10: Publish exchange status endpoint | [SDX-J1](…/browse/APS-10) |
| SDX-J6 | Jira | APS-50: Expose exchange metrics on the API gateway | [SDX-J6](…/browse/APS-50) |
| APS-J2 | Jira | APS-50: Expose exchange metrics on the API gateway | [APS-J2](…/browse/APS-50) |
| SDX-C1 | Confluence | Decision: certificate rotation cadence | [SDX-C1](…/wiki/pages/1001) |
```

Three problems:

- A reader sees `[SDX-J1]` in prose and must scroll to the table to learn it
  means `APS-10`. The Jira key is shorter than the lookup.
- The same issue gets two tags when two workstreams claim it (`APS-50` is
  `SDX-J6` and `APS-J2`).
- The table is one flat list in fetch order. It is not grouped by
  workstream, Epic, or topic, so it does not help anyone catch up.

### 1.2 There is no Epic level

The report fetches two things per workstream: in-Sprint child work (scope
`report`) and the open Epics (scope `roadmap`). Both go into one flat
material list for the model. The fetch (`DEFAULT_REPORT_FIELDS` in
`core/sources.py`) does not ask for `parent`, so nothing knows which Epic a
Story sits under. The report goes Product → Workstream → seven model
headings. Nobody can read "what is happening on Epic APS-1".

### 1.3 Confluence is narrow and cut short

- **Only labelled pages.** The CQL is `space = X AND label IN (decision,
  risk, dependency)` (`filters.build_cql`). A requirements page, a design
  page, or a blog post that changed this week is never seen.
- **Only one content type by accident.** No `type` clause, so the v1 search
  returns whatever matches. Blog posts, databases and smart-link embeds are
  not distinguished.
- **The body is cut to 400 characters before the page budget applies.**
  `sources.strip_html` ends with `short(text, 400)`. `core/pages.py` then
  trims to `pages.excerpt_chars` (2000), which can never be reached. Checked:
  a 2,800-character body comes out of `strip_html` at 403 characters.
- **`pages.section_chars` is unused.** It is defined in `core/pages.py`
  `DEFAULTS` and in the migration, and nothing reads it.
- **Uncached.** `pages.cache_fetch` and `pages.summary_key` exist and are
  never called. `fetch_confluence` hits the network every run and
  `--cached` does nothing for it.
- **No link from a page to an Epic.** Pages sit in the workstream's material
  next to issues with nothing saying which Epic they concern.

### 1.4 The window flags do not change what is fetched

`pm report --since` and `pm report --sprint` were added in 0.11.0.
`commands/report.py::run` calls `prepare()` for every workstream **before**
it resolves the window, and never passes the window in. The only effect of
the flag is that last-report memory is not saved. Checked with
`pm report -w SDX --since 2026-06-01`: the Confluence query still said
`lastmodified >= '2026-09-18'` (seven days) and the Jira queries were
unchanged.

Separately, `prepare()` reads `previous.get("_ran_at")` from the top level
of the state file, but `_ran_at` is stored per workstream
(`previous["SDX"]["_ran_at"]`). The page cutoff is therefore always `None`.

`pm brief` accepts `--since` and `--sprint` and does not read either.

### 1.5 Smaller defects on the same path

- The Portfolio table counts items per workstream with
  `it["ref"].split("-")[0]`. It works only because the tag starts with the
  workstream abbrev. Change the tag and the count silently breaks (and
  `APS-10` would count toward the `APS` workstream).
- The model writes `### What changed since last week`, which is the same
  heading level as the workstream heading (`### Secure Data Exchange`) when
  products are shown. The report's outline is flat.
- `pm report --json` is accepted by the parser and does nothing.
- `commands/publish.py::markdown_to_storage` handles `#`, `##`, `###`,
  `- ` bullets, tables and links. It does not handle `####`, `**bold**`, or
  indented bullets. Anything this plan adds must stay inside what publish
  can render, or publish must learn it (Step 6 does the latter).
- A published report keeps the same title every week, so `pm publish`
  updates one page in place. That is fine for one audience. With three, the
  titles must differ or the leadership run overwrites the PM page.
- `output.audience` ("stakeholders") is a free-text word pasted into the
  prompt. There is no notion of who a report is for.

---

## Part 2 — The rules this plan keeps

These already hold in the codebase. Every step below must keep them.

1. **Rules decide what is true; the model writes prose.** Which issues are
   in a report, their status, which Epic they sit under, an Epic's progress,
   and whether an Epic is "at risk" are computed. The model summarises and
   narrates.
2. **Every claim cites a real source, and every citation is a link.** After
   this plan, the reader never sees an invented tag.
3. **One front door.** No new verbs. `pm report`, `pm brief`,
   `pm release-notes`, `pm metrics` and `pm warm` gain a flag; nothing new is
   added to the command list.
4. **Read-only unless the user confirms.** Nothing here writes to Jira. The
   partner report is never published without a person reading it first.
5. **Cache at the granularity of the thing that changes.** A page summary is
   keyed on page id and version, so an unedited page is never summarised
   twice.
6. **A config written before this change keeps working.** New keys have
   defaults in code; `pm update` inserts them; nothing is replaced.

---

## Part 3 — The new report shape

### 3.1 Citations: the Jira key is the tag

- A Jira item's `ref` becomes its key: `APS-10`. The model cites `[APS-10]`.
- A document (Confluence or SharePoint) gets a short tag **local to one
  model section**: `D1`, `D2`, … numbered by page id ascending so the
  numbering is stable between runs. The model cites `[D1]`.
- After the model replies, `core/citations.py::resolve()` rewrites every
  bracketed tag into a Markdown link:
  - `[APS-10]` → `[APS-10](https://…/browse/APS-10)`
  - `[D1]` → `[Decision: certificate rotation cadence](https://…/pages/1001)`
    (title cut to 60 characters on a word boundary)
  - `[APS-10, D1]` → both links, separated by `, `
  - A tag that is not in that section's map is removed. The count is
    printed to the terminal and a line is added under the section:
    `_1 citation removed: it was not in the material._`
- The reader therefore sees issue keys and page titles, never `D1` and never
  `SDX-J1`.

### 3.2 The PM report, as it should read

This is the target output for the default audience. Headings in angle
brackets are placeholders.

```markdown
# Weekly State-of-Product Report
_Audience: Product management · Window: since 2026-09-18 (last report) · Generated 2026-09-25_

## At a glance

| Product | Workstream | Epics active | Items in window | Moved | Blocked | Docs changed |
|---------|------------|-------------:|----------------:|------:|--------:|-------------:|
| IP | SDX | 2 | 6 | 1 | 0 | 3 |
| IP | APS | 1 | 2 | 0 | 0 | 1 |

## Integration Platform (IP)

Product Goal: <product_goal>

### Increment
<Definition of Done list, unchanged>

### Secure Data Exchange (SDX)

#### What changed since last week
- Status endpoint moved to review, waiting on the certificate review. [APS-10](…)
- Rotation cadence decided: every 90 days, automated from October. [Decision: certificate rotation cadence](…)
#### Progress this sprint
…the other five model headings, one level below the workstream…

#### Epics

**[APS-1](…) Secure exchange platform** — In Progress · 3 of 7 done · due 30 Oct · On track

- Moved: [APS-10](…) Publish exchange status endpoint — To Do → In Review
- In this Sprint: [APS-11](…) Fix stuff (In Progress), [APS-12](…) Wire retry handling (To Do)
- Comment: 2026-09-25 A. Lee on [APS-10](…): Waiting on the certificate review.
- Doc: [Decision: certificate rotation cadence](…) — decision, updated 24 Sep by Dana. Certificates rotate every 90 days, automated from October.

**[APS-3](…) Housekeeping and compliance** — To Do · 0 of 1 done · Epic in no workstream

- In this Sprint: [APS-30](…) Rotate exchange signing certificates (To Do, overdue 4 days)

**Not under an Epic**

- In this Sprint: [APS-50](…) Expose exchange metrics on the API gateway (In Progress)

#### Documentation changed

- [SDX runbook index](…) — page, updated 23 Sep by Sam. Lists the runbooks for certificate rotation and key escrow.
- [Partner onboarding tracker](…) — database, updated 22 Sep. (Listed by title.)

## Sources

### Secure Data Exchange (SDX)

| Epic | Item | Type | Status | Assignee | Updated |
|------|------|------|--------|----------|---------|
| APS-1 Secure exchange platform | [APS-10](…) Publish exchange status endpoint | Story | In Review | A. Lee | 25 Sep |
| APS-1 Secure exchange platform | [APS-11](…) Fix stuff | Task | In Progress | B. Ray | 24 Sep |

| Epic | Document | Type | Kind | Updated | By |
|------|----------|------|------|---------|----|
| APS-1 Secure exchange platform | [Decision: certificate rotation cadence](…) | page | decision | 24 Sep | Dana |
| — | [SDX runbook index](…) | page | other | 23 Sep | Sam |

# Delivery metrics
<unchanged appendix>
```

What changed from today, in one list:

- Header says who it is for and which window it covers.
- "At a glance" replaces "Portfolio". It is counted from item fields, not
  from tag prefixes.
- The seven model headings move one level below the workstream heading.
- A deterministic **Epics** block per workstream: every Epic with activity
  in the window, its status, child progress, target date, and a signal
  word, then the moved items, in-Sprint items, windowed comments, and
  changed documents under it.
- A **Documentation changed** block for pages that did not match an Epic.
- **Sources** replaces "References": grouped by workstream, then Epic, with
  the facts a reader scans for. No invented IDs.

### 3.3 Epic facts (deterministic)

For each Epic shown, computed in `core/epics.py`:

| Field | How |
|---|---|
| `status`, `status_category` | From the Epic's own Jira status. Category key is `new`, `indeterminate`, or `done`. |
| `children_total`, `children_done`, `children_in_progress` | One query per workstream: `parent IN (<epic keys>)`, all statuses, fields `status,issuetype,labels,updated`, `max_items=0`. Direct children only (Stories, Tasks, Bugs), so Sub-tasks do not double count. |
| `blocked` | Children where `core.blocked.is_blocked(child, cfg)` is true. |
| `due` | The Epic's `duedate`, if any. |
| `moved` | Children in the window whose status changed since last report (from `state.compute_changes`). |
| `in_scope` | `False` when the Epic is not one of this workstream's Epics (it was reached by walking up from a child). Printed as "Epic in no workstream" or "Epic in <abbrev>". |
| `signal` | See the rule below. |

**The signal rule.** Evaluate in this order; the first match wins. The
reason text lists every fact that triggered it.

1. `Done` — the Epic's status category is `done`.
2. `At risk` — any of: a blocked child; the Epic's due date is before today
   and it is not done; the due date is within `audiences.leadership.at_risk_due_days`
   (default 14) and fewer than half its children are done.
3. `No movement` — neither the Epic nor any child was updated inside the
   window.
4. `Not started` — no child is in progress or done, and the Epic's category
   is `new`.
5. `On track` — anything else.

The report footer prints one line saying the signal is a rule, and names
it: `_Signal is a rule, not a judgement: At risk means a blocked item, a
passed due date, or under half done within 14 days of the due date._`

---

## Part 4 — Confluence as a source

### 4.1 What to read

| Confluence type | Read how | Default |
|---|---|---|
| `page` | Body read, summarised, cited | on |
| `blogpost` | Body read, summarised, cited. Blog posts are where teams post updates. | on |
| `database` | Title and link only ("Database updated") | on, title only |
| `embed` (smart link) | Title and link only | on, title only |
| `whiteboard` | Not read | off (add to `title_only_types` later) |
| `folder` | Not read; it has no content | off |
| `attachment` | Not read in this tranche | off |
| page comments | Not read in this tranche | off |

Config: `confluence.content_types` (default `[page, blogpost]`) and
`confluence.title_only_types` (default `[database, embed]`). The CQL clause
is `type IN (<both lists joined>)`.

`pm doctor` runs the CQL once per configured type with `limit=1`. A type the
site rejects (400) is reported as a warning naming the key to edit, and the
report drops that type for the run instead of failing.

### 4.2 Which spaces

- Each workstream's `confluence_space` (unchanged key).
- Optional new `confluence_space` on a **product**. Pages found there are
  matched to that product's Epics (all workstreams in the product).
- With `pages.scope: space` (the new default), every changed page in the
  space is read. `confluence_labels` no longer filter the fetch; they
  classify the page (`kind`). With `pages.scope: labelled`, today's
  behaviour: only labelled pages.
- `pages.follow_jira_links: true` (default) also reads Confluence pages that
  an Epic links to (Jira remote links), from any space, if they changed in
  the window. This is the most reliable page→Epic signal Jira has.

### 4.3 Which window

The report window from Step 1 (`core/window.py`), never
`confluence.lookback_days`. The CQL clause is
`lastmodified >= "<window start as YYYY-MM-DD>"` and results are ordered
`order by lastmodified desc`. `confluence.lookback_days` is kept only for
`pm brief`'s first run with an audience when there is no other window, and
documented as such.

### 4.4 What to leave out

- Pages under `publish.confluence.parent_page` in `publish.confluence.space`
  (the tool's own published reports). Detected from the `ancestors` expand.
- Pages with the label `pm-report`. `pm publish` adds that label to every
  page it creates or updates (Step 7), so this works in any space.
- Pages outside the window (defensive re-check in Python after the CQL).

### 4.5 What one page record holds

`core/pages.py::normalise(raw, base_url)` turns one Confluence API result
into this dict. Every later step relies on these keys.

```python
{
    "source": "Confluence",
    "uid": "confluence:1001",       # stable identity for state diffs
    "page_id": "1001",
    "type": "page",                 # page | blogpost | database | embed
    "title_only": False,            # True for title_only_types
    "title": "Decision: certificate rotation cadence",
    "url": "https://…/wiki/spaces/SDX/pages/1001",
    "space": "SDX",
    "labels": ["decision"],
    "version": 4,
    "updated": "2026-09-24",        # version.when[:10]
    "updated_by": "Dana",           # version.by.displayName, or ""
    "version_message": "",          # version.message; editors sometimes say what changed
    "created": "2026-09-23",        # history.createdDate[:10], or ""
    "is_new": True,                 # created inside the window
    "ancestor_ids": ["900", "950"],
    "ancestor_titles": ["SDX", "Decisions"],
    "body_text": "…",               # strip_html(body, limit=pages.summary_chars)
    "keys": ["APS-1", "APS-10"],    # Jira keys found in title + raw HTML body
    "kind": "decision",             # from labels first; else summary kind; else "other"
    "epic": "",                     # filled by map_to_epics
    "epic_match": "",               # link | mention | ancestor | model | ""
    "summary": "",                  # filled by page summaries (Step 5)
    "workstream": "SDX",
    "product": "IP",
    "watch": "2026-09-24",          # what state.compute_changes compares
    "ref": "",                      # D-tag, assigned per model section
    "detail": "…",                  # excerpt for the model, pages.excerpt_chars
}
```

Fetch expand: `body.view,version,space,history,metadata.labels,ancestors`.

### 4.6 Matching a page to an Epic

`core/pages.py::map_to_epics(pages, epics, parent_of, cfg)` fills `epic` and
`epic_match`, trying these in order and stopping at the first hit:

1. **link** — the page id is in the Confluence remote links of one of the
   Epics, or of a child whose Epic is known. Remote links come from
   `GET /rest/api/3/issue/{key}/remotelink`; keep entries whose
   `application.type` is `com.atlassian.confluence` or whose `object.url`
   starts with `confluence.base_url`; the page id is `pageId=(\d+)` or
   `/pages/(\d+)` in the URL. Remote links are fetched for Epics only (one
   call each, cached), not for every child.
2. **mention** — `page["keys"]` contains exactly one Epic key, or keys whose
   Epics (walk `parent_of`) resolve to exactly one Epic. Two or more
   different Epics: no match here (the page is cross-cutting; it falls
   through).
3. **ancestor** — a page in `ancestor_ids` was already matched in this run
   by rule 1 or 2. Inherit its Epic.
4. **model** — only when `pages.match_epics_with_model` is true and the page
   has a summary: ask the model to pick one Epic key from the candidate
   list (the workstream's Epics, or the product's for a product space), or
   none. The answer must be one of the listed keys; anything else is
   treated as none. Printed as "matched by the model".
5. Otherwise `epic` stays `""` and the page is listed under
   **Documentation changed** for its workstream.

### 4.7 Page summaries, and why they belong in `pm warm`

`core/page_summaries.py`:

- `summarise(cfg, page)` returns `{"summary": str, "kind": str}`.
- Store: one JSON file per page version at
  `<cache.path>/pages/<page_id>-<version>.json`, holding
  `{"summary", "kind", "model", "stored_at"}`. **No TTL**: a page version
  never changes. `--refresh` ignores and overwrites it. `--cached` uses it.
- Miss: call `model.call_model_json` with `PAGE_SUMMARY_PROMPT`
  (Appendix B). Take element `[0]`. Validate `kind` against the allowed list;
  anything else becomes `other`. Cut `summary` to 240 characters. A failed
  call stores nothing and returns `{"summary": "", "kind": ""}`.
- Title-only types are never summarised.
- At most `pages.max_summaries` (default 20) **new** summaries per run. The
  rest are listed by title with `(not summarised yet — run pm warm --pages)`.
  Stored summaries do not count against the cap.
- The model's Epic pick (4.6 rule 4) is stored in the same folder as
  `<page_id>-<version>-epic-<hash of candidate keys>.json`.

`pm warm --pages` computes the same window the next `pm report` will use and
summarises every changed page in it. Run overnight, the morning report only
pays for pages edited since.

### 4.8 SharePoint

Keep the current fetch, but route it through the same record shape
(`type: "file"`, `title_only: True`, no body, no summary) so it lands in
**Documentation changed** and **Sources** with a real title instead of
`SDX-S1`. Summarising SharePoint files is out of scope (Part 11).

---

## Part 5 — Audiences: pm, leadership, partner

### 5.1 What each audience is for

| Audience | Reader | Wants | Must not get |
|---|---|---|---|
| `pm` | The product manager and the Scrum Team | Everything: items, assignees, comments, risks, docs, metrics | — |
| `leadership` | Directors, heads of, portfolio reviews | Epic-level outcomes, what is at risk, decisions needed from them, headline delivery numbers | Ticket-level detail, individual names, comment quotes |
| `partner` | People outside the company | What is new and what is coming, by feature (Epic) name | Anything not explicitly marked shareable, names, risks, internal keys and links (by default), metrics |

### 5.2 Tagging who it is for

- New flag `--audience {pm,leadership,partner}` on `pm report`, `pm brief`,
  `pm release-notes`, `pm metrics`, and `pm warm` (warm accepts a
  comma-separated list). Default: `audiences.default` in config, else `pm`.
- `pm brief` keeps `--for "Monthly portfolio review"` as the meeting name and
  its per-meeting memory. `--audience` sets the level. The brief state file
  remembers the level (`_audience_level`), so the next `pm brief --for
  "Monthly portfolio review"` uses it without the flag.
- The tag appears in four places:
  1. The header line: `_Audience: Leadership · Window: … · Generated …_`.
  2. The H1 for non-pm audiences: `# Weekly State-of-Product Report — Leadership`.
     The pm H1 is unchanged, so an existing published page keeps updating in
     place.
  3. The file name: `weekly_report_leadership_2026-09-25.md`. The pm file
     name is unchanged. `output.file` may contain `{audience}`; when it does
     not and the audience is not pm, `_<audience>` is inserted before the
     extension.
  4. On publish, a Confluence label `pm-audience-<audience>` next to
     `pm-report`.
- `--json` on `pm report` writes the gathered data model (Step 6.6) with a
  top-level `"audience"` key. That also retires the dead flag from 1.5.

### 5.3 Memory per audience

`pm report` remembers when it last ran, and "since last report" is the
default window. If the pm run moved that memory, a leadership run five
minutes later would have a five-minute window and say nothing. So memory is
per audience:

- `pm`: `output.state_file` (unchanged, `report_state.json`).
- `leadership`, `partner`: `report_state_<audience>.json` next to it.

An explicit window (`--since`, `--sprint`) still moves no memory.

### 5.4 The partner allow-list

The partner report shows only what someone marked shareable. There is no
fallback to "everything".

- An Epic is partner-visible when it carries a label in
  `audiences.partner.epic_labels` (default `[partner-visible]`) or its
  workstream sets `partner_visible: true`.
- A child item under a visible Epic is shown only by title, and not at all
  when it carries a label in `audiences.partner.exclude_labels` (default
  `[internal]`).
- A page is partner-visible only when it carries a label in
  `audiences.partner.page_labels` (default `[partner-visible]`).
- Nothing is visible: the command exits 1 with
  `No Epic is marked for partners. Add the label partner-visible to an Epic, or set partner_visible: true on a workstream.`
- Jira and Confluence links are left out unless
  `include_jira_links` / `include_confluence_links` are true.
- Target dates are left out unless `show_target_dates` is true.
- **Redaction check** (`core/audience.py::redact`): after the model writes,
  every line containing a person's name seen anywhere in the gathered data
  (assignees, comment authors, page editors) or a Jira key that is not a
  visible Epic key (all keys when `include_jira_links` is false) is removed.
  The count is printed to the terminal only; the file does not say lines
  were removed.
- `pm report --audience partner --publish` exits with
  `Read a partner report before it leaves. Publish it with: pm publish <file>`.
  `pm schedule add report --audience partner` is refused the same way.

---

## Part 6 — Every report, per audience

| Command | `pm` | `leadership` | `partner` |
|---|---|---|---|
| `pm report` | Part 3.2 in full | 6.1 | 6.2 |
| `pm brief` | Today's prep, plus "Documents changed" with summaries, and risk pages by summary | Epic signals, decisions needed, docs of kind decision/risk | Prep for a partner meeting, scoped to visible Epics (for the PM's eyes) |
| `pm release-notes` | Grouped by product, workstream, **Epic**; keys; "Further reading" pages | Epic-level: which Epics shipped work, counts, model prose | Visible Epics only; done item titles; no keys by default; model prose |
| `pm metrics` | Unchanged | Headline table only | Not offered (exit 1 with a sentence) |
| `pm daily`, `pm today`, `pm triage`, `pm lint`, `pm ready`, `pm refine`, `pm review`, `pm coverage` | Unchanged | Not offered | Not offered |

The last row stays pm-only on purpose. Those commands are the Scrum Team's
working tools: they judge the Product Backlog as it stands or run the Daily
Scrum. A leadership version of `pm lint` would be a scorecard on the team,
which is not what a Product Backlog check is for. They get no `--audience`
flag, so there is nothing to misuse.

### 6.1 `pm report --audience leadership`

```markdown
# Weekly State-of-Product Report — Leadership
_Audience: Leadership · Window: since 2026-09-18 (last leadership report) · Generated 2026-09-25_

## Summary
### Headline
- Secure exchange platform is on track: 3 of 7 items done, due 30 Oct. [APS-1](…)
### Decisions needed
- Confirm the certificate rotation window with Security. [Decision: certificate rotation cadence](…)
### Risks to watch
- Public API foundations is at risk: rate limiting is blocked. [APS-2](…)

## Integration Platform (IP)
Product Goal: <product_goal>

| Epic | Workstream | Status | Progress | Signal | Target |
|------|------------|--------|---------:|--------|--------|
| [APS-1](…) Secure exchange platform | SDX | In Progress | 3 / 7 | On track | 30 Oct |
| [APS-2](…) Public API foundations | APS | In Progress | 1 / 4 | At risk — 1 blocked | — |

Documents: 
- [Decision: certificate rotation cadence](…) — decision. Certificates rotate every 90 days, automated from October.

## Delivery
<metrics headline table>

_Signal is a rule, not a judgement: …_
```

- One model call per **product** (`LEADERSHIP_PROMPT`, Appendix B). Its
  facts are: the Epic table rows as text; decision, risk and dependency
  pages with their summaries; and the "Decisions we are waiting on",
  "Open dependencies" and "Risks" sections from each workstream's pm model
  section. That means a leadership run also needs the pm sections — they
  come from the model cache when `pm warm --report` ran, and are computed
  otherwise (the call count says so).
- Documents: only kind `decision`, `risk`, `dependency`, or `is_new`, at
  most `audiences.leadership.max_docs_per_product` (default 5), newest first.
- No ticket rows, no assignees, no comment quotes, no Sources appendix of
  items. A short Sources list of Epics and documents stays.
- Portfolio-wide "Summary" is the product summaries concatenated when there
  is one product; with several products, each product's three headings sit
  under its own product heading and "Summary" is omitted.

### 6.2 `pm report --audience partner`

```markdown
# Weekly State-of-Product Report — Partners
_Audience: Partners · Window: since 2026-09-01 · Generated 2026-09-25_

## Integration Platform

### What's new
- Secure exchange platform: the status endpoint is in review.
### Coming next
- Public API foundations is in progress.

| Feature | Status | Progress |
|---------|--------|---------:|
| Secure exchange platform | In progress | 43% |
| Public API foundations | Planned | 0% |

Further reading:
- Partner guide: connecting to the exchange
```

- One model call per product (`PARTNER_PROMPT`), fed only visible Epics
  (name, status phrase, progress percent, done child titles in the window,
  optional target date) and visible pages (title, summary).
- Status phrase mapping: category `new` → "Planned", `indeterminate` → "In
  progress", `done` → "Delivered".
- Product name is printed; workstream names are not (they are often
  internal team names).
- No metrics, no Definition of Done, no signal words, no risks.
- The redaction check runs on the whole file before it is written.

### 6.3 `pm brief --audience …`

The brief is prep for the PM to read before a meeting. The level decides
what the PM is prepared to talk about, not who reads the file.

- `pm` (default): today's sections, plus **Documents changed** (pages in the
  window since that meeting last met, max 5 per product, with summaries).
  The risk list uses the page summary instead of the 200-character excerpt.
- `leadership`: per product, the Epic table from 6.1 (no model), then
  "Decisions you need from the room" = pages of kind `decision` changed in
  the window plus Epics signalled At risk, then "What you owe the room" =
  counts of overdue and blocked items per Epic (not the item list).
- `partner`: header `_Prep for a partner meeting — internal, do not forward._`
  Only visible Epics and their children; the overdue and blocked items
  inside those Epics are listed, because the PM needs to know before the
  partner asks.

The brief stays deterministic apart from page summaries, which come from
the page store.

### 6.4 `pm release-notes --audience …`

- All levels: `bullet_lines` groups by product → workstream → **Epic**
  (use the item's resolved Epic from `core/epics.py`; items with none go
  under "Not under an Epic").
- `pm`: as today plus a "Further reading" list per Epic: pages matched to
  that Epic that changed inside the window.
- `leadership`: per product, one line per Epic with done work:
  `[APS-1](…) Secure exchange platform — 4 done this window (5 of 7 total)`,
  then the model prose (existing `PROMPT`, fed Epic lines instead of item
  lines). No item bullets.
- `partner`: visible Epics only. Under each, the done child titles minus
  `exclude_labels`, no keys unless `include_jira_links`. Model prose with
  `PARTNER_PROMPT`'s rules 2–4 appended to `PROMPT`. Redaction check.

### 6.5 `pm metrics --audience …`

- `pm`: unchanged.
- `leadership`: `commands/metrics.py::render_headline(groups, weeks)`: one
  table per product with columns Workstream, Done / week, Cycle (median),
  Open, Landing. No aging list, no forecast points, no weekly throughput
  table. The same function renders the leadership report's "Delivery"
  section.
- `partner`: exit 1 with `pm metrics has no partner view.`

---

## Part 7 — What the model is asked, and what it costs

| Call | When | Count per run | Cache |
|---|---|---|---|
| Page summary | Each changed page without a stored summary | ≤ `pages.max_summaries` (20) | Page store, no TTL, keyed page id + version |
| Page → Epic | Unmatched page with a summary, when enabled | ≤ pages left after rules 1–3 | Page store, keyed page id + version + candidate hash |
| pm section | Per workstream (unchanged) | workstreams | Model cache (7 days) |
| Leadership summary | Per product | products | Model cache |
| Partner summary | Per product with a visible Epic | products | Model cache |
| Release notes prose | Per run (unchanged) | 1 | Model cache |

For the shipped config (1 product, 3 workstreams, say 12 changed pages a
week): a cold pm report is 12 + ≤12 + 3 = up to 27 calls; after an
overnight `pm warm` it is only what changed since. Leadership adds 1 call on
top of the pm sections. `model.announce` must be given the real total so
the estimate line stays honest.

---

## Part 8 — Implementation steps, in order

Each step is one commit, leaves `python3 -m unittest discover -s tests`
green, and adds the tests listed. Do them in order: later steps use the data
shapes earlier steps create.

### Step 1 — Make the window drive the fetch (bug fix, no new behaviour)

**Files:** `commands/report.py`, `commands/brief.py`, `core/window.py`,
`core/sources.py`, `commands/warm.py`.

1. In `core/window.py::resolve`, also return `"sprint_id"` (the chosen
   Sprint's id or `None`).
2. In `commands/report.py::run`, resolve the window **before** the gather
   loop (move the existing block up). Pass it to `prepare(cfg, ws, previous,
   window)`.
3. In `prepare`:
   - `prev_snapshot = previous.get(prefix, {})` (already there).
   - `cutoff`: when `window["explicit"]`, the window start as an aware UTC
     datetime at midnight; otherwise `comments.report_cutoff(prev_snapshot,
     comments.settings(cfg))`. Use this one value for comments, pages, and
     the Confluence query. Delete the broken `previous.get("_ran_at")` line.
   - When `window["sprint_id"]` is set, call `workstreams.scope_jql(cfg, ws,
     "report", overrides={"sprint": window["sprint_id"]})`.
4. `sources.fetch_confluence(cfg, cql, tag_prefix, start_index, since=None)`:
   new keyword `since` (a `date`). When given, the CQL uses it instead of
   `lookback_days`.
5. `commands/brief.py::gather(cfg, audience, window)`: same cutoff logic,
   with `last` as the default. `_risks` passes `since`.
6. `commands/warm.py::_warm_report` builds a non-explicit window the same
   way so warmed prompts match the next report.

**Tests** (`tests/test_reporting_window.py`, new):
- `pm report -w SDX --since 2026-06-01` sends a Confluence CQL containing
  `lastmodified >= '2026-06-01'` (read `self.jira.calls`).
- Two report runs: the second run's page cutoff is the first run's
  `_ran_at`, not `None` (unit test on `prepare` with a hand-made
  `previous`).
- `pm report --sprint 10` puts `sprint = 10` in the report-scope JQL.
- `pm brief --for X --since 2026-06-01` changes the brief's CQL date.

**Done when** all four pass and the existing report tests still pass.

### Step 2 — Real keys as citations

**Files:** `core/sources.py`, `core/state.py`, `core/model.py`,
`commands/report.py`, new `core/citations.py`, `tests/test_model.py`,
`tests/test_comments.py`.

1. `sources.fetch_jira`: set `ref=iss["key"]`. Keep the `(items,
   next_index)` return shape so callers do not change; the index is now
   unused. Add keys to the item: `"key"`, `"summary"` (raw summary),
   `"status"`, `"status_category"` (statusCategory key), `"assignee"`,
   `"issuetype"`, `"labels"`, `"due"`.
2. `sources.fetch_confluence` and `fetch_sharepoint`: set `ref=""`. Tags are
   assigned later, per section.
3. Every item gets `"workstream": ws["abbrev"]` in `report.prepare` (and in
   `brief.gather`).
4. New `core/citations.py`:

   ```python
   TAG = re.compile(r"\[([A-Z][A-Z0-9]+-\d+|D\d+)(?:\s*,\s*([A-Z][A-Z0-9]+-\d+|D\d+))*\]")

   def assign_doc_tags(docs):
       """Give each doc a D-tag, numbered by page id ascending. Returns the docs."""

   def citation_map(items):
       """{tag: (label, url)}. Jira: (key, url). Docs: (title cut to 60, url)."""

   def resolve(text, cmap):
       """Return (new_text, removed_count). Rewrite bracketed tags to links;
       drop tags not in cmap. Handles comma lists inside one bracket."""
   ```

   Parse a bracket by taking its inner text, splitting on commas, and
   resolving each part; do not rely on the regex's repeated groups (Python
   keeps only the last).
5. `core/model.py`: in `REPORT_SYSTEM_PROMPT`, rule 3 becomes `After a fact,
   cite its tag like [APS-10] or [D1]. Use only tags that appear in the
   Material.` The example bullets cite `[APS-10]` and `[D1]`.
6. `commands/report.py::run`: after each `infer_report_section`, call
   `citations.resolve(body, citation_map(row["items"]))`; when `removed > 0`
   print `  (SDX: 1 citation removed — not in the material)` and append the
   italic line from 3.1 to the section.
7. `core/state.py::build_change_block`: for dropped items, cite the uid when
   it looks like a Jira key (`^[A-Z][A-Z0-9]+-\d+$`), otherwise no tag.
   Ignore any `ref` stored by an older state file.
8. `commands/report.py::build_report`: count per workstream with
   `it["workstream"]`, not the ref prefix. Keep the old References table for
   now (Step 6 replaces it), but its first column is the key.

**Tests:**
- `citations.resolve` unit tests: single key, doc tag, comma list, unknown
  tag removed and counted, a key-looking word in prose without brackets is
  left alone.
- An older state file whose snapshot has `"ref": "SDX-J1"` produces a change
  block with no `SDX-J1` in it.
- End-to-end: the report contains `[APS-10](` and no `SDX-J`.
- Update `tests/test_model.py` and `tests/test_comments.py` fixtures that use
  `SDX-J1` refs to use keys.

### Step 3 — The Epic layer

**Files:** new `core/epics.py`, `core/sources.py`, `commands/report.py`,
new `tests/test_epics.py`.

1. `sources.fetch_jira`: always add `parent` (and `jira.epic_link_field`
   when it is not `parent`) to the requested fields, **even when
   `jira.fields` is set in config** — user configs list fields without
   `parent`. Store `item["parent"]` as the parent key or `None`.
2. New `sources.fetch_issues_by_key(cfg, keys, fields)`: `key IN (…)` in
   chunks of 100, returns raw issues. Used to walk up to missing parents.
3. New `core/epics.py`:

   ```python
   def parent_map(cfg, items, epic_types, max_depth=3):
       """{key: parent_key} for items and their ancestors. Fetches missing
       parents with fetch_issues_by_key, at most max_depth rounds.
       Also returns {key: raw_issue_fields} for fetched ancestors."""

   def epic_of(key, parents, types_by_key, epic_types):
       """Walk up until an issue whose type is in epic_types. None if none."""

   def assign(items, parents, types_by_key, epic_types):
       """Set item['epic'] on every Jira item (None when not under an Epic)."""

   def child_counts(cfg, epic_keys, blocked_cfg):
       """One `parent IN (...)` query (chunks of 100), max_items=0.
       {epic_key: {"total", "done", "in_progress", "blocked"}}."""

   def signal(epic, counts, window_start, today, at_risk_due_days, updated_in_window):
       """(word, reason) per the rule in Part 3.3."""

   def build(cfg, ws, items, window, prev_changes):
       """[epic dict, …] in display order: At risk, then by key.
       Each epic dict has the fields in Part 3.3 plus
       'items' (in-window items under it), 'moved', 'pages' (filled in Step 4).
       Adds a pseudo-epic {'key': None, 'summary': 'Not under an Epic'} last
       when any item has no Epic."""
   ```

4. Which Epics appear for a workstream: (a) the `roadmap` scope Epics
   already fetched; (b) every Epic reached from an in-window item; (c) the
   workstream's Epics resolved inside the window — `workstreams.membership_jql(cfg,
   ws, "epics")` plus `AND statusCategory = Done AND resolved >= "<window
   start>"`. The fake Jira reads `resolved` from the issue dict, so give a
   done fixture Epic a `resolved` stamp when a test needs (c). Mark (b)
   Epics not in `workstreams.get_epic_keys` as
   `in_scope: False` and name the workstream that owns them if any.
5. `report.prepare` returns `row["epics"] = epics.build(...)`. Nothing is
   rendered yet.

**Tests** (`tests/test_epics.py`, using the end-to-end backlog):
- APS-12 (Sub-task under APS-10 under APS-1) resolves to APS-1.
- APS-31 (Sub-task under APS-30 under APS-3) resolves to APS-3, and APS-3 is
  `in_scope: False` for SDX.
- APS-50 (under SDX's Epic, carries API Platform) resolves to APS-1 in SDX
  and to APS-1 (out of scope) in APS.
- `child_counts` counts direct children only.
- Each signal branch with a hand-built epic dict, including the order
  (Done beats At risk).
- A config whose `jira.fields` omits `parent` still gets `parent` requested.

### Step 4 — Confluence reader, version 2

**Files:** `core/sources.py`, `core/pages.py`, `core/filters.py`,
`commands/report.py`, `tests/fake_jira.py`, new `tests/test_pages_v2.py`.

1. `sources.strip_html(html, limit=400)`: keep the default for other
   callers; `fetch_confluence` passes `limit=pages.summary_chars`.
2. `filters.build_cql(ws, scope="space", types=None)`: `space = X`, plus
   `label IN (…)` only when `scope == "labelled"`, plus `type IN (…)` when
   `types` is given. A hand-written `confluence_cql` still wins.
3. `sources.fetch_confluence(cfg, cql, since=None, limit=None)` → list of raw
   results. Expand as in 4.5. Add `order by lastmodified desc`. Route through
   `pages.cache_fetch(cfg, "confluence", (cql, since, limit), fetch)`.
   Keep a thin wrapper with the old signature for `brief._risks` until Step 10.
4. `sources.fetch_confluence_page(cfg, page_id)` and
   `sources.fetch_remote_links(jira_cfg, key)` (both cached with
   `pages.cache_fetch`).
5. `core/pages.py`:
   - `normalise(raw, base_url, ws, product, projects, window_start, opts)` →
     the dict in 4.5. `kind` from the first label that matches the
     workstream's `confluence_labels` (lower-cased), else `""` (Step 5 fills
     it). `keys` from `re.findall` over title + raw HTML, restricted to the
     configured project keys.
   - `excluded(page, cfg)` per 4.4.
   - `gather(cfg, ws, product, epics, window)` → list of page dicts: space
     query, plus linked pages from `fetch_remote_links` for each in-scope
     Epic when `follow_jira_links`, de-duplicated by `page_id`, excluded pages
     dropped, capped at `pages.max_pages` newest first.
   - `map_to_epics(pages, epics, parent_of, cfg)` per 4.6 rules 1–3 (rule 4
     arrives in Step 5).
   - `apply_excerpt` keeps working on the new dicts: `detail` =
     `excerpt(body_text, excerpt_chars)`.
6. `report.prepare`: replace the old Confluence block with
   `pages.gather(...)` and `pages.map_to_epics(...)`; attach each page to its
   Epic's `pages` list; the rest go to `row["loose_pages"]`.
7. Product spaces: when a product has `confluence_space`, gather it once per
   product (not per workstream), map against the product's Epics, and attach
   each page to the workstream that owns the matched Epic; unmatched ones go
   under the product.

**Fake Jira changes** (`tests/fake_jira.py`):
- Page fixtures gain `type` (default `page`), `version` (int), `by`,
  `created`, `ancestors` (list of `{id, title}`), `message`.
- `_confluence()` honours `space = …`, `label IN (…)`, `type IN (…)` and
  `lastmodified >= 'YYYY-MM-DD'` (compare against `when[:10]`). Parse each
  clause with its own regex; today's parser takes every quoted word after
  the first `label`, which would also swallow the `type IN` values. It
  returns `type`, `version.number`,
  `version.when`, `version.by.displayName`, `version.message`,
  `history.createdDate`, `metadata.labels.results`, `ancestors`.
- New route `GET /wiki/rest/api/content/<id>` returning one page.
- New route `GET /rest/api/3/issue/<KEY>/remotelink` from an issue's
  `remote_links` list in the backlog fixture.

**New fixture pages** (add to `pages()` in `tests/test_cli_end_to_end.py`):
unlabelled SDX page mentioning `APS-10` in its body; SDX blog post; SDX
database; SDX whiteboard (must not appear); APS page linked from APS-2 by a
remote link; page under `Weekly Reports` in space APS (must not appear);
page in SDX edited 30 days ago (must not appear on a first run).

**Tests:** each fixture page lands where 4.6 says; types filter; the 400
character cut is gone (a 3,000-character body keeps its last sentence in
`body_text`); a second run inside the fetch TTL makes no new Confluence call.

### Step 5 — Page summaries and `pm warm --pages`

**Files:** new `core/page_summaries.py`, `core/model.py` (prompts),
`core/pages.py`, `commands/warm.py`, `pm.py`, `tests/fake_jira.py`, new
`tests/test_page_summaries.py`.

1. Add `PAGE_SUMMARY_PROMPT`, `PAGE_EPIC_PROMPT` and `PAGE_KINDS` to
   `core/model.py` (Appendix B).
2. `core/page_summaries.py` per 4.7: `store_path(cfg)`, `load(cfg, page)`,
   `save(cfg, page, record)`, `summarise(cfg, page)`, `pick_epic(cfg, page,
   candidates)`, and `fill(cfg, pages, budget)` which summarises in newest
   first order and returns how many model calls it made.
3. `pages.map_to_epics` gains rule 4, calling `pick_epic` when enabled.
4. `page["kind"]` = label kind if set, else summary kind, else `"other"`;
   blog posts with kind `other` become `"update"`.
5. `pm warm --pages`: new flag. No-flag warm runs review, **pages**, report,
   inbox, in that order (pages before report, because the report material
   contains the summaries).
6. The fake model answers `Summarise one Confluence page` with
   `[{"summary": "<first sentence of the page text>", "kind": "decision"}]`
   and `Match one Confluence page` with the first key listed.

**Tests:** a second summarise of the same page version makes no model call;
a new version does; `--refresh` does; a bad `kind` becomes `other`; the cap
lists the rest as not summarised; `pm warm --pages` then `pm report` makes
no page-summary calls; a model Epic pick outside the candidate list is
ignored.

### Step 6 — The PM report layout

**Files:** `core/model.py`, `commands/report.py`, new `core/report_render.py`,
`commands/publish.py`, tests.

1. `model.build_grouped_material(epics, loose_pages, comment_budget,
   page_budget, max_items=40, max_per_epic=8)`: the text block in Appendix B
   (Material format). Per Epic, children are chosen in this order until
   `max_per_epic`: moved, new, commented, blocked, in progress, the rest;
   then `(+N more under this Epic)`. Page excerpts share
   `pages.section_chars` (this finally uses that key); a page that does not
   fit is listed by title with its summary only.
2. `model.infer_report_section` takes the grouped material. Signature:
   `infer_report_section(model_cfg, audience_text, workstream, material,
   change_block)`. Update `warm.py` to match.
3. After resolving citations, make the model headings one level deeper
   than the workstream heading. When products are shown the workstream is
   `###`, so `### What changed…` becomes `#### What changed…`. When
   products are not shown the workstream is `##` and the model's `###` is
   already one level below; leave it. Implement as
   `report_render.demote(text, levels)` that prefixes `levels` extra `#`
   to every line starting with `#`.
4. `core/report_render.py`:
   - `at_a_glance(groups, rows)` → table in 3.2.
   - `epic_block(epic, links=True)` → the bold line and bullets in 3.2.
   - `docs_block(pages)` → "Documentation changed".
   - `sources_appendix(groups, rows, level)` → the grouped tables.
   - `render_pm(cfg, groups, rows, sections, window, scope_note)` → the whole
     file. Move `_increment_lines` here unchanged.
5. `commands/publish.py::markdown_to_storage`: add `####`/`#####` headings,
   `**bold**` inside `_inline` (escape first, then turn `**x**` into
   `<strong>x</strong>`), and keep bullets flat (the layout above uses no
   nested bullets — keep it that way).
6. `pm report --json`: write `weekly_report_<date>.json` with
   `{"audience", "window", "products": [{"abbrev", "workstreams": [{"abbrev",
   "epics": [...], "pages": [...], "section": "<markdown>"}]}]}`. Use
   `json.dump(..., default=str)`.

**Tests:** end-to-end report contains `## At a glance`, `#### Epics`,
`**[APS-1](`, `Not under an Epic` only when needed, `## Sources`, no
`## References`; model headings are `####` under a product; publish
converts `####` and `**bold**`; `--json` writes a file whose epics include
APS-1 with `children_total`.

### Step 7 — Audience plumbing

**Files:** new `core/audience.py`, `pm.py`, `core/config.py`,
`commands/report.py`, `commands/publish.py`, `commands/schedule.py`.

1. `core/audience.py`:

   ```python
   LEVELS = ("pm", "leadership", "partner")
   DEFAULTS = {...}            # Part 9, audiences block
   def settings(cfg): ...      # merged block, like pages.settings
   def level(cfg, args): ...   # --audience, else audiences.default, else "pm"; validate
   def display_name(cfg, level): ...
   def state_path(cfg, level, args): ...      # Part 5.3
   def output_name(cfg, level, date): ...     # Part 5.2 point 3
   def partner_visible_epic(epic, ws, opts): ...
   def partner_visible_page(page, opts): ...
   def redact(text, names, allowed_keys, drop_all_keys): ...  # returns (text, removed)
   ```
2. `pm.py`: `--audience` with `choices=LEVELS` on report, brief,
   release-notes, metrics; on warm, a comma-separated string validated
   against `LEVELS`.
3. `core/config.py`: validate the `audiences:` block (mapping; `default` in
   `LEVELS`; label lists are lists of strings; booleans are booleans).
4. `commands/report.py`: header line, H1 suffix, file name, state path per
   level. `pm` keeps today's names.
5. `commands/publish.py::publish_file(cfg, args, path, title=None,
   labels=None)`: include `metadata.labels` on create
   (`[{"prefix": "global", "name": n} for n in labels]`) and, after an update,
   `POST /rest/api/content/{id}/label` with the same list. `pm report`
   passes `["pm-report", f"pm-audience-{level}"]`; `pm brief` passes
   `["pm-report", "pm-brief"]`.
6. Partner guard on `--publish` and in `schedule.add` (Part 5.4).
7. Fake server: accept `metadata.labels` on `POST /wiki/rest/api/content`
   (store them on the page) and add `POST /wiki/rest/api/content/<id>/label`.

**Tests:** default level is pm and nothing about the pm file name, H1 or
state file changes; `--audience leadership` writes
`weekly_report_leadership_<date>.md` and `report_state_leadership.json`, and
leaves `report_state.json` untouched; an invalid `audiences.default` fails
at load; publishing adds the labels (inspect the fake's POST body); partner
publish and partner schedule are refused.

### Step 8 — Leadership report

**Files:** `core/model.py`, `commands/report.py`, `core/report_render.py`,
`commands/metrics.py`.

1. `LEADERSHIP_PROMPT` (Appendix B). `model.infer_leadership(model_cfg,
   product, facts)`.
2. `report_render.extract_sections(markdown, names)` returns the body under
   the named `####`/`###` headings from a pm section.
3. `commands/report.py::run_leadership`: gather exactly as pm (Steps 1–5),
   compute pm sections (cache hits after warm), then per product build the
   facts text (Appendix B, Leadership facts) and call the model; resolve
   citations with a map of Epic keys and page D-tags only (child keys are
   not in the map, so the model cannot cite a ticket).
4. `report_render.render_leadership(...)` per 6.1.
5. `commands/metrics.py::render_headline(groups, weeks)` per 6.5.
6. Call `model.announce` with `workstreams + products` (the pm sections
   plus one leadership call per product). Whether a pm section is already
   cached is not known in advance; the cache hits show in the counts
   `pm warm` already prints, and `pm report` should print the same
   `N model call(s), M already cached` line at the end.

**Tests:** leadership file has the three headings, an Epic table with a
Signal column, no assignee names from the fixture (`A. Lee`, `B. Ray`), no
child keys (`APS-10`), and the Delivery table without "Aging in"; the fake
model's reply citing `[APS-10]` has that citation removed.

### Step 9 — Partner report

**Files:** `core/model.py`, `commands/report.py`, `core/report_render.py`,
`core/audience.py`.

1. `PARTNER_PROMPT` (Appendix B). `model.infer_partner(model_cfg, product,
   facts)`.
2. `commands/report.py::run_partner`: gather; filter Epics with
   `partner_visible_epic`, children with `exclude_labels`, pages with
   `partner_visible_page`; exit 1 with the Part 5.4 sentence when no Epic is
   visible; one model call per product with a visible Epic; render per 6.2;
   run `redact` over the whole file with every person name seen during the
   gather and the allowed keys.
3. Links: Epic names are plain text unless `include_jira_links`; page titles
   are plain text unless `include_confluence_links`.

**Tests:** with no labels the command exits 1 with the sentence; with
`partner-visible` on APS-1 only APS-1's name appears, APS-2's does not; a
child labelled `internal` is absent; no person names; no Jira keys; no
`http` links by default; a fake model reply that includes `A. Lee` has that
line removed and the terminal says `1 line removed`.

### Step 10 — Brief levels and documents

**Files:** `commands/brief.py`, `core/report_render.py`.

1. `gather` uses `pages.gather` + summaries for the window since that
   meeting last met, and `epics.build` per workstream.
2. `render_prep(audience, sections, last, level)` branches per 6.3.
3. `_risks` becomes "pages of kind risk", read from the gathered pages, so
   the separate risk fetch goes away. Risk lines use `summary` when present,
   else today's 200-character excerpt.
4. The state file stores `_audience_level`; `--audience` overrides it and
   is saved.

**Tests:** pm brief has "Documents changed" with the fixture decision page
and its summary; leadership brief has the Epic table and no item keys under
"What you owe the room"; partner brief has the internal header and only
visible Epics; a second brief without `--audience` reuses the saved level.

### Step 11 — Release notes by Epic and level

**Files:** `commands/release_notes.py`.

1. `collect` also returns each row's Epic (use `core/epics.py` with the
   `parent` field `fetch_jira_detailed` already returns in `"epic"` — note
   that for a Sub-task this is its parent Story, so walk up with
   `epics.parent_map`).
2. `bullet_lines` groups by Epic inside each workstream.
3. Level branches per 6.4; "Further reading" uses `pages.gather` for the
   `--since` window (skip when only `--version` is given and say so).

**Tests:** pm notes show an Epic line above its done items; leadership shows
Epic lines only; partner shows only visible Epics and no keys.

### Step 12 — Metrics levels

**Files:** `commands/metrics.py`.

`run` reads the level; `leadership` renders `render_headline`; `partner`
exits 1. JSON output is unchanged for pm and adds `"audience"`.

**Tests:** leadership output has no "Aging in" and no "Forecast pts";
partner exits 1 with the sentence.

### Step 13 — Warm per level

**Files:** `commands/warm.py`, `pm.py`.

1. `pm warm --report --audience pm,leadership`: warms pm sections for every
   selected workstream, then the leadership product summaries. Partner
   warming is allowed (it is read-only) and warms the partner product calls.
2. Default levels when `--audience` is not given:
   `audiences.warm` (default `[pm]`).
3. `_warm_report` reuses the exact gather and material builders the report
   uses. **Do not rebuild the material separately in warm**; any difference
   in the text means a cache miss.

**Tests:** `pm warm --audience pm,leadership` then `pm report --audience
leadership` makes zero model calls (count POSTs to `/v1/chat/completions`
in the fake).

### Step 14 — Config, migration, doctor, docs, release

**Files:** `config.yaml`, `core/migrations.py`, `commands/doctor.py`,
`README.md`, `docs/EVERYDAY.md`, `docs/DEPTH.md`, `docs/AUTOMATION.md`,
`CHANGELOG.md`, `pyproject.toml`, `tests/test_update.py`.

1. Template: the blocks in Part 9, with comments in the file's existing
   style. `config_version: 6`.
2. `migrations.to_version_6` (Part 9.3). Append `(5, to_version_6)`.
3. `pm doctor`: a Confluence line per workstream — the space exists, the
   content types are accepted, and how many pages changed in the last 7
   days. Warn when a workstream has no `confluence_space`.
4. README: rewrite the `pm report` section around the new layout and the
   three levels; add `--audience` to `pm brief`, `pm release-notes`,
   `pm metrics`, `pm warm`. `docs/AUTOMATION.md`: the warm order and
   `pm schedule add warm --at 06:30` before `pm schedule add report`.
5. CHANGELOG `0.12.0`, pyproject `version = "0.12.0"`.

**Tests:** migration from a version 5 file inserts `audiences:` and the new
`pages` and `confluence` keys, leaves set values alone, and is idempotent;
the test config in `tests/test_cli_end_to_end.py` moves to version 6.

---

## Part 9 — Config and migration (`config_version` 6)

### 9.1 New and changed keys

```yaml
pages:
  enabled: true
  scope: space              # space: every changed page; labelled: only confluence_labels
  follow_jira_links: true   # pages an Epic links to, from any space
  max_pages: 20
  excerpt_chars: 2000
  section_chars: 8000
  summaries: true           # one cached sentence per page version
  summary_chars: 6000       # page text the summary sees
  max_summaries: 20         # new summaries per run; the rest are listed by title
  match_epics_with_model: true

confluence:
  # existing keys unchanged
  content_types: [page, blogpost]
  title_only_types: [database, embed]

audiences:
  default: pm               # pm | leadership | partner
  warm: [pm]                # what `pm warm --report` warms with no --audience
  pm:
    name: "Product management"
  leadership:
    name: "Leadership"
    at_risk_due_days: 14
    max_docs_per_product: 5
  partner:
    name: "Partners"
    epic_labels: [partner-visible]
    page_labels: [partner-visible]
    exclude_labels: [internal]
    include_jira_links: false
    include_confluence_links: false
    show_target_dates: false
```

Per product, optional: `confluence_space: "IPX"`.
Per workstream, optional: `partner_visible: true`.

`output.audience` stays and keeps meaning the words in the pm prompt
("stakeholders"). The header uses `audiences.pm.name`.

### 9.2 Defaults in code

Every key above has its default in the module that reads it
(`core/pages.py::DEFAULTS`, `core/audience.py::DEFAULTS`,
`sources.CONFLUENCE_DEFAULTS`), so a version 5 config runs without the
migration. Do not add them to `core/config.py::SECTION_DEFAULTS`; that dict
fills whole sections and `audiences` has nested blocks.

### 9.3 `to_version_6`

Follow `to_version_5`:

- Insert the `audiences` block before `output` when absent.
- Insert each missing `pages` key (`scope`, `follow_jira_links`,
  `summaries`, `summary_chars`, `max_summaries`, `match_epics_with_model`)
  under `pages`, keeping existing values.
- Insert `content_types` and `title_only_types` under `confluence` when the
  block exists and the keys are missing.
- `set_version(text, 6)`.

Note for the CHANGELOG: `scope: space` widens what the report reads for an
existing user. Say so, and say how to keep the old behaviour
(`pages.scope: labelled`).

---

## Part 10 — Tests and fixtures

Run: `python3 -m unittest discover -s tests` (the CI command in
`.github/workflows/tests.yml`). Baseline before this tranche: 315 tests, OK.

New test files: `test_reporting_window.py`, `test_epics.py`,
`test_pages_v2.py`, `test_page_summaries.py`, `test_audience.py` (level,
file names, state paths, redaction, partner visibility), plus new classes in
`test_cli_end_to_end.py` for leadership, partner, brief levels and release
notes levels.

Fixture additions, in one place so every step shares them:

- Backlog: label `partner-visible` on APS-1; label `internal` on APS-12;
  `remote_links` on APS-2 pointing at page 2002; a `duedate` on APS-1
  (30 days out) and APS-2 (5 days out); APS-20 labelled `blocked` so APS-2
  signals At risk.
- Pages: the list in Step 4, plus one `partner-visible` page in SDX.
- Fake model: branches keyed on the first words of each new system prompt
  (Appendix B). The leadership branch returns the three headings and one
  bullet citing `[APS-10]` (to prove the removal). The partner branch
  returns one bullet containing `A. Lee` (to prove redaction).

Every end-to-end assertion reads the written file, and the model-call
assertions count `POST /v1/chat/completions` in `self.jira.calls`, the way
`ReportTests` already does.

---

## Part 11 — Not in this plan, and choices worth revisiting

Not in this plan:

- Whiteboards, folders, attachments, and Confluence page comments. The
  record shape and `title_only_types` leave room for them.
- Summarising SharePoint files (needs a file text extractor).
- A partner report per partner (a partner name and its own allow-list
  label). The label list design allows it later: `partners: {acme:
  {epic_labels: [acme]}}`.
- A leadership view of `pm daily`, `pm lint` or `pm ready` (Part 6 says
  why).
- The v2 Confluence REST API. The v1 search still works; the record shape
  isolates the switch.

Choices made here that the user may want to change:

- `pages.scope: space` as the new default (wider than today).
- Leadership built on top of the pm sections rather than straight from the
  material (fewer hallucination paths, one extra dependency).
- Partner links off by default.
- The At risk thresholds (14 days, half done).
- Epics ordered At risk first, then by key.

---

## Appendix A — Pitfalls for the implementer

1. `jira.fields` in a user's config overrides `DEFAULT_REPORT_FIELDS` and
   does not list `parent`. Always append `parent` in code (Step 3.1).
2. Counting by `ref` prefix breaks once refs are keys. Count by
   `item["workstream"]` (Step 2.8).
3. `window.resolve` must run before the gather, or `--since` stays a no-op
   (Step 1).
4. `_ran_at` is per workstream in the state file, not top level (Step 1).
5. `strip_html` truncates to 400 characters by default. Pass a limit for
   Confluence (Step 4.1).
6. `call_model_json` returns a list. A single object comes back wrapped;
   take `[0]`.
7. Python's `re` keeps only the last repetition of a group. Resolve comma
   lists inside a bracket by splitting the inner text (Step 2.4).
8. `markdown_to_storage` does not know `####` or `**bold**` until Step 6.5.
   Do not use nested bullets anywhere.
9. Warm must build byte-identical prompts, or the cache never hits. Call the
   same functions the report calls (Step 13.3).
10. Leadership and partner memory must not move pm memory (Part 5.3).
11. The same issue can belong to two workstreams. Show it under both; do not
    de-duplicate across workstreams in the Epic blocks or Sources.
12. The pm H1 and pm file name must not change, or existing published pages
    and tests (`weekly_report_.*\.md`) break.
13. The model cache key includes the whole prompt. Adding the window label or
    today's date to the material would miss the cache every day. Keep dates
    out of the material except the facts themselves.
14. Do not import `commands.*` from `core.*` (the existing layering). Rendering
    helpers go in `core/report_render.py`; the leadership and partner
    runners stay in `commands/report.py`.

## Appendix B — Exact prompts

Keep the style of `core/model.py`: short, numbered, format last, one
example. Each prompt below is a module-level constant in `core/model.py`.

### `REPORT_SYSTEM_PROMPT` (changed lines only)

```
3. After a fact, cite its tag like [APS-10] or [D1]. Use only tags that \
appear in the Material.
6. Items are grouped under their Epic. Name the Epic when it helps the \
reader. A "Summary:" line under a document is a summary of that page; \
cite the document's tag.

Example of one filled section:
### Progress this sprint
- Status endpoint is in review. [APS-10]
- Certificate rotation cadence is decided. [D1]
```

### Material format (built by `build_grouped_material`)

```
Epic APS-1: Secure exchange platform | In Progress | 3 of 7 done | due 2026-10-30 | On track
  [APS-10] (Story) Publish exchange status endpoint | Status: In Review | Assignee: A. Lee
      2026-09-25 A. Lee: Waiting on the certificate review.
  [APS-11] (Task) Fix stuff | Status: In Progress | Assignee: B. Ray
  [D1] (Confluence decision, updated 2026-09-24) Decision: certificate rotation cadence
      Summary: Certificates rotate every 90 days, automated from October.
      Rotate every 90 days, automated from October. (excerpt)
Not under an Epic
  [APS-50] (Story) Expose exchange metrics on the API gateway | Status: In Progress
Documents not tied to an Epic
  [D2] (Confluence page, updated 2026-09-23) SDX runbook index
      Summary: Lists the runbooks for certificate rotation and key escrow.
```

### `PAGE_SUMMARY_PROMPT`

```
Summarise one Confluence page for a product report.

Use ONLY the page text. Do not invent decisions, dates, or people.

Return a JSON array with exactly one object and nothing else:
[{"summary": "...", "kind": "..."}]

Rules:
1. summary is one sentence of at most 30 words.
2. If the page records a decision, the summary states the decision itself.
3. kind is one of: decision, risk, dependency, requirement, design, meeting, status, other.

Example:
[{"summary": "Certificates rotate every 90 days, automated from October.", "kind": "decision"}]
```

User content:

```
Page 1001, version 4 (page)
Title: Decision: certificate rotation cadence
Labels: decision

Text:
<body_text, at most pages.summary_chars>

Return the JSON array now.
```

`PAGE_KINDS = ("decision", "risk", "dependency", "requirement", "design",
"meeting", "status", "other")`.

### `PAGE_EPIC_PROMPT`

```
Match one Confluence page to the Epic it is about.

Return a JSON array with exactly one object and nothing else:
[{"epic": "KEY"}]

Rules:
1. KEY must be one of the Epic keys listed.
2. If the page is not clearly about one listed Epic, return [{"epic": ""}].
3. Do not match on a single shared word.
```

User content:

```
Epics:
- APS-1: Secure exchange platform
- APS-2: Public API foundations

Page: SDX runbook index
Summary: Lists the runbooks for certificate rotation and key escrow.

Return the JSON array now.
```

### `LEADERSHIP_PROMPT`

```
Write a portfolio summary for leadership.

Use ONLY the Facts. Do not invent people, dates, status, or work.

Output exactly these three headings, in this order, and nothing else:
### Headline
### Decisions needed
### Risks to watch

Rules:
1. Each section is 1 to 3 short bullets, or this exact sentence: Nothing this period.
2. Talk about Epics and outcomes, not tickets or people.
3. After a fact, cite its tag like [APS-1] or [D2]. Use only tags in the Facts.
4. Every Epic marked At risk appears under Risks to watch.
5. Do not add a title or a reference list.

Example of one filled section:
### Risks to watch
- Public API foundations is at risk: one item is blocked and it is due in 5 days. [APS-2]
```

Leadership facts (user content):

```
Product: Integration Platform (IP)
Product Goal: <goal or "none">

Epics:
- [APS-1] Secure exchange platform | SDX | In Progress | 3 of 7 done | due 2026-10-30 | On track
- [APS-2] Public API foundations | APS | In Progress | 1 of 4 done | due 2026-09-30 | At risk: 1 blocked; due in 5 days with 25% done

Documents:
- [D1] decision: Decision: certificate rotation cadence. Certificates rotate every 90 days, automated from October.

From the team reports:
SDX, Decisions we are waiting on: <text of that section>
SDX, Risks: <text>
APS, Open dependencies: <text>

Write the three sections now.
```

The "From the team reports" text has had its citations resolved to links
already; strip the Markdown links back to their labels before inserting, so
the leadership model sees `APS-10` as plain text and cannot cite it.

### `PARTNER_PROMPT`

```
Write a short progress update for partners outside the company.

Use ONLY the Facts. Do not invent dates, features, or commitments.

Output exactly these two headings, in this order, and nothing else:
### What's new
### Coming next

Rules:
1. Each section is 1 to 4 short bullets, or this exact sentence: Nothing to share this period.
2. Name features by their Epic name. Do not use ticket keys, people's names, or team names.
3. Do not mention risks, blockers, estimates, or effort.
4. Do not promise delivery. Say "in progress" or "planned". Give a date only if the Facts give one.
```

Partner facts (user content):

```
Product: Integration Platform

Features:
- Secure exchange platform | In progress | 43% done
  Done this period: Publish exchange status endpoint
- Public API foundations | Planned | 0% done

Documents:
- Partner guide: connecting to the exchange. Explains how partners register and test a connection.

Write the two sections now.
```
