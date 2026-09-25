# Customising prompts and queries

Defaults live in the code. The config file holds overrides only.
`pm doctor --prompts` and `pm doctor --queries` show what is in effect.

## Prompts

### `report.section`

Writes one workstream's section of the weekly report from its Material. Change the wording or add team rules; keep {headings} so the report keeps its seven sections.

Used by: pm report, pm warm --report (one call per workstream).
Placeholders: audience, empty_section, first_run_line, heading_changed, heading_decisions, heading_dependencies, heading_progress, heading_risks, heading_roadmap, heading_waiting, headings.

```
Write a weekly status note for {audience}.

Use ONLY the CHANGE SUMMARY and the Material. Do not invent people, dates, status, or work.

Output exactly these seven headings, in this order, and nothing else:
{headings}

Rules:
1. Each section is 2 to 4 short bullets, or this exact sentence: {empty_section}
2. If CHANGE SUMMARY says this is the first run, the first section is exactly: {first_run_line}
3. After a fact, cite its tag like [APS-10] or [D1]. Use only tags that appear in the Material.
4. Do not add a title, a workstream heading, or a reference list.
5. A dated line under an item is a comment from this window. Use it for what changed, decisions, blockers, and risks, and cite that item's tag. A comment is not a status change.

Example of one filled section:
### {heading_progress}
- Status endpoint is in review. [APS-10]
- Certificate rotation cadence is decided. [D1]
```

### `report.section_tail`

Last line of the user message for the weekly section.

Used by: pm report, pm warm --report.

```
Write the seven sections now.
```

### `brief.debrief`

Pulls decisions and actions out of meeting notes. Keep the JSON keys; the code reads decisions and actions back.

Used by: pm brief --notes.
Placeholders: action_types.
Must still contain: JSON object, "decisions", "actions", "title", "owner".

```
Extract decisions and actions from these meeting notes.

Return a JSON object with exactly two keys:
- "decisions": array of {"text": string, "owner": string or ""}
- "actions": array of {"title": string, "owner": string or "",
  "issuetype": {action_types}, "workstream": abbrev or ""}

Use ONLY workstream abbrevs from the list. Do not invent dates.
Extract decisions and actions. Do not write any text outside the JSON object.
```

### `inbox.file_note`

Suggests where a captured note belongs. Keep the JSON keys.

Used by: pm inbox.
Placeholders: note_types.
Must still contain: JSON object, "product", "workstream", "issuetype", "title", "criteria".

```
Suggest how to file this note as a Jira Product Backlog item.

Return a JSON object with exactly these keys:
- "product": a product abbrev from the list, or ""
- "workstream": a workstream abbrev from the list, or ""
- "issuetype": {note_types}
- "title": a clear title
- "criteria": one or two Given/When/Then lines, or ""

Use ONLY abbrevs from the list. Do not invent people or dates.
file this note. Do not write any text outside the JSON object.
```

### `refine.titles`

Drafts clearer titles. The code reads key and title from each object.

Used by: pm refine.
Must still contain: JSON array, "key", "title".

```
Draft a clearer title for each Jira item. Keep the meaning. Do not invent scope.

Return a JSON array. Each object has exactly two keys:
- "key": the issue key, copied exactly
- "title": the rewritten title

If you would not change a title, omit that item.

Draft a clearer title. Do not write any text outside the JSON array.
```

### `refine.criteria`

Drafts acceptance criteria. The code reads key and criteria.

Used by: pm refine.
Must still contain: JSON array, "key", "criteria".

```
Draft testable acceptance criteria for each story that is missing them.

Return a JSON array. Each object has exactly two keys:
- "key": the issue key, copied exactly
- "criteria": 2 to 4 short Given/When/Then lines, separated by newlines

Draft acceptance criteria. Do not write any text outside the JSON array.
```

### `refine.tail`

Last line of the user message. The caller adds the blank line before it.

Used by: pm refine.

```
Return the JSON array now.
```

### `review.titles`

Says why a title is unclear and suggests one. The code reads key, problem and suggestion.

Used by: pm review.
Must still contain: JSON array, "key", "problem", "suggestion".

```
Flag only Jira titles a teammate cannot understand without opening the ticket.

A good title names the work. Flag a title if it is one or two vague words, or if it does not say what will change. Do not flag a title that is already clear.

Return a JSON array. Each object has exactly three keys:
- "key": the issue key, copied exactly
- "problem": one short sentence
- "suggestion": a clearer title

If nothing is unclear, return []

Example input:
1. APS-11: Fix stuff
2. APS-10: Publish exchange status endpoint

Example JSON array:
[{"key":"APS-11","problem":"Does not say what to fix.","suggestion":"Fix retry handling in the exchange client"}]

Do not add keys that are not in the list. Do not write any text outside the JSON array.
```

### `review.criteria`

Says what acceptance criteria are missing. The code reads key, problem and missing.

Used by: pm review.
Must still contain: JSON array, "key", "problem", "missing".

```
Flag only stories whose acceptance criteria are missing, vague, or not testable. Good criteria state an observable outcome and cover the happy path plus one obvious error case. Do not flag a story whose criteria are already solid.

Return a JSON array. Each object has exactly three keys:
- "key": the issue key, copied exactly
- "problem": one short sentence
- "missing": the criteria you would add, as one short string

If every story is solid, return []

Example input:
1. APS-20: Rate limiting for public endpoints
   Acceptance criteria / description: (none provided)
2. APS-10: Publish exchange status endpoint
   Acceptance criteria / description: Acceptance criteria: returns current status.

Example JSON array:
[{"key":"APS-20","problem":"No acceptance criteria.","missing":"Given a tenant over the limit, requests are rejected with 429; under the limit, they succeed."}]

Do not add keys that are not in the list. Do not write any text outside the JSON array.
```

### `review.titles_tail`

Last line of the titles user message.

Used by: pm review.

```
Return the JSON array now.
```

### `review.criteria_tail`

Last line of the criteria user message.

Used by: pm review.

```
Return the JSON array now.
```

### `release_notes.prose`

Turns the done list into prose.

Used by: pm release-notes.

```
Draft short release notes from the issue list below.

Use only the issues in the list. Do not add, drop, or rename an issue.
Keep the product and workstream groupings. Write prose, not a new list
of keys. Do not invent dates, people, or outcomes that the list does not
state.
```

### `pages.summary`

One sentence and a kind for a changed Confluence page. The page version is cached, so this is not asked again until the page changes.

Used by: pm warm --pages, pm report.
Placeholders: kinds.
Must still contain: JSON array, "summary", "kind".

```
Summarise one Confluence page for a product report.

Use ONLY the page text. Do not invent decisions, dates, or people.

Return a JSON array with exactly one object and nothing else:
[{"summary": "...", "kind": "..."}]

Rules:
1. summary is one sentence of at most 30 words.
2. If the page records a decision, the summary states the decision itself.
3. kind is one of: {kinds}.

Example:
[{"summary": "Certificates rotate every 90 days, automated from October.", "kind": "decision"}]
```

### `pages.epic_match`

Picks one Epic key for a page, or none. The answer must be one of the keys in the user message.

Used by: pm report, when a page names no single Epic.
Must still contain: JSON array, "epic".

```
Match one Confluence page to the Epic it is about.

Return a JSON array with exactly one object and nothing else:
[{"epic": "KEY"}]

Rules:
1. KEY must be one of the Epic keys listed.
2. If the page is not clearly about one listed Epic, return [{"epic": ""}].
3. Do not match on a single shared word.
```

### `pages.tail`

Last line of a page summary or Epic match.

Used by: pm warm --pages, pm report.

```
Return the JSON array now.
```

### `report.leadership`

One portfolio summary per product, from Epic facts. Cite Epic keys and document tags only.

Used by: pm report --audience leadership.

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

### `report.partner`

A short external update. Epic names only; no keys, names, or risks.

Used by: pm report --audience partner.

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

## Queries

### `status.open`

What 'open' means: not in the Done status category.

Used by: scopes (status: open), pm coverage, pm doctor, pm today.

```
statusCategory != Done
```

### `status.done`

What 'done' means: the Done status category.

Used by: scopes (status: done), pm release-notes.

```
statusCategory = Done
```

### `status.in-progress`

The In Progress status category.

Used by: scopes (status: in-progress).

```
statusCategory = "In Progress"
```

### `status.todo`

The To Do status category.

Used by: scopes (status: todo).

```
statusCategory = "To Do"
```

### `sprint.open`

Issues in a Sprint that is open.

Used by: scopes (sprint: open), pm today.

```
sprint in openSprints()
```

### `sprint.future`

Issues in a Sprint that has not started.

Used by: scopes (sprint: future).

```
sprint in futureSprints()
```

### `sprint.none`

Issues in no Sprint.

Used by: scopes (sprint: none).

```
sprint IS EMPTY
```

### `sprint.by_id`

Issues in one Sprint, by its id.

Used by: scopes when sprint is a number.

```
sprint = {sprint_id}
```

### `assignee.me`

Issues assigned to the authenticated user.

Used by: scopes (assignee: me).

```
assignee = currentUser()
```

### `assignee.unassigned`

Issues with no assignee.

Used by: scopes (assignee: unassigned).

```
assignee IS EMPTY
```

### `assignee.assigned`

Issues that have an assignee.

Used by: scopes (assignee: assigned).

```
assignee IS NOT EMPTY
```

### `membership.anchor.component`

The workstream's own Components.

Used by: workstream membership when membership.by is component.

```
component IN ({values})
```

### `membership.anchor.label`

The workstream's own labels.

Used by: workstream membership when membership.by is label.

```
labels IN ({values})
```

### `membership.anchor.field`

A custom field naming the workstream.

Used by: workstream membership when membership.by is field.

```
{field} IN ({values})
```

### `membership.epics`

Epics that carry the workstream's anchor.

Used by: which Epics anchor a workstream.

```
project = {project} AND issuetype IN ({epic_types}) AND {anchor}
```

### `membership.tagged`

Issues other than Epics that carry the workstream's anchor.

Used by: non-Epic issues that carry the anchor themselves.

```
project = {project} AND issuetype NOT IN ({epic_types}) AND {anchor}
```

### `membership.inherit.epic`

Children of the workstream's Epics. A company-managed project on the old Epic Link may use "Epic Link" IN ({epic_keys}).

Used by: how a child finds its Epic.

```
parentEpic IN ({epic_keys})
```

### `membership.inherit.parent`

Sub-tasks of issues that carry the anchor themselves.

Used by: how a Sub-task inherits from a tagged parent.

```
parent IN ({tagged_keys})
```

### `membership.own_empty.component`

A child with no Component of its own.

Used by: child_component_wins in component mode.

```
component IS EMPTY
```

### `membership.own_empty.field`

A child with no value in the membership field.

Used by: child_component_wins in field mode.

```
{field} IS EMPTY
```

### `coverage.open_in_project`

Open work in a project, before workstreams are applied.

Used by: pm coverage, pm doctor (unclaimed work).

```
project = {project} AND {status_open}
```

### `doctor.membership_open`

The workstream's membership, limited to open issues.

Used by: pm doctor.

```
({base}) AND ({status_open})
```

### `release_notes.done`

Done work in a project inside the release window.

Used by: pm release-notes.

```
project = {project} AND {status_done} AND ({window})
```

### `release_notes.since`

Issues resolved on or after a date.

Used by: pm release-notes --since.

```
resolved >= "{since}"
```

### `release_notes.version`

Issues in one fixVersion.

Used by: pm release-notes --version.

```
fixVersion = {version}
```

### `today.in_sprint_open`

Open issues in the open Sprint of a project.

Used by: pm today.

```
project = {project} AND {sprint_open} AND {status_open}
```

### `confluence.space`

Pages in one space.

Used by: every Confluence read.

```
space = {space}
```

### `confluence.types`

Only these Confluence content types.

Used by: Confluence reads that name content types.

```
type IN ({types})
```

### `confluence.labels`

Pages carrying one of these labels.

Used by: labelled Confluence reads.

```
label IN ({labels})
```

### `confluence.window`

Only pages modified on or after a date.

Used by: every Confluence read.

```
({cql}) AND lastmodified >= '{since}'
```

### `epics.children`

Direct children of these Epics.

Used by: pm report epic progress.

```
parent IN ({keys})
```

### `epics.resolved`

Epics in the workstream that were resolved inside the window.

Used by: pm report epics finished in the window.

```
({base}) AND {status_done} AND resolved >= "{since}"
```

### `registers.descendants`

Every page under a register summary page.

Used by: decision, risk and ADR registers.

```
ancestor = {page_id} AND type = page
```

### `registers.children`

Direct child pages of a register summary page.

Used by: decision, risk and ADR registers.

```
parent = {page_id} AND type = page
```

### `brief.risk_pages`

Pages the workstream labelled as risks.

Used by: pm brief.

```
space = {space} AND label = {label}
```
