# Review: where the rules guess, and what inference really costs

Written against 0.8.0 (`config_version` 2). Two questions were asked:

1. Where does pm-tools make a judgement with a **string comparison** instead of
   inference, and would inference be worth it there?
2. Inference runs on a laptop and is slow. Should a **background service**
   pre-evaluate so that a command only has to catch up?

This document answers both and proposes the work. Nothing here is built yet.

---

## Status

Shipped in 0.9.0 (`config_version` 3). The review below is unchanged. What
landed: status category and sprint identity from Jira ids, configurable
blocked names, mention account ids, link direction, risk pages by label,
narrower `pm lint` rules, a model-result cache, call counts and an estimate
from `pm doctor`, `model.total_timeout`, and read-only `pm warm` on the
existing scheduler. No daemon. The home directory is `~/.pm-tools`.

---

## How the numbers below were produced

The model-call counts are **measured, not estimated**, and the measurement is
committed: `python3 scripts/measure_inference.py` reproduces the table in
Part 2. It runs each command as a real subprocess against
`tests/fake_jira.py` — the same fake Jira and fake `/v1/chat/completions` the
end-to-end suite uses — and counts every POST the command actually made, with
the prompt sizes. Reading the source and counting `call_model` sites gives a
different (wrong) answer, because batching and issue-type filtering decide the
count at run time.

Wall-clock figures for a real laptop are **not** measured here and are not
invented. `pm doctor` already times a round trip (`core.model.ping` returns
`answered in 12.4s, thinking off`). The plan below makes that the number the
tool quotes, rather than a number this document makes up.

---

# Part 1 — The review: where the rules guess

## 1.1 The finding: this is three populations, not two

The instinct behind the question is "string comparison = dumb, inference =
smart, so swap them." Reading every site says something more useful. The
comparisons fall into three groups, and **only the third is a case for
inference.**

| | What it is | Right answer |
|---|---|---|
| **(a)** | Comparing against something structural: an issue key, a configured component name, a Jira `statusCategory` enum key | Leave it alone. Correct by construction. |
| **(b)** | Guessing at something **Jira already knows the answer to**, by matching English words against a human-typed name | Not an inference problem. Ask Jira. This is the biggest group and every bug in it is silent. |
| **(c)** | A genuine judgement about the quality of free text, expressed as a hardcoded word list | Inference is the right tool — and `pm review` already does exactly this job, better. |

Group (b) is the important one. The repo has been asking the wrong question
about it. Replacing `status.lower() in {"done", "closed"}` with a model call
would be slower, non-deterministic, and *still* a guess. Replacing it with
the status's `statusCategory`, which is already in the API response, is
faster than what is there now and is simply correct.

## 1.2 The inventory

### Group (a) — structural. No change.

| Site | Comparison |
|---|---|
| `core/products.py`, `core/config.py`, `core/workstreams.py` | product/workstream abbrev and name lookups, case-folded |
| `core/filters.py` `STATUS_VALUES` | compiles `open`/`done`/`in-progress` to `statusCategory` JQL |
| `commands/lint.py` | `issue["status_category"] == "done"` / `== "indeterminate"` |
| `commands/today.py` | `_is_done`, `_is_in_progress`, `_is_not_started` on `status_category` |
| `core/metrics.py` | `issuetype.lower() == "epic"` |
| `commands/review.py` | `if key not in valid_keys: continue` — the guard against invented keys |
| `commands/release_notes.py` | `text.startswith("_Could not reach")` — matching the tool's own sentinel |

These compare against a closed set the tool or Jira controls. `statusCategory`
is a three-value enum (`new`, `indeterminate`, `done`) that Jira guarantees
for every status on every site, in English, forever. Matching it is not a
guess. **`core/filters.py` already gets this exactly right, which is the
proof that the rest of the codebase can too.**

### Group (b) — guessing at what Jira already knows. Fix with a lookup.

#### b1. `core/metrics.py` — hardcoded English status names

```python
DONE_NAMES = {"done", "closed", "resolved", "released"}
IN_FLIGHT_NAMES = {"in progress", "in review", "in development",
                   "code review", "review"}

def is_in_flight_name(value):
    text = _name(value)
    return text in IN_FLIGHT_NAMES or "progress" in text or "review" in text
```

Every number `pm metrics` prints — throughput, cycle time, the 85th
percentile, aging, the sprint snapshot — is arithmetic on the dates these two
functions return. They read status names out of the changelog.

What breaks, silently:

- A workflow with `Complete`, `Shipped`, `Accepted`, or `Rejected` never
  matches `is_done_name`. Cycle time is `None`. The issue vanishes from
  throughput. **The report still renders; it is just wrong.**
- A workflow in French, German, or any localised Jira matches nothing.
- `"progress" in text` matches a status named `No progress possible`.
- `"review" in text` matches `Awaiting review of the review` and also
  `Rejected at review`.
- A status named `Ready for Dev` is in flight to the team and invisible here.

The header on the output reads `_Deterministic ... no model._`. It is
deterministic. It is not necessarily right.

**Fix — not inference.** Jira's changelog item for a status change carries
both `toString` (the display name) and `to` (the status ID). `core/sources.py`
keeps `toString` and throws `to` away:

```python
"from": it.get("fromString") or "",
"to": it.get("toString") or "",
```

Keep the IDs too, fetch the project's statuses once
(`/rest/api/3/project/{key}/statuses`), build `status_id -> statusCategory`,
and classify every transition with certainty. Same three-value enum the rest
of the codebase already trusts. Deterministic, one extra cached call per run,
and correct on any workflow in any language.

Category maps to intent exactly: `done` is done, `indeterminate` is in flight,
`new` is not started. That is what `DONE_NAMES` and `IN_FLIGHT_NAMES` were
trying to approximate.

#### b2. `core/metrics.py` — sprint name substring

```python
name = (sprint.get("name") or "").lower()
...
if when and when > start and name and name in to:
```

`sprint_scope_change` decides what was added mid-sprint by asking whether the
sprint's *name* appears inside the changelog's `to` string. Sprint changelog
entries are comma-separated lists of sprint names, hence the substring test.

`Sprint 42` is a substring of `Sprint 421`. It is also a substring of
`Sprint 42 (carry-over)`. Scope-change counts and the `--sprint` forecast are
wrong whenever a team's sprint names nest, which is the default naming scheme.

**Fix — not inference.** The sprint changelog item's `to` field is a list of
sprint **IDs**. `fetch_active_sprints` already returns `id` for every sprint.
Compare IDs. Exact, and it costs nothing.

#### b3. `commands/today.py` — blocked by substring

```python
def _is_blocked(issue):
    status = (issue.get("status") or "").lower()
    if "blocked" in status:
        return True
    labels = [str(l).lower() for l in (issue.get("labels") or [])]
    return "blocked" in labels
```

This feeds `pm today`'s Needs you list, `pm triage`, and the Sprint Goal risk
sentence added in 0.8.0 — so a wrong answer now appears in a line that says
`Blocked: 3`.

It misses a team that says `Impediment`, `On hold`, `Waiting on vendor`, or
`Parked`. It fires on a status named `Unblocked`.

**Fix — configuration, not inference.** The team knows what "blocked" means
in their workflow; that is a Definition-of-Workflow fact, not a judgement.
Add a config block naming the statuses and labels that mean blocked, default
it to today's behaviour so nothing changes on upgrade, and have
`pm workstreams check` (which already validates component names against Jira)
validate these against the project's real status list.

#### b4. `commands/triage.py` — mentions by name substring

```python
text = _comment_text(comment).lower()
if any(name.lower() in text for name in names):
```

A reviewer called `Sam` matches the word `sample`. `Johnson` matches
`johnsonville`. Meanwhile a real Jira `@mention` is stored in ADF as an
`accountId` node, not as the display name, so the case this check exists for
is the case it misses most often.

**Fix — structural.** Walk the ADF for `type: "mention"` nodes and compare
`attrs.id` against the account ID `fetch_myself` already returns. Keep the
name substring as a fallback for plain-text comments, but require a word
boundary.

#### b5. `commands/triage.py` — blocking link by substring

```python
if "block" in (link.get("relation") or ""):
```

Jira's link types are `blocks` and `is blocked by`. This matches both, so it
reports "blocked by" for issues that are actually *blocking others* — the
opposite problem, on a triage line that tells you to go unblock something.

**Fix — structural.** Match the inward/outward direction Jira gives you.

#### b6. `commands/brief.py` — risk pages by the word "risk"

```python
if "risk" in labels:
    return [i for i in items if "risk" in (i.get("title") or "").lower()
            or "risk" in (i.get("detail") or "").lower()
            or "risk" in (i.get("meta") or "").lower()] or items[:2]
```

The workstream already declares `confluence_labels: [decision, risk]`, and
`build_cql` already filters on the label in Confluence. This re-filters the
already-filtered results by looking for the literal word, then falls back to
"the first two, whatever they are" when nothing matches.

**Fix — delete the re-filter.** The label is the author's own statement that
the page is about a risk. That is better evidence than the word appearing in
the title, and it is the evidence the CQL already used.

### Group (c) — genuine judgement in a word list. Inference belongs here.

#### c1. `commands/lint.py` — vague titles

```python
vague = [t.lower() for t in lint_cfg.get("vague_title_terms", [])]
hits = [t for t in vague if t in tokens]
```

Shipped list: `fix, stuff, misc, tbd, wip`.

This is a real judgement — "can a teammate understand this title without
opening the ticket?" — reduced to five words. It flags
`Fix the retry backoff in the exchange client`, which is a perfectly clear
title, because it contains `fix`. It passes
`Update the thing for the release`, which is meaningless, because none of the
five words appear.

`pm review titles` already asks the model this exact question, with a prompt
written for the job:

> Flag only Jira titles a teammate cannot understand without opening the
> ticket. A good title names the work. ... Do not flag a title that is
> already clear.

**So the capability is not missing. It is duplicated, badly, inside the
command that promises not to guess.**

#### c2. `commands/lint.py` — acceptance criteria by marker phrase

```python
markers = [m.lower() for m in lint_cfg.get("acceptance_criteria_markers", [])]
haystack = (issue["acceptance_criteria"] + " " + issue["description"]).lower()
has_ac = any(m in haystack for m in markers)
```

Shipped markers: `"acceptance criteria"`, `"given "`, `"when "`, `"then "`.

`when ` is an extremely common English word. Any description containing
"when the user clicks save" passes this check with zero acceptance criteria
written. The rule finds the *word*, then reports that criteria exist.

`pm review criteria` already judges whether criteria are present, complete,
and testable.

## 1.3 The recommendation for group (c), and the promise it has to keep

The README makes a promise:

> `pm lint` and the fast `pm ready` are rules you can trust.

Moving these two rules into `pm lint` as model calls would break that promise
and make the tool that runs before every Sprint Planning slow. That is not
the proposal.

The proposal is the opposite: **`pm lint` should stop making judgement calls
it cannot make.**

- `vague-title` keeps the part that is a rule — a title under
  `min_title_words`, or a title that is *only* a vague word — and drops the
  "contains a word from a list of five" part. That is the part that produces
  both the false positives and the false confidence.
- `missing-acceptance-criteria` keeps the part that is a fact: the
  acceptance-criteria field is empty and the description has no structure that
  looks like criteria. It stops claiming that the word `when ` is acceptance
  criteria.
- Both findings gain a pointer: `run pm review for a judgement on this`.

That makes `pm lint` smaller, faster, fully trustworthy, and honest about its
own limits — and it routes the judgement to the command that was built for it,
which the user opts into and which already frames its output as opinion.

No new inference is added anywhere. Two bad heuristics are removed.

---

# Part 2 — What inference actually costs

## 2.1 Measured model calls per command

Against the end-to-end fixture: 3 workstreams, ~13 issues, `batch_size` 8.

| Command | Model calls | Prompt chars sent |
|---|---:|---:|
| `pm today` | 0 | 0 |
| `pm lint` | 0 | 0 |
| `pm daily` | 0 | 0 |
| `pm triage` | 0 | 0 |
| `pm metrics` | 0 | 0 |
| `pm metrics --sprint` | 0 | 0 |
| `pm coverage` | 0 | 0 |
| `pm ready` | 0 | 0 |
| `pm ready --deep` | 6 | 6,629 |
| `pm review all` | 6 | 6,697 |
| `pm refine` | 2 | 775 |
| `pm report` | 3 | 4,964 |
| `pm brief --debrief FILE` | 1 | 582 |
| `pm release-notes` | 1 (by inspection *) | — |
| `pm inbox` (5 notes) | 5 | — |
| `pm inbox` (**same 5 notes, second run**) | **5** | — |
| `pm inbox create 1` | 1 | — |

\* The fixture backlog has no done issues, so `release-notes` correctly
skipped the model and measured 0. `draft()` is a single unlooped
`call_model`, so it is one call for any non-empty window.

Two facts jump out.

**Every command in the daily habit already costs nothing.** `today`, `daily`,
`triage`, `lint`, `metrics`, `coverage`, and the fast `ready` make zero model
calls. The commands people run every morning are already instant. A background
service would make none of them faster, because there is nothing to pre-compute.

**Nothing was cached, before 0.9.0.** Running `pm inbox` twice on an unchanged
inbox cost ten model calls to produce two identical outputs. `core/cache.py`
cached Jira search payloads (`FetchCache`, 300s TTL) and nothing else.
`pm inbox create` then paid an eleventh call to re-derive the suggestion it
just showed you. After 0.9.0 the same measurement is 5 calls, then 0, then 0:
the second list and the create both hit the model cache.

## 2.2 How it scales

The fixture is tiny. The shape matters more than the numbers:

```
pm review all      = 2 aspects x workstreams x ceil(issues_in_workstream / 8)
pm ready --deep    = 2 aspects x workstreams x ceil(issues_in_sprint / 8)
pm report          = 1 x workstreams
pm refine          = 2 x ceil(candidates / 8)
pm inbox           = 1 x notes, every single time you list
```

A realistic backlog — 3 workstreams, ~70 open issues each — puts
`pm review all` at roughly `2 x 3 x 9 = 54` sequential calls. Prompts stay
small (measured max 2,262 characters, about 570 tokens), because
`build_material` already caps at 40 items and 180-character details. **The
cost is almost entirely generation, not prompt processing**, and generation is
capped at `max_tokens: 2048` per call.

That makes the arithmetic simple and honest: **time ≈ calls × (answer tokens ÷
decode rate)**. The decode rate is the one number this document will not
invent — it depends on the machine, and on which of the two shipped setups is
in use (`setup-windows-qwen-small.ps1` runs Qwen3-4B Q4_K_M;
`setup-windows-qwen-large.ps1` runs Qwen3.8-27B Q3_K_M, which is several times
slower). `pm doctor` already measures a round trip. **The plan below makes the
tool do this arithmetic with the user's own measured rate instead of guessing.**

## 2.3 The three problems that are real regardless of speed

1. **Everything is recomputed.** The backlog changes by a handful of issues
   between runs; `pm review` re-judges all of it. The single worst case is
   `pm inbox`, which re-infers on every list of an unchanged local JSON file.
2. **The timeout is per call, with no overall budget.** `model.timeout`
   defaults to **600 seconds**. A 54-call review whose endpoint is wedged can
   sit there for hours before giving up. There is no total budget, no ETA, and
   no resume — a `Ctrl-C` at call 40 throws away 40 calls of work.
3. **There is no ETA.** The command prints `Reviewing titles: ... ` per
   workstream and then goes quiet. The user cannot tell a slow run from a hung
   one, which is exactly the situation the 600-second timeout creates.

---

# Part 3 — Should there be a background service?

**Recommendation: no resident daemon. Yes to pre-computation — as a cache, a
`pm warm` command, and the scheduler that already exists.**

## 3.1 Why not a daemon

- **It would not speed up the daily habit.** Measured above: `today`, `daily`,
  `triage`, `lint`, `metrics`, `coverage` and fast `ready` make zero model
  calls today. The commands that are slow are the weekly ones
  (`report`, `review`, `release-notes`) and they are already understood as
  "start it and go get a coffee".
- **A resident process is a support burden on a laptop.** It has to survive
  sleep, hibernate, VPN drops, and a Jira token expiring, and when it is wrong
  it is wrong invisibly. `docs/PLAN.md` section 2.8 deliberately left out a
  GUI, a dashboard, and unattended Jira writes for the same reason.
- **It solves the wrong half of the problem.** The measurement says the
  dominant waste is *recomputing unchanged work*, not *computing at the wrong
  time*. A cache fixes that on the very first run, with no new process.
- **The scheduler already exists.** `pm schedule` registers Windows Task
  Scheduler entries and writes a crontab snippet. "Run something expensive
  before I sit down" is already a solved problem in this repo. It needs
  something worth running, not a second mechanism.

## 3.2 What to build instead, in order

**Step 1 — a model-result cache.** Key on a hash of `(prompt, user content,
model name, sampling settings)`, store under `~/.pm-tools/cache/model/`, TTL and
mode flags mirroring the existing `FetchCache` (`--cached` / `--refresh`
already exist and already mean the right thing). Because every prompt is built
from issue text, an issue whose summary and criteria did not change produces
the same key and costs nothing on the next run.

This alone:
- makes the second `pm inbox` free instead of 5 calls;
- makes `pm inbox create` free, because it reuses the key `pm inbox` just
  computed;
- turns a re-run of `pm review all` after editing 5 of 70 issues from ~54
  calls into ~2 (only the batches containing a changed issue miss).

It requires no new process, no new config section, and no daemon.

**Step 2 — `pm warm`.** One read-only command that walks the configured
workstreams and fills the model cache for the commands you are about to run:
`--review`, `--report`, `--deep`, `--inbox`, or all. It writes no Jira, edits
no config, and produces no report; the only side effect is a warmer cache. If
it is interrupted, everything it finished is still cached — which fixes the
"Ctrl-C throws away 40 calls" problem for free.

**Step 3 — `pm schedule add warm --at 07:00`.** No new code path. The existing
scheduler runs `pm warm` overnight; by the time you run `pm review` you are
"catching up a bit", which is exactly what was asked for. A user who does not
want it simply does not register the job.

**Step 4 — make the cost visible.** Before making any run of N calls,
print the count and an estimate based on the rate `pm doctor` measured on this
machine, then the progress as it goes:

```
pm review all — 54 model calls across 3 workstreams.
Last measured: 18s per call (pm doctor, 2026-09-21). Estimate: ~16 minutes.
  [12/54] API Platform, criteria ...
```

Add `model.total_timeout` as an overall budget so a wedged endpoint stops in
minutes rather than hours, and have the command say what it skipped.

That is the whole benefit of a background service, obtained with a cache, one
new read-only command, and a scheduler entry — all of which are inspectable,
killable, and off by default.

---

# Part 4 — The plan

## Tranche 3a — correctness (no inference added, no inference removed)

1. **Status category from Jira, not from English.** Keep status IDs in
   `core/sources.py` transitions; add `fetch_project_statuses`; build the
   `status_id -> category` map once per run and cache it; rewrite
   `is_done_name` / `is_in_flight_name` to use it, keeping the current name
   lists only as a fallback for a site that will not serve the endpoint.
2. **Sprint scope change by ID.** Compare sprint IDs in the changelog against
   `sprint["id"]` instead of substring-matching the name.
3. **Blocked is configuration.** New `blocked:` config block naming statuses
   and labels; defaults reproduce today's behaviour exactly; validated by
   `pm workstreams check` against the project's real status list.
4. **Mentions by account ID.** Walk ADF `mention` nodes; keep a
   word-boundary name match as fallback.
5. **Link direction.** Match `blocks` / `is blocked by` properly.
6. **Drop the `brief` risk re-filter.** Trust the Confluence label.
7. **`pm doctor` reports the status map** — how many statuses were resolved,
   and which (if any) fell back to name matching.

Everything here makes a deterministic command *more* deterministic. No command
gains a model call. `pm metrics` keeps its `no model` header and starts
deserving it.

## Tranche 3b — honest lint, and the model cache

8. **Narrow `vague-title`** to the two parts that are rules; drop the
   `vague_title_terms` substring test. Point the finding at `pm review`.
9. **Narrow `missing-acceptance-criteria`** to "the field is empty and the
   description has no criteria-shaped structure"; drop the bare `when `/`then `
   word test. Point the finding at `pm review`.
10. **Model-result cache** (`core/model_cache.py`), wired into
    `call_model` / `call_model_json`, honouring `--cached` / `--refresh`,
    reported by `pm doctor` and cleared by the existing cache clear path.
11. **Call counting and an ETA** before any multi-call run, using the latency
    `pm doctor` last measured on this machine, persisted in `~/.pm-tools`.
12. **`model.total_timeout`** as a whole-run budget, with a clear message
    naming what was skipped.

## Tranche 3c — pre-computation

13. **`pm warm`** — read-only, resumable, fills the model cache.
14. **Docs**: `pm schedule add warm --at 07:00` as the recommended setup, and
    a README section on what is deterministic, what is inferred, and what is
    cached.

## Config migration — `config_version` 3

Two new keys, inserted only if absent, never replacing a set value, never
touching products or workstreams, in one migration step `2 -> 3`:

```yaml
blocked:
  statuses: [Blocked]
  labels: [blocked]

model:
  total_timeout: 3600
```

Plus `cache.model_ttl_seconds`, defaulted in `SECTION_DEFAULTS` so an
unmigrated config still works.

## Deliberately not in this plan

- **No daemon, no service, no tray icon.** Part 3 explains why.
- **No new model call in any command that currently advertises "no model".**
  `lint`, `today`, `daily`, `triage`, `metrics`, `coverage` and fast `ready`
  stay deterministic. The README promise holds.
- **No model-written claims about what is true.** Unchanged from
  `docs/PORTFOLIO_PROPOSALS.md`: the model drafts prose and offers opinions; it
  never decides whether an issue is done, blocked, or in a sprint.
- **Nothing from `docs/PLAN.md` section 2.8.** Still deferred.

## Done when

- `pm metrics` produces correct cycle time on a workflow whose statuses are
  named `Complete` / `Shipped`, with a test covering it.
- `Sprint 42` no longer matches `Sprint 421`, with a test covering it.
- `pm lint` makes no claim it cannot support, and says where to get the
  judgement it declines to make.
- A second identical `pm inbox` makes **zero** model calls, with a test
  covering it.
- `pm review all` after a small edit re-runs only the affected batches.
- Every multi-call command states its call count and an estimate before it
  starts, and cannot run past `model.total_timeout`.
- `pm warm` exists, is read-only, is resumable, and is schedulable with the
  scheduler that already ships.
