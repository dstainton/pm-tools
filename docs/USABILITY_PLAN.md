# Tranche 4 — usefulness, accessibility, and fewer commands

A review of the whole CLI from the seat of the person who uses it: a product
manager for one agile team. It asks of every command *what does a PM do
differently because this exists*, and treats accessibility — including the
way the tool reads to someone with ADHD or on the autism spectrum — as part
of whether it works, not as a coat of paint.

Nothing here is built. This is a plan.

Vocabulary follows `docs/TERMINOLOGY.md`: Daily Scrum, refinement, Sprint
Goal, Product Goal, Definition of Done, team working agreement, throughput
and cycle time (never velocity), forecast (never committed), assignee,
stakeholders, and `workstream` stays `workstream`.

---

## How this review was done

Every command was run for real against the stand-in Jira in `tests/fake_jira.py`
with the end-to-end backlog, and the output read as a user reads it. Findings
below quote that output. Nothing in this document is inferred from source
alone.

---

## The verdict in one page

**What is genuinely good.** The daily habit is real. `pm today` answers a
question a PM actually has at 8:30am and hands back five numbered things to
do. Capture (`pm note`) is frictionless. Every Jira write previews and asks
once. `pm lint` and the fast `pm ready` are rules, not opinions, and say so.
`pm doctor` names its own fix. The local-model boundary is drawn in the right
place: the model writes prose, rules decide what is true. `pm brief` is the
strongest idea in the tool and the least finished.

**The hurdle before any of that.** There is no guided way in. `pm init`
copies a 409-line annotated template and stops; from there you hand-edit
YAML across twenty sections, and the concepts you must get right first —
workstreams, Components, custom-field IDs — are the ones a new user
understands least. Every piece needed to do this conversationally already
exists (`pm doctor` verifies, `core/config_edit.py` writes without
disturbing comments, `pm workstreams add` appends an entry,
`sources.fetch_project_components` lists what Jira already knows). Nobody
meets the defects below if they cannot get past the config file. See Part 3.

**The three things most worth fixing once you are in.**

1. **Two numbered queues for one queue.** `pm today` and `pm triage` classify
   the same tickets with the same code and hand out *different numbers* for
   the same ticket, into two state files, applied by two different commands.
   In the live run, `pm do 4` and `pm triage --apply 6` were the same write to
   the same issue. This is the single worst usability defect in the tool and
   it lands hardest on the user who most needs a stable list.

2. **The answer is in a file you have to go and open.** `pm lint` prints
   `7 issues checked — 3 findings` and a filename. `pm ready` prints a count
   and a filename. `pm report` prints nothing but a filename. The findings
   exist; the tool declines to say them. For a PM whose hard part is
   *starting*, "the answer is in `~/.pm-tools/out/lint_report_2026-09-24.md`"
   is a tax, not a result.

3. **Severity is a coloured circle and every link says "open".** The weekly
   report's reference table came back with thirteen links, every one of them
   reading `open`; the lint report conveyed error, warn and review only as
   🔴 / 🟠 / 🔵. Both fail for a screen-reader user, and both fail for anyone
   who does not hold a colour-to-severity map in working memory.

**And one source is being wasted.** Confluence is fetched by `pm report` and
`pm brief`, and then a whole decision page reaches the model as its title
plus the first **180 characters** of its body, on a fixed seven-day window
that no command can vary. Jira comments got a windowed reader and a
6000-character budget in 0.10.0; the pages where a team actually writes its
decisions down got neither. The report section named "Decisions since last
report" is fed the thinnest source in the tool. See Part 4.

**The shape of the fix.** The tool has 23 commands. The answer to most of the
gaps below is *fewer commands with better answers*, not new verbs — with one
exception, `pm setup`, which earns a verb because it runs before the front
door exists. Rule 1 of `docs/PORTFOLIO_PROPOSALS.md` is "one front door". The
command list has since grown past what one front door can cover.

---

## Part 1 — Command by command

For each: what it does now, what it should do for this user, and the call.

### `pm today` — keep, and make it the only queue

**Now.** Date line, Sprint Goal, NEEDS YOU (5 of 7), MOVED SINCE YESTERDAY,
AGING, REFINEMENT GAPS, and a footer. Numbered actions persist to
`today.json` for `pm do N`.

**Defects seen in the live run.**

- The same ticket appeared twice with two numbers, because it is claimed by
  two workstreams: `4 APS-50 … IP/SDX` and `5 APS-50 … IP/APS`. Both wrote
  the same `PUT /rest/api/3/issue/APS-50`. Overlap is deliberate at the
  membership layer and `pm coverage` exists to surface it — but a numbered
  action list must be a list of *things to do*, and doing this one twice is
  not a thing to do. De-duplicate by issue key at the action layer; show the
  extra workstream as a tag on the single row.
- A finished sprint printed under the `SPRINT GOAL` heading with the line
  `Sprint ended 14 days ago.` A goal that ended two weeks ago is not today's
  goal; it is an alert that no sprint is open.
- Nothing says how old the numbers are. `pm do 4` at 4pm silently uses the
  snapshot taken at 8:30am.

**Should.** Same shape every day (predictability is a feature — keep it),
one row per ticket, an explicit line when the list is stale, and an honest
line when a sprint is not open.

### `pm triage` — fold into `pm today`

**Now.** The same classifier as `pm today` over a wider net: it adds mentions
of you, blocked-by links, and new bugs, groups by product/workstream, writes
`triage.json`, and applies with `pm triage --apply N`.

The live run is the argument. `pm today` listed 5 of 7; `pm triage` listed
the same 7, renumbered. `APS-30` was `1` in both. `APS-50` was `4` and `5` in
today, `6` and `7` in triage.

**Call.** Keep the mention, blocked-by-link, and new-bug classifiers — they
are the valuable part and `pm today` lacks them. Retire the second list.
`pm today` shows the top few; `pm today --all` shows the whole queue with the
*same numbers*; `pm do N` applies either. Keep `pm triage` as an alias for
`pm today --all` for one release, as `pm review` was kept.

### `pm lint` — keep, print the findings

**Now.** Seven deterministic rules. Prints counts, writes Markdown or JSON.
Exits non-zero with `--fail-on`. Snooze / accept / assign memory.

**Defects.** The findings never reach the screen. Severity in the file is
emoji-only. Link text is `open`. Findings for `vague-title` and
`missing-acceptance-criteria` instruct the user to run `pm review titles` and
`pm review criteria` — a command the tool itself prints a deprecation notice
for. The tool is routing users to a command it is retiring. Count lines read
`1 issues checked — 1 findings`.

**Should.** Print the top findings grouped by rule, with the file as the
archive. Point at `pm refine`, which drafts the fix, rather than at a
deprecated verb.

### `pm ready` — keep; it is the gate, and it should answer a planning question

**Now.** Maps lint rules to named criteria, applies the team working
agreement, adds `too-big-for-a-sprint`, reports a percentage and a gap table.

**Should.** A PM runs this before Sprint Planning. The question is not "what
percent is ready" but "can we fill a sprint from what is ready?" The tool
already computes throughput and cycle time in `pm metrics` and story points
here. Joining them — *N ready items, M points, against a recent throughput of
X per week* — turns a statistic into a planning answer. Keep the percentage
for `--fail-under` and CI.

### `pm refine` — keep; lower the ceremony

**Now.** Finds items failing the agreement, drafts titles and acceptance
criteria with the model, suggests an estimate from the median of done
stories, writes a worksheet you edit by hand, writes back on `--apply`.

The no-blank-page idea is right and the write-back is well guarded.

**Defect.** An item that fails *only* on `too-big-for-a-sprint`, or whose
findings are all hidden by an earlier decision, is silently absent from the
queue — so a ticket can be blocked by the agreement and invisible to the
command whose job is to unblock it.

### `pm review` — finish the deprecation

**Now.** A half-state. The `pm review` verb prints a deprecation note and
delegates to `refine`; `review.py` is live library code used by `pm ready
--deep` and `pm warm`; and `pm lint` messages send users to the deprecated
verb.

**Call.** Remove the verb. Keep `review.py` as the model-judgement library
under a name that says so. Repoint the lint messages at `pm refine`. This is
a naming cleanup, not a capability cut.

### `pm coverage` — keep, fold the surface into `pm doctor`

**Now.** Unclaimed open issues, overlaps, unused components. Exits 1 on
unclaimed work. Honest and correctly scoped. This is a setup-and-drift
command, run rarely.

**Call.** Keep the code and the exit code. It belongs next to `pm doctor` and
`pm workstreams check`, which answer the same question — *does my config
still match Jira?* — from three different verbs.

### `pm metrics` — keep; stop forecasting from two data points

**Now.** Throughput per week, cycle time median and p85, open count, a
landing date, scope added, forecast points. `--sprint` reports the open
sprint. No model.

**Defect.** `landing_date` divides open items by the weekly rate with no
minimum sample. The live run produced `Landing: 26 Aug 2027` from one
completed item in eight weeks, printed in a table beside real numbers with
no qualifier. A PM who repeats that in a stakeholder meeting has been let
down by the tool. Suppress the forecast below a sample threshold and say why:
*not enough completed work to forecast*.

**Should.** Say what the numbers mean for the next sprint, not only what they
were.

### `pm brief` — keep; the best idea here, and the least finished

**Now.** Per-audience memory, what changed since you last met them, comments
from that window, decisions needed, risks from Confluence. `--debrief` turns
meeting notes into decisions and actions and can create the tickets.

**Defects.** No links anywhere — bare keys, and a Confluence risk rendered as
a raw URL after an em dash. "Decisions needed" is the triage queue relabelled,
so it lists things waiting on *you*, not things this room can decide. The
risk pages are fetched in full and then only their titles are printed, on a
seven-day window regardless of when you last met this audience (Part 4).

**Should.** The prep page is what a PM reads walking into a room. Link every
key. Say what each risk page actually says. Separate *what I owe this room*
from *what I need from this room* — that second list is the reason the
meeting exists.

### `pm report` — keep; let the shape follow the content

**Now.** Model writes seven fixed headings per workstream; deterministic
wrapper, portfolio table, references, metrics appendix. Prints nothing but a
filename.

**Defects.** Seven headings are emitted whether or not there is anything
under them, so a quiet week produces a page of `No update this week`.
"Decisions we are waiting on" — the only section that asks the reader to act
— is sixth. The references table shows the key as plain text and puts the
link on the word `open`. Metrics rendering is wrapped in a bare
`except Exception: pass`, so a broken appendix is invisible. And the section
called "Decisions since last report" is fed Confluence pages truncated to 180
characters (Part 4).

### `pm daily` — keep; print it

**Now.** Movement in the window and work in progress, grouped by assignee,
with comments. Markdown links to Jira — the only command that links keys in
its file. Writes a file; `--print` echoes it.

**Defect.** This is the one artifact read aloud in a meeting at 9:15, and by
default it goes to a file. Print by default; keep the file.

### `pm note` / `pm inbox` — keep; keep them instant

**Now.** `pm note "…"` captures in one line and answers
`Captured #1. Nothing else needed now.` — the best single line in the tool.
`pm inbox` lists notes with a model-suggested product, workstream, title and
acceptance criteria, and can create the ticket.

**Defect.** `pm inbox` calls the model once per note on every list, so the
latency of reviewing your own notes grows with the number of notes. A capture
tool must stay instant at both ends. Cache the suggestion with the note and
refresh on request.

### `pm publish` — rework; it silently degrades the artifact

**Now.** Markdown to Confluence storage format and/or a Teams webhook, behind
preview and confirmation.

**Defect.** The converter handles headings, bullets, code fences and
paragraphs. It does not handle tables or links. So publishing a weekly report
to Confluence drops the entire references table into escaped text and turns
every link into literal `[open](https://…)` characters. The command reports
success. The one place the tool speaks to the whole organisation is the place
it quietly mangles the output.

### `pm doctor` — keep; fix the column

**Now.** Config, Jira, projects, custom fields, membership, statuses, model
timing, caches, each with `ok` / `warn` / `FAIL` as a word. Status as text
rather than colour is exactly right.

**Defect.** The status column is placed by padding the detail to a fixed
width. A long config path pushes `ok` past the column and the alignment that
carries the meaning is gone, as it was in the live run.

### `pm schedule`, `pm update`, `pm products`, `pm workstreams` — keep

Infrastructure, and sound. `pm update` never replacing a filled-in config is
a promise worth the code it takes. Read-only scheduling is the right line.

### `pm warm` — keep; warm the things that do not change

**Now.** Fills the model cache for review, report and inbox. Read-only.

**Defect.** `--report` warms the whole per-workstream section prompt, which
contains every issue in the workstream. One ticket moving invalidates the
entire section, so an overnight warm is wasted by the first morning edit.
The cache is keyed at the granularity of the report rather than of the thing
that changed. Part 4.4 proposes the first fix — per-page Confluence summaries
keyed on the page version, which is stable for weeks — and the principle
generalises.

### `pm init` — keep as the manual path; it should no longer be the only one

**Now.** Copies a 409-line annotated template and stops. Refuses to overwrite.

Both behaviours are right, and neither is a way in for someone who has not
used the tool before. Part 3.

---

## Part 2 — Defects found by running the tool

| # | Command | What happens | Why it matters |
|---|---------|--------------|----------------|
| 1 | `today`, `triage` | One issue claimed by two workstreams gets two action numbers and two identical writes | Duplicate work, and a numbered list you cannot trust |
| 2 | `today`, `triage` | The same ticket has different numbers in the two lists | Working-memory hazard |
| 3 | `today` | An ended sprint prints under `SPRINT GOAL` | Reads as the current goal |
| 4 | `do N` | Writes from the snapshot with no staleness check or warning | Silent write against old state |
| 5 | `do N` | Overdue suggestion is always today + 14 days | Ignores the sprint end date |
| 6 | `lint`, `ready` | Severity is emoji-only in the Markdown | Colour as the sole carrier of meaning |
| 7 | all Markdown | Every link's text is `open` | "open, open, open" in a link list |
| 8 | `lint`, `ready` | Findings point at `pm review`, which prints a deprecation notice | The tool routes users to a retiring command |
| 9 | `metrics` | Landing date extrapolated from one completed item | False confidence in a stakeholder-facing number |
| 10 | `publish` | Tables and links are dropped converting to Confluence | Report loses its references, reports success |
| 11 | `doctor` | Status column breaks on a long config path | Alignment carries the meaning |
| 12 | `report` | Metrics appendix wrapped in `except Exception: pass` | Failures invisible |
| 13 | `lint`, `ready` | `1 issues checked — 1 findings` | Small, constant, and reads as unfinished |
| 14 | `brief` | Confluence risk rendered as a bare URL after an em dash | Unreadable aloud, unclickable in the file |
| 15 | `refine` | Items failing only `too-big-for-a-sprint` never enter the queue | The gate blocks work the fixer cannot see |
| 16 | `coverage`, `triage` | `--out` is accepted and ignored | A flag that does nothing |
| 17 | `report` | A Confluence page body is cut to 180 characters | The decisions source is the thinnest input |
| 18 | `report`, `brief` | Confluence window is one fixed global number | Ignores the window the command already has |
| 19 | `report`, `brief` | Confluence fetches are never cached | `--cached` and `pm warm` cannot help |
| 20 | `brief` | Risk pages are fetched in full, then only the title is shown | The body is discarded at the moment it is needed |

---

## Part 3 — Getting started: `pm setup`

The tool is unusable until `config.yaml` is right, and the only help on
offer is a well-commented template. This is the largest barrier to anyone
adopting it, and it lands on exactly the people Part 6 is about: a
409-line YAML file across twenty sections is a wall, and the sections you
must get right first are the ones whose vocabulary you have not learned yet.

### 3.1 What already exists

Most of a guided setup is already written and only needs to be sequenced:

| Piece | Where | Does |
|---|---|---|
| Verify and name the fix | `commands/doctor.py` | config, Jira login, projects, fields, membership, statuses, model timing, caches |
| Write without breaking comments | `core/config_edit.py` | `set_jira_field_if_blank`, `add_list_entry`, `remove_list_entry` |
| Append a workstream or product | `commands/workstreams.py`, `commands/products.py` | the exact YAML a setup step needs to emit |
| Find custom-field IDs | `pm doctor --discover-fields --yes` | writes only blank values |
| List a project's Components | `sources.fetch_project_components` | already used by `pm coverage` and `pm workstreams check` |
| Count what a query would see | `sources.approximate_count` | already used by `pm workstreams check` |

### 3.2 What is missing

Four lookups the tool never makes, plus the conversation itself:

- **The Jira project list.** `GET /rest/api/3/project/search`. Today you must
  know your project key before you start.
- **The Confluence space list.** `GET /wiki/rest/api/space`. Same problem,
  once per workstream.
- **The model list.** `GET {model base}/v1/models`. Both llama.cpp and
  Lemonade serve it; the bundled PowerShell scripts even tell you to curl it
  by hand. Nothing in the Python ever asks.
- **Opening a browser.** Python's `webbrowser` module, to land the user on
  the API-token page rather than describing where it is.

### 3.3 The shape of `pm setup`

One question at a time, each step verified against the live service before
it is written.

| Step | Asks for | Verified by | Writes |
|---|---|---|---|
| 1. Site | the site name, `dpdd` | — | `jira.base_url: https://dpdd.atlassian.net` |
| 2. Login | your Atlassian email | — | `jira.email` |
| 3. Token | opens the API-token page, you paste | `GET /rest/api/3/myself` → greets you by name | `jira.api_token`, preferring `${ENV:…}` |
| 4. Project | pick from the projects you can see | — | `jira.project` |
| 5. Workstreams | confirms one per Jira Component, with an issue count each | `approximate_count` | the `workstreams:` entries |
| 6. Products | group those workstreams, or skip | — | `products:` and each `product:` line |
| 7. Fields | story points, start date, acceptance criteria | the existing field discovery | the three `jira.*_field` keys |
| 8. Confluence | a space per workstream, then which labels exist there | a page count | `confluence_space`, `confluence_labels` |
| 9. Model | pick a model id from the server | times one round trip | `model.endpoint`, `model.name` |

Step 5 is the one that matters most. Workstreams are the concept a new user
least understands, and the Jira project already contains the answer — the
Component list *is* the proposal. Turning "read the README section on
membership, then write YAML" into "these are your Components, which of them
are workstreams?" is the difference between adopting the tool and not.

### 3.4 Rules it must hold to

Setup is not a licence to break the invariants the rest of the tool keeps.

- **Never change a value that is already set.** The same promise `pm update`
  makes. Re-running is safe, and it picks up only what is unset.
- **Resumable and skippable.** Every step can be skipped, and says what it
  leaves unset and which command fixes it later.
- **Show the line before writing it.** Same contract as a Jira write:
  preview, then confirm.
- **Prefer the environment variable for the token.** The config documents
  `${ENV:VAR_NAME}` and nothing helps anyone use it. Default to writing the
  reference and printing the one command that sets it; pasting the secret
  into the file is the fallback, not the default.
- **Read-only against Jira and Confluence.** Setup writes one local file.
- **Refuse to prompt when stdin is not a terminal**, and name the flags,
  exactly as the write path already does.
- `pm setup --section jira|model|workstreams|confluence` fixes one thing
  later, so `pm doctor` can stop describing a fix and start naming a command:
  *run `pm setup --section model`*.

`pm init` stays as the "I will edit it myself" path.

### 3.5 Why this is also an accessibility item

Everything Part 6 asks for — bounded, predictable, resumable, one thing at a
time, always says what it will do before it does it — is what a guided setup
is. The current alternative is the opposite of all four. This is the single
largest executive-function barrier the tool has, and it is at the front door
where it turns people away silently.

---

## Part 4 — Confluence and the other sources

### 4.1 What happens today

Confluence is read by two commands and written by one.

- **`pm report`** calls `sources.fetch_confluence` per workstream with CQL
  built from `confluence_space` and `confluence_labels`, filtered to
  `lastmodified >= today - confluence.lookback_days`. Pages become items with
  `detail` set to the HTML-stripped body and `watch` set to the version date,
  so `core/state.py` does detect a page that changed since last week. They
  reach the model as material and appear in the references table.
- **`pm brief`** fetches only the risk-labelled pages, takes the top three,
  and prints the title and a raw URL.
- **`pm publish`** writes a page. Nothing else touches Confluence.

So the answer to "are we bringing Confluence in?" is: fetched, largely
discarded.

### 4.2 The four problems

**The body is cut to 180 characters.** `model.build_material` renders each
item's detail through `short_detail(detail, detail_limit)` with
`detail_limit=180`. A decision page arrives as its title and the first 180
characters — which is the preamble, not the decision.

A 452-character decision page, put through `build_material` as it stands:

```
[SDX-C1] (Confluence) Decision: certificate rotation cadence
    The team met on 18 September to decide the certificate rotation
    cadence. Options considered were 30, 60 and 90 days. Security argued
    for 30 on the grounds of exposure window; platf...
```

The page says `DECISION: rotate every 90 days, automated from October`. That
sentence is not in the prompt. The model is handed the options and denied the
outcome, and then asked to write a section called "Decisions since last
report". Jira comments were given a windowed reader and a 6000-character
section budget in 0.10.0. The page where the decision is actually recorded
was left on 180 characters and cut mid-word.

**The window is one global number.** `confluence.lookback_days` (default 7)
applies to every caller. 0.10.0 taught Jira comments to follow each
command's own window — since the last report, since you last briefed that
audience, `--days`. Confluence never learned it. Brief an audience you last
met six weeks ago and you still see seven days of pages.

**Nothing is cached.** The fetch cache wraps `search_issues`,
`approximate_count` and `fetch_comments`. `fetch_confluence` and
`fetch_sharepoint` are outside it, so every run re-fetches, `--cached` does
nothing for them, and `pm warm` cannot pre-fetch them.

**`pm brief` throws the body away.** It fetches the whole risk page and
prints a title and a bare URL. What the risk actually says — the one thing
you need walking into the room — is fetched and dropped.

### 4.3 What to build: a windowed page reader

Mirror `core/comments.py`, which already solved this problem once. A new
`core/pages.py` with the same shape: per-command cutoff, caps
(`max_pages`, `excerpt_chars`, `section_chars`), and an `enabled` switch,
under a `pages:` config block.

- `pm report` uses the last report's timestamp, as its comments already do.
- `pm brief` uses the last time that audience was briefed.
- `pm daily` does not read Confluence and should not start.
- A real excerpt budget in the material, so a decision page gets the space a
  decision needs.
- Cache the fetch on the same discipline as comments:
  `("confluence", cql, cutoff, limit)`.

### 4.4 Summarising a page — and why it belongs in `pm warm`

A changed Confluence page is the ideal thing to summarise with a local model,
for one reason: **it changes rarely, and it has a version number.** Key a
one-paragraph summary on the page id and its version, and a page that has
not been edited is never summarised twice. That is what makes it warmable in
a way today's warming is not.

`pm warm --report` currently warms the whole per-workstream section prompt.
That prompt contains every issue, so a single ticket moving invalidates the
entire section and the overnight warm is wasted. A per-page summary keyed on
`(page id, version)` is stable for weeks. On a machine where inference is
slow, the difference between those two cache granularities is the difference
between warming being worth running and not.

So: **`pm warm --pages`**, warming per-page summaries. And the more general
lesson — *cache the model at the granularity of the thing that changes, not
the granularity of the report* — is worth applying beyond Confluence.

This stays inside the project's rules. Summarising a page a human wrote, and
citing it, is prose about a source, not a claim about what is true. The
summary must cite the page, and the page must stay in the reference table.

### 4.5 What that unlocks

- **`pm brief`** can say what a risk page actually says, in a sentence, with
  a link — instead of a title and a URL.
- **`pm report`**'s "Decisions since last report" section gets a real source.
- **A "what changed in the wiki" view.** Pages changed inside the window,
  each with a one-line summary and a link. As a section of `pm report` and
  `pm brief` rather than a new verb, per rule 1.

### 4.6 SharePoint has the same shape

`fetch_sharepoint` reaches the model through the same 180-character detail,
on the same global `lookback_days`, uncached, and is disabled by default so
nobody has noticed. Whatever `core/pages.py` does for Confluence should cover
it, or SharePoint should be honestly marked as unfinished.

---

## Part 5 — Improvements that benefit every command

### 5.1 One shared render layer

`pm today` gained OSC 8 terminal hyperlinks in 0.10.1, implemented privately
in `commands/today.py` as `terminal_links`, `terminal_width`, `_hyperlink`
and `_issue_cell`. That work should be promoted to `core/render.py` and used
everywhere, so that **every Jira reference is a link in every command**:

- Terminal: OSC 8 on the key when stdout is a terminal; plain when piped.
  Gaps today are `pm triage`, `pm coverage`, the aging block in `pm metrics`,
  `pm refine`, the `pm lint` and `pm ready` count lines, `pm inbox create`,
  and every `writes.preview`.
- Markdown: link text is the key, never `open`. `[APS-30](…)`, not
  `[open](…)`. Gaps are `pm lint`, `pm ready`, `pm report` references, and
  the whole of `pm brief` and `pm release-notes`.
- One helper for "issue key as a link", so a new command cannot get it wrong.

### 5.2 One identity for an issue

Three schemes are live: `pm report` cites `SDX-J1`, `pm brief` uses the Jira
key as the same field, everything else uses the key. The report's tag scheme
exists so the model can cite a source without inventing a key — that is
sound and should stay — but the references table should show and link the
key, and the two commands should not use one field for two meanings.

### 5.3 Answer on screen; keep the file as the archive

`pm lint`, `pm ready`, `pm report` and `pm review` write a file and tell you
its name. Print the bounded answer — the same "top few, never a wall" rule
already applied to `pm today` — and keep writing the file.

### 5.4 One way of saying when

The live output mixes `due 4 days ago`, `(09:12)`, `2026-09-20`,
`26 Aug 2027`, `19 days`, and `today 09:12`. Pair relative and absolute
everywhere: `20 Sep 2026 (4 days ago)`. Relative alone assumes the reader is
tracking today's date; absolute alone assumes they will do the arithmetic.

### 5.5 Say what is not there

`--out` is accepted by every config-driven command and ignored by `pm today`,
`pm triage` and `pm coverage`. Either honour it or reject it.

---

## Part 6 — Accessibility

Two audiences, overlapping: someone using a screen reader or a
non-monospace/high-zoom display, and someone whose attention, working memory
or sense of time works differently. Most fixes serve both.

### 6.1 Meaning carried by colour or symbol alone

- **Lint severity is 🔴 / 🟠 / 🔵 with no word.** The severity names already
  exist in the code and in the JSON output. Print them: `Error · bad-dates`.
  Keep the glyph if it helps; do not let it be the only carrier.
- **`pm ready` section headings** (`### 🔴 Not ready`) already carry the
  words. That is the pattern to copy.
- **`→` is the only marker for "this is a command you can type"** in
  `pm today`, `pm triage` and `pm inbox`. Add a word: `Run: pm do 1`.
- **`·` as a separator** in date lines and inbox suggestions reads as
  nothing or as "middle dot" depending on the screen reader.
- Add a `--plain` flag (and honour `NO_COLOR`) that drops OSC 8, glyphs and
  padding and prints one labelled fact per line. This is the accessible path,
  not a degraded one.

### 6.2 Link purpose

Thirteen links in one weekly report, all reading `open`. A screen reader's
link list is thirteen identical entries, and "open" is also the least useful
thing to read aloud: it describes the action, not the destination. Link text
must identify the target — the issue key.

### 6.3 Layout that only exists in a monospace terminal

`pm today`, `pm triage`, `pm coverage`, `pm doctor`, `pm schedule` and the
aging blocks align with space padding (`{key:<8}`, `{n:<2}`, `{abbrev:<6}`)
and have no column headers. The relationship between a key and its status is
positional and visual only. Fixes:

- Under `--plain`, emit labelled lines instead of columns.
- Give the terminal tables a header row where columns carry meaning.
- Stop hard-coding the status column position (`pm doctor` already breaks on
  a long path).

### 6.4 Truncation and terminal width

Titles are cut at fixed widths — 52, 40 and 36 characters in `pm today`, 60
and 55 in the Markdown — regardless of the terminal. `pm today` learned to
wrap Sprint Goal lines to the real width in 0.10.1; nothing else did. A
`NEEDS YOU` row runs to roughly 75 characters before the terminal wraps it
with no indent, breaking the alignment that is doing the work. Use the real
width everywhere, and hang-indent the wrap as the Sprint Goal now does.

### 6.5 For ADHD and autistic users specifically

This is where the tool is closest to being genuinely good, and where the
remaining defects cost the most.

**What the tool already gets right, and must not lose**

- The same screen shape every day. Predictable structure is a feature; empty
  sections should keep their heading and say they are empty, exactly as they
  do now.
- Bounded output. "Top few, never a wall."
- One-line capture with an explicit end: `Captured #1. Nothing else needed
  now.` — it closes the loop and asks nothing further.
- Preview, then one confirmation. No irreversible surprise.
- Decisions stick: snooze and accept mean a dismissed thing stays dismissed.

**What to fix**

- **One queue, one numbering.** Two lists that number the same ticket
  differently is the highest-cost defect in this document for a user who
  relies on external structure to hold state.
- **Numbers must not go stale silently.** `pm do 4` uses whenever you last
  ran `pm today`. Print the age of the list (`from pm today at 08:31, 7 hours
  ago`) and warn past a threshold before writing. Time blindness is the
  expected case, not the edge case.
- **Put the answer where the attention already is.** A filename is a second
  task. Print the findings.
- **Give the day an end.** `pm today` always closes with a prompt to do more.
  When the queue is clear it should say so plainly. Completion is not a
  decoration; it is what makes a daily habit survivable.
- **Keep capture and review instant.** `pm inbox` calling the model per note
  on every list turns a two-second check into an unpredictable wait, and
  unpredictable waits are where a capture habit dies.
- **One sensory vocabulary.** Emoji appear in files but never the terminal;
  arrows in the terminal but never files. Decide once.
- **Say the next action in words, not punctuation.** `→ pm do 1` should read
  `Run: pm do 1`.
- **Never present a guess as a fact.** `Landing: 26 Aug 2027` from one data
  point is the kind of false precision that is very expensive to a person who
  will anchor on it.

### 6.6 What to measure

Add a test that renders each command's screen with `--plain` and asserts no
line depends on a glyph, a colour or a fixed column for its meaning. That
keeps the property from decaying.

---

## Part 7 — Code and refactoring

### 7.1 `core/sources.py` (904 lines) — one Jira item model

Five near-duplicate fetchers each build their own dict from the same search:

| Function | Shape |
|---|---|
| `fetch_jira` → `make_item` | citation shape: `ref`, `title`, `watch`, `uid` |
| `fetch_jira_detailed` | the full lint shape, 18 keys |
| `fetch_jira_cards` | a strict subset of the above |
| `fetch_jira_changelog` | subset + `transitions`, **no `updated`** |
| `fetch_jira_history` | subset + `transitions` (status and sprint) |

They agree on `key`, `url`, `summary`, `status`, `assignee`, `issuetype`.
The missing `updated` on changelog rows is already worked around in
`commands/daily.py`, which stamps `card["updated"] = now` so the comment
reader will look at it — a workaround that marks the seam.

Proposal: one normalizer (raw issue plus a field spec, out comes the core
item, optionally with transitions), with `make_item` reduced to a thin report
adapter. Three datetime parsers (`parse_timestamp`, `parse_jira_datetime`,
and an inline `_parse`) collapse to one.

### 7.2 Two HTTP layers, one used

`core/http.py` implements `send` with 429 handling and is exercised by tests
but imported by no production path; `core/sources.py:send` duplicates the
policy and is what actually runs. Make one real.

### 7.3 Error messages a PM can act on

Jira failures surface as `raise_for_status()` text. A 401 reads
`401 Client Error: Unauthorized for url: …`. The fix a user needs is "your
API token is wrong or expired — regenerate it at id.atlassian.com". `pm
doctor` has the right voice; the rest of the tool should borrow it.

### 7.4 Config validation stops short of Jira

`core/config.py` validates products, workstreams, membership, ready, blocked,
scopes and the model budget, and reports typos well. There are no defaults or
validation for the `jira:` block, so a missing `base_url` surfaces as a
`KeyError` from whichever command touches it first — the one part of the
config a first-time user is guaranteed to touch is the one part that fails
late. Separately, `vague_title_terms` and `acceptance_criteria_markers`
survive in the test fixtures after 0.9.0 replaced them with
`vague_title_alone`; the shipped template is already correct.

### 7.5 Functions worth splitting

`ready.build_markdown` (~103), `today.render_screen` (~100), `lint.check_issue`
(~84), `daily.build_markdown` (~88), `refine.run` (~76), `today.gather` (~76),
`report.build_report` (~71), `sources.fetch_jira_changelog` (~69). The common
shape is gather, decide and render in one function; the render half is what
the shared layer in §5.1 wants anyway.

### 7.6 Duplication to retire alongside the merges

`today.classify_need` / `triage.classify`; `today.render_screen` /
`triage.render`; `today.build_aging` / `metrics.aging_wip`; `review._batches`
/ `refine._chunks`; `today.run_do` / `writes._fill_current_user`; the summary
table in `lint.build_markdown` / `ready.build_markdown`.

### 7.7 Cache invalidation on write

`pm do` can change a due date and the search cache keeps the old value for up
to five minutes, with nothing connecting the write log to the cache. Drop the
affected entries after a successful write.

### 7.8 Keep

304 tests that run with no network, and `tests/fake_jira.py` evaluating real
JQL against an in-memory backlog, are the reason this review could be done by
running the tool. That infrastructure is an asset.

---

## Part 8 — Gaps worth filling

Ranked by how often a PM hits them. Each is a view on data the tool already
fetches, and — respecting "one front door" — most are flags, not new verbs.

Parts 3 and 4 are the two largest and have their own sections: a guided
`pm setup`, and a windowed Confluence reader with warmable per-page
summaries. Everything below assumes both.

1. **One issue, everything about it.** `pm show APS-30`: status, assignee,
   dates, parent, lint findings, readiness verdict, recent comments, links,
   and what changed lately. When a stakeholder messages you about a ticket,
   the tool currently has no answer that is not a whole report. This is the
   largest missing piece and the cheapest to build.
2. **Sprint Planning support.** `pm metrics --sprint` covers the Sprint
   Review case and `docs/PLAN.md` deliberately dropped `pm sprint-review`.
   Nothing covers planning. `pm ready --plan` — ready items, ranked, with
   points against recent throughput — is the joining of two things already
   computed. (The Sprint Retrospective stays out, per `docs/TERMINOLOGY.md`.)
3. **What is blocking what.** `sources.fetch_issue_links` exists and
   `pm triage` uses blocked-by to classify, but nothing shows the chain. As a
   section of `pm today --all`, not a new verb, and distinct from the
   standalone risk register that `docs/PLAN.md` §2.8 deferred.
4. **What did I change, and when.** Every write appends to
   `write-log.jsonl` and nothing reads it. `pm log` — or `pm today --log` —
   answers "when did we move that due date?" from data already on disk.
5. **Epic-level rollup.** Workstream and issue are covered; the Epic, which
   is how a PM talks to stakeholders about a feature, is not.

---

## Part 9 — What this plan does not propose

Already decided, with reasons recorded in `docs/PLAN.md` §2.8,
`docs/PORTFOLIO_PROPOSALS.md` and `docs/INFERENCE_PLAN.md`, and not reopened
here: `pm duplicates`; a standalone risk register; `membership.parent_depth`,
label and fixVersion membership; a keyring backend; a GUI or dashboard ("a
dashboard is another place to have to go and look"); a resident daemon;
unattended Jira writes; model-written claims about what is true; a second
capture command; a thread pool; `pm done`; and retrospective automation.

Nothing above needs any of them.

---

## Part 10 — Sequence

Grouped so each step ships something usable on its own. Earlier steps are
mostly deletion and consolidation, which makes the later ones smaller.

**Step 0 — `pm setup`.** First, because it gates adoption and because it
depends on nothing else here. The four missing lookups (project list,
Confluence space list, model list, browser open), then the step sequence in
§3.3 on top of the existing verification and comment-preserving write
helpers. Confluence steps can land with the rest and simply write the space
and labels; Part 4 makes those fields earn their place afterwards.
*Touches a new `commands/setup.py`, small additions to `core/sources.py` and
`core/config_edit.py`; no existing command changes behaviour.*

**Step 1 — correctness of the daily habit.** De-duplicate actions by issue
key. Print the age of the numbered list and warn before a stale write. Treat
an ended sprint as an alert, not a goal. Suggest the sprint end date rather
than today + 14. Suppress the landing-date forecast below a sample threshold.
Fix the `pm doctor` status column. Fix the count-line plurals.
*Touches `commands/today.py`, `commands/doctor.py`, `core/metrics.py`.*

**Step 2 — `core/render.py`.** Promote the OSC 8 helpers out of
`commands/today.py`. Every issue key becomes a link in every command,
terminal and Markdown. Link text becomes the key. Severity gains its word.
Add `--plain` and honour `NO_COLOR`. Add the rendering test from §6.6.
*Touches every command's render path; no fetch logic.*

**Step 3 — answers on screen.** `pm lint`, `pm ready` and `pm report` print
their bounded answer. `pm daily` prints by default. `pm inbox` caches its
suggestions. `pm today` says when the queue is clear.

**Step 4 — one queue.** `pm today --all` absorbs the triage classifiers with
one numbering and one state file. `pm triage` becomes an alias for a release.
Retire the `pm review` verb, rename the library, repoint the lint messages.
This is where the duplication in §7.6 is deleted rather than refactored.

**Step 5 — Confluence earns its place.** `core/pages.py` as the windowed
reader, modelled on `core/comments.py`: per-command cutoff, caps, an
`enabled` switch, and the fetch inside the cache. A real excerpt budget in
the material. Per-page summaries keyed on page id and version, and
`pm warm --pages` to fill them. `pm brief` says what a risk page says. The
same treatment decides SharePoint's fate.
*Needs a `pages:` config block, so this is the `config_version` bump.*

**Step 6 — the comms artifacts.** Teach the Confluence converter tables and
links so `pm publish` stops degrading a report. Drop empty sections from
`pm report` and lead with what the reader must act on. Split `pm brief`'s
"decisions needed" into what you owe the room and what you need from it.

**Step 7 — the refactor.** One Jira item model, one HTTP layer, one datetime
parser, `jira:` config validation, actionable HTTP errors, cache
invalidation on write. Internal, and much smaller once steps 2 and 4 have
removed the duplicate render and classify paths.

**Step 8 — the gaps.** `pm show` first; it is the most-wanted and the
cheapest. Then planning support, the blocking chain, and the write log.

Step 5 needs a `config_version` bump for the `pages:` block, and
`pm update`'s existing migration path carries it — the same way the
`comments:` block arrived in 0.10.0. Nothing else here has to be
configuration: `--plain` and the forecast threshold can both be behaviour.
