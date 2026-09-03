# What `pm` is, and what it could do next

Written after reading the whole codebase (about 2,100 lines) and running every
command end to end against a stand-in Jira. Part 1 describes the tool as it
stands. Part 2 lists what a read of the code suggests is worth building, in
priority order, with a config sketch for each.

Two constraints shape every proposal here:

- **Workstreams stay easy to add and remove.** Anything new must work for a
  fourth or fifth workstream without touching code, and dropping one must be a
  single command.
- **The user never writes JQL.** New capability arrives as plain config options
  compiled into queries, not as another query string to maintain.

---

## Part 1 — What the repo does

`pm` is a single-user command-line assistant for a product manager running
several workstreams out of one Jira project. It reads Jira, Confluence and
optionally SharePoint, and writes Markdown a human is meant to read. Where
judgement is needed it asks a **local** OpenAI-compatible model (llama.cpp with
Qwen, per the bundled Windows setup scripts), so no backlog content leaves the
machine.

| Command | Model? | Answers |
|---------|--------|---------|
| `pm init` | no | Copy the config template to `~/.pm/config.yaml` |
| `pm workstreams` | no | What's configured, and does Jira agree with it |
| `pm report` | yes | The weekly state-of-product write-up, plus what changed since last week |
| `pm lint` | no | Deterministic backlog hygiene findings |
| `pm review` | yes | Judgement calls rules can't make: title clarity, acceptance-criteria quality |
| `pm ready` | optional | One pass/fail Definition-of-Ready verdict per ticket |
| `pm standup` | no | What moved since yesterday, and what's in flight now |

The design that makes it hang together:

- **One config, discovered in a fixed order** (`--config`, `$PM_CONFIG`, `./`,
  `~/.pm/`, bundled), with `${ENV:VAR}` expansion so the API token can stay out
  of the file.
- **Workstreams resolved centrally.** `pm.py` narrows the list once from
  `--workstream`, and every command reads `cfg['_workstreams']`, so a new
  command gets scoping for free.
- **Membership by Jira Component, inherited down the hierarchy.** Epics carry
  the Component; Stories, Tasks, Bugs and Sub-tasks usually don't, and are
  claimed through their parent. Because inheritance is understood, `pm lint`
  and `pm ready` don't nag child work for a Component it doesn't need.
- **Deterministic and inferred output kept apart.** `lint` and the fast `ready`
  are rules you can trust; `report`, `review` and `ready --deep` are opinions,
  labelled as such, and a model call that misfires skips a batch instead of
  sinking the run.
- **Week-to-week memory.** `report_state.json` keys items by a stable id (Jira
  key, Confluence page id) so "what changed" survives re-ordering.

### What this change set fixed on the way through

These were blocking or actively wrong, so they are already done rather than
proposed:

| Fix | Why it mattered |
|-----|-----------------|
| Moved every Jira call to `/rest/api/3/search/jql` with `nextPageToken` paging | Atlassian has **removed** `/rest/api/3/search` from Jira Cloud, which every fetch in the tool called. Nothing worked against a real site. |
| Item fetches now page | `lint`, `ready`, `standup` and `report` stopped at `max_results` (100) with no indication that there was more. |
| `pm report` no longer crashes | A local variable shadowed the `workstreams` module, so the command died with `AttributeError` before its first fetch. |
| Membership also follows an issue's **own** Component | The old scope was `parentEpic IN (epics)` only, so a Story tagged directly under an untagged Epic, its sub-tasks, and any workstream with no tagged Epic were silently invisible. |
| Workstreams are declarative; scopes are plain options | Six `*_jql` strings per workstream became `components: [...]`. |
| `pm workstreams` | Add, remove and verify a workstream without hand-editing YAML. |
| Config validated at load | A mistyped option names the valid choices instead of failing inside Jira. |
| End-to-end tests | `tests/fake_jira.py` answers searches by evaluating the generated JQL against an in-memory backlog, so membership resolution is provable without a Jira site. |

---

## Part 2 — Proposals

Priority is "what a PM notices first", and each item names what it touches so
the cost is visible.

### P1 — Make the setup trustworthy and automatable

#### 1. `pm doctor` — prove the whole setup in one command

`pm workstreams check` now verifies Jira membership. Nothing verifies the rest:
Confluence credentials, the model endpoint, the custom-field IDs, or whether the
output directory is writable. A first-run PM finds out one command at a time.

```
pm doctor
  config          ~/.pm/config.yaml — 14 settings, 3 workstreams        ok
  jira            connected as Dana Stainton (APS project visible)      ok
  custom fields   story points customfield_10016                        ok
                  start date customfield_10015                          MISSING
  workstreams     SDX 11 items · APS 7 · ITK 1                          ok
  confluence      space SDX reachable, 4 pages in the last 7 days       ok
  model           qwen-local answered in 1.8s                           ok
  output          ~/.pm writable                                        ok
```

Touches: one new `commands/doctor.py` reusing the checks in
`commands/workstreams.py`; a `fetch_fields` call in `core/sources.py`. Exits
non-zero on failure, so it doubles as a scheduled smoke test. Low risk.

#### 2. Discover the custom-field IDs instead of asking for them

Today a wrong `story_points_field` makes `no-estimate` and `has-estimate`
silently pass on every ticket — the documented failure mode most likely to make
a report quietly wrong. `/rest/api/3/field` gives the answer.

```
pm doctor --discover-fields      # write the IDs it finds back into config
```

Match on field name (`Story Points`, `Story point estimate`, `Start date`,
`Acceptance Criteria`), show what it found, ask before writing. Reuses the
comment-preserving config editor `pm workstreams add` already has. Low risk.

#### 3. `pm coverage` — what no workstream claims, and what two claim

The direct consequence of making workstreams easy to add and remove: it becomes
easy to leave work behind. Membership is a union by default, so a child naming a
different Component than its Epic lands in two workstreams, and an Epic with no
Component lands in none.

```
pm coverage
  Claimed by nobody (7 issues)
    APS-30  Rotate exchange signing certificates   epic APS-3 has no component
    ...
  Claimed by two or more
    APS-50  Expose exchange metrics on the gateway  SDX (via epic), APS (own component)
  Components in Jira with no workstream
    Documentation, Spike
```

This is also how a PM decides whether `membership.child_component_wins` should
be `true`. Touches: one new command; the queries are the negation of existing
membership clauses, so no new config. Low risk, high diagnostic value.

#### 4. Where output goes, and in what shape

Every command writes `<name>_<date>.md` into the current directory. That makes
`report_state.json` position-dependent (the README has to tell people to always
run from `~/.pm`) and makes automation awkward.

```yaml
output:
  directory: "~/pm-reports"     # default: alongside the config
  formats: [md, json]           # per-command override with --format
```

Plus `--out PATH` on every command, and `--stdout` for piping. Touches a small
`core/output.py` helper and one line in each command. Low risk.

#### 5. An exit-code contract, so the gates can actually gate

`pm lint` and `pm ready` are exactly the checks worth running before sprint
planning, but both always exit 0. Give them a threshold:

```
pm lint  --fail-on error          # non-zero if any error-severity finding
pm ready --fail-under 80          # non-zero if under 80% of tickets are ready
```

Touches `commands/lint.py`, `commands/ready.py`, `pm.py`. Trivial, and turns the
tool into something a scheduled job can act on.

#### 6. A local cache, and `--cached`

Every command re-fetches from scratch. Iterating on lint thresholds, or showing
someone a report, means hammering Jira and waiting each time.

```yaml
cache:
  enabled: true
  directory: "~/.pm/cache"
  ttl_minutes: 30
```

```
pm lint --cached        # reuse the last fetch, however old
pm lint --refresh       # ignore the cache for this run
```

Touches `core/sources.py` (one decorator around `search_issues`) and a new
`core/cache.py`. It also unlocks demo and test runs with no credentials at all.
Low risk if the cache key includes the JQL and the field list.

### P2 — New answers, not just new plumbing

#### 7. `pm triage` — the daily "needs me" queue

`pm standup` says what moved. It doesn't say what's stuck waiting on the PM,
which is the more useful daily question.

```yaml
triage:
  unassigned_in_sprint: true
  blocked: true                  # flagged, or blocked-by links, or Blocked status
  mentions_me: true              # comments mentioning me since last run
  new_bugs_within_days: 1
  in_sprint_untouched_days: 3
```

Grouped by workstream, each with the one action that would unblock it. Touches a
new command plus two fetches in `core/sources.py` (issue links, comments). All
deterministic — no model needed.

#### 8. `pm metrics` — the numbers a director asks for

The changelog fetch that powers `pm standup` already has everything needed for
delivery metrics, and they are pure arithmetic:

- throughput: issues reaching Done per week, per workstream
- cycle time: first `In Progress` to `Done`, median and 85th percentile
- aging work in progress: how long each in-flight item has been in flight
- estimate accuracy: story points completed per sprint versus committed
- scope change: items added to an open sprint after it started

```
pm metrics --weeks 8
pm metrics --json          # for a spreadsheet or a dashboard
```

Touches a new command and a `changelog`-based helper in `core/state.py`. No
model. This is the largest single addition in value-per-line here.

#### 9. A structured risk / decision / dependency register

The weekly report asks the model to write "Decisions", "Dependencies" and
"Risks" sections out of whatever Confluence pages happened to be modified. It
has no register to draw on, so those sections are as good as last week's page
edits.

```yaml
register:
  jira_labels:                   # a Jira issue can be the source of truth
    risk: [risk]
    decision: [decision]
    dependency: [dependency, external-dep]
  confluence_labels: [decision, risk, dependency]
```

`pm risks` lists them with owner, status and age; the weekly report cites the
register instead of inferring one. Touches `core/sources.py` (label-scoped
fetch), `commands/report.py`, one new command. Medium size, and the report gets
noticeably less hand-wavy.

#### 10. `pm duplicates`

Already on the README's roadmap, and cheap to do well: generate candidate pairs
deterministically (title token overlap, same Component, both open), then ask the
model only about the shortlist. Keeps the local model's work bounded, which
matters on a laptop.

```
pm duplicates --threshold 0.6 --workstream SDX
```

#### 11. `pm release-notes`

Also on the roadmap. Done since a date or in a `fixVersion`, grouped by
workstream, drafted by the model with a plain bullet list as the fallback when
the model is unavailable.

```
pm release-notes --since 2026-08-01
pm release-notes --version "2026.9"
```

#### 12. `pm publish` — put the report where people read it

A Markdown file on a laptop is not distribution. Publishing to a Confluence page
(create or update by title) and/or a Teams webhook closes the loop.

```yaml
publish:
  confluence: {space: "APS", parent_page: "Weekly Reports"}
  teams_webhook: "${ENV:PM_TEAMS_WEBHOOK}"
```

First write path in the tool, so `--dry-run` should be the default until
confirmed. Medium risk: needs Confluence write scope on the token.

#### 13. Write-back to Jira, behind an explicit flag

The PM reads a lint report and then does the fixes by hand. A narrow, safe
subset is worth automating:

```
pm lint  --apply-labels needs-grooming --yes
pm ready --apply-label ready-for-sprint --yes
```

Nothing writes without both the flag and `--yes`, and a dry run prints the exact
change list first. Touches a new `update_issue` in `core/sources.py`. Higher
risk than anything else here, hence the double opt-in.

#### 14. `pm sprint-review` — committed versus delivered

At sprint end: what was in the sprint at the start, what finished, what carried
over, and what was added mid-flight. All from the changelog, all deterministic,
and the one report that makes the weekly write-up credible over time.

### P3 — Reach and robustness

#### 15. Membership by more than Component

Not every team tags by Component; some use labels, a team field, or a
fixVersion, and some workstreams span projects. The membership resolver is now
one function, so this generalises without reintroducing JQL:

```yaml
- name: "Billing Platform"
  abbrev: "BIL"
  projects: [APS, BILL]          # more than one project
  match:
    components: ["Billing Platform"]
    labels: ["billing"]          # any match claims the issue
```

Touches `core/workstreams.py` only, plus config validation. Keeps
`components:` working as the common shorthand.

#### 16. Deeper hierarchies

`epic_types` already lets an Initiative act as the anchor, but the inheritance
walk is one hop of `parentEpic` plus one of `parent`. Advanced Roadmaps sites
with Initiative → Epic → Story → Sub-task need a configurable depth:

```yaml
membership:
  parent_depth: 3
```

#### 17. Concurrency and progress

Each workstream is fetched serially, and a run over three workstreams with the
model enabled is a coffee break. Fetches are independent and read-only: a small
thread pool plus a progress line would cut wall time substantially. Needs care
with Jira rate limits (`429` with `Retry-After`), which nothing currently
handles.

#### 18. Continuous integration

There is no CI. The suite is now 99 tests and needs no network, so a GitHub
Actions workflow running it on Python 3.9 through 3.13 (and a Windows job, since
that's the target laptop) would catch exactly the class of breakage that made
`pm report` crash and left the tool pointed at a removed Jira endpoint.

#### 19. Keep the token out of a plaintext file entirely

`${ENV:VAR}` helps, but the default path still ends with a token in
`~/.pm/config.yaml`. `keyring` support (Windows Credential Manager, macOS
Keychain, Secret Service) would let the config say
`api_token: "${KEYRING:pm/jira}"`. Small change to `core/config.py`, one optional
dependency.

#### 20. Model-call resilience

`core/model.py` skips a batch when JSON parsing fails. Better: retry once at half
the batch size, then fall back to per-issue calls, and cache successful
responses by content hash so a re-run after a crash is instant. Touches
`core/model.py` only.

---

## Smaller fixes worth batching

Found while reading; each is a few lines.

| Where | Issue |
|-------|-------|
| `core/sources.py` `fetch_sharepoint` | The search term is interpolated straight into `search(q='{query}')` with no escaping — a Component name containing an apostrophe breaks the URL. |
| `core/sources.py` `fetch_confluence` | Uses the v1 `/rest/api/content/search` endpoint. Still live, but Atlassian is steering people to the v2 API; worth tracking given what just happened to Jira's search endpoint. |
| `core/config.py` | Only the workstream, membership and scope sections are validated. A missing `model.timeout` or `output.file` still fails with a raw `KeyError` mid-run. |
| `config.yaml` `lint.vague_title_terms` | `refactor` and `test` flag plenty of legitimate titles ("Refactor the retry handler"). Worth splitting into "vague on its own" versus "vague anywhere". |
| `commands/lint.py` | `stale` only looks at `updated`, which any bulk edit resets. The changelog would give a truer "no real movement in N days". |
| `commands/report.py` | Dropped items in the change block lose their reference tag, so the model can't cite them. |
| `pm.py` | `--workstream` accepts abbreviations only. Accepting the full name, case-insensitively, costs three lines. |
