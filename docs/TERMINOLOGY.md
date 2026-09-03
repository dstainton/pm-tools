# Terminology, checked against Scrum

Measured against the **Scrum Guide, November 2020** (v7), which is still the
current official edition — there is no 2021–2026 revision, whatever the dates on
search results suggest. Where a practice sits outside the Guide, this document
says so rather than pretending otherwise.

## The rule that resolves most of this

`pm` speaks **two vocabularies**, and every disagreement below comes from mixing
them:

- **Jira's vocabulary** — Epic, Story, Task, Sub-task, Component, story points,
  assignee. These are field and type names in a tool. They are not Scrum, and
  several are not even Jira-universal, but when we name a field we must use
  Jira's word or the config is a lie.
- **Scrum's vocabulary** — Sprint, Product Backlog, Sprint Backlog, Increment,
  Sprint Goal, Product Goal, Definition of Done, refinement, Developers,
  Product Owner, stakeholders.

The rule: **config keys and field names use Jira's word; everything a human
reads uses Scrum's word.** Today `pm` mixes them in both directions.

---

## Where we stand

### Already correct — keep

| Term | Why it is right |
|------|-----------------|
| **refinement** | The Guide's phrase is "Product Backlog refinement". Fixed already. |
| **Sprint**, **Sprint Planning** | Scrum events, used correctly. |
| **stakeholders** | The Guide's word for the people at Sprint Review. Currently only in the proposals; see `directors` below. |
| **acceptance criteria** | Not Scrum, but not Scrum-conflicting either — it belongs to the Product Backlog item, and every team uses it. |
| no **velocity** anywhere | The Guide prescribes no metrics. `pm metrics` proposes throughput and cycle time, which is the flow-metric direction Scrum.org itself takes in the Kanban Guide for Scrum Teams. Keep velocity out. |

### Wrong or outdated — change

| We say | Scrum says | Where | Action |
|--------|-----------|-------|--------|
| `pm standup`, "Daily Standup" | **Daily Scrum** | command, `standup:` config, `standup_moved` / `standup_wip` scopes, report title, README | Rename to `pm daily`; keep `standup` as an alias |
| "committed points", "committed versus delivered" | **forecast** — in 2020 Scrum, "commitment" means the three commitments (Product Goal, Sprint Goal, Definition of Done); Developers *forecast* the work | both proposal docs | Say forecast. Fixed in this change |
| "Owner: A. Lee" | collides with **Product Owner** | `core/sources.py` report meta, README's `--by` description | Say "Assignee" — which is also Jira's actual field name |
| `audience: "directors"` | **stakeholders** | `config.yaml`, report header | Change the default, keep it configurable |
| "backlog quality checks" | **Product Backlog** — the tool checks the Product Backlog, never the Sprint Backlog | README, `pm lint` report title | Be specific |
| `missing-epic`, `linked-to-epic` | Epic is a Jira type, not Scrum — and `epic_types` is already configurable, so a site anchoring on Feature or Initiative gets a rule name that misdescribes it | lint rule, ready criterion | Rename to `missing-parent` / `linked-to-parent`, accept the old names as aliases |
| `--assign --to ba` | Scrum has three accountabilities: **Product Owner, Scrum Master, Developers**. A Business Analyst is part of the Developers | proposal item 6 | Assign to a *person*, not a role — see below |

### Keep Jira's word, on purpose

`Epic`, `Story`, `Task`, `Sub-task`, `Component`, `story_points_field`,
`parentEpic`, `assignee`, `sprint in openSprints()`. All of these name something
in Jira. Renaming them to Scrum words would make the config describe a Jira that
does not exist. Where prose can avoid them it should say "Product Backlog item"
and "estimate", since the Guide says Developers *size* items and prescribes no
unit.

---

## The one real argument: Definition of Ready

`pm ready` is built on a concept that **is not in the Scrum Guide**. This is
worth being straight about, because it is the tool's most prominent gate.

What the Guide actually says about readiness is narrow: Product Backlog items
are ready for Sprint Planning when the Developers judge them small enough to be
Done within one Sprint. That is the whole of it.

The wider community is genuinely split:

- **Against.** Scrum Alliance and Scrum.org both classify a Definition of Ready
  as a complementary practice, and warn that an exhaustive checklist becomes a
  stage gate — work queuing behind an approval step, which is the waterfall
  shape Scrum exists to avoid, and prioritises process over the conversation.
- **For.** Jeff Sutherland has argued repeatedly that a strong Definition of
  Ready is one of the highest-leverage practices available, and it appears as a
  pattern in the Scrum Patterns work. The Guide's own allowance that refinement
  can take up to a tenth of the Developers' time exists precisely so items
  arrive at Sprint Planning usable.

**Recommendation — keep the capability, change the framing and the default.**

1. Call it what it is: a **team working agreement**, not part of Scrum. One line
   in the report header and the config comment does this.
2. Make the Scrum-anchored criterion the one that always blocks: *can this be
   Done inside one Sprint?* In practice that is an estimate that exists and is
   under a size threshold — a new `too-big-for-a-sprint` check, which the tool
   cannot currently make at all.
3. Keep the rest (`clear-title`, `has-acceptance-criteria`, …) blocking only
   because the team chose them, which is already how `ready.blocking_criteria`
   works. The mechanism is right; only the labelling implies more authority than
   it has.
4. Report the gate as a **refinement worklist**, not a pass/fail gate on the
   Sprint. Same data, and it stops the tool arguing for a tollgate.

## The other real argument: the PM to BA handoff

Proposal item 6 has `--assign --to ba`, and item 5 is framed around the BA's
queue. In Scrum terms this encodes exactly the split the Definition-of-Ready
critique warns about: refinement is a Scrum Team activity between the Product
Owner and the Developers, not a baton passed from one job title to another.

The practical fix keeps the usefulness without the shape: **assign to a person,
not a role.** `pm refine --assign APS-20 --to dana` works for a BA, a Developer,
a Product Owner, or an external SME, and it does not bake a two-stage process
into the tool. The proposals should describe the BA as a member of the Scrum
Team who does most of the refinement in practice, which is true, rather than as
the second stage of a pipeline.

---

## What the audit found missing

Three Scrum concepts the tool has no notion of. All three are worth building,
and the first is the most glaring.

### Sprint Goal — the Sprint's commitment

The Guide's Daily Scrum inspects progress **toward the Sprint Goal**, and the
Sprint Goal is one of the three commitments. `pm` never mentions it. A daily
snapshot that lists movement without saying whether the Sprint Goal is at risk
is a status report, not a Scrum artifact — and search results and Scrum trainers
alike make the same point about the Daily Scrum: it is the Developers'
re-planning session, not a report-out.

```
$ pm daily -w SDX
Sprint 24 · Goal: "Tenants can rotate exchange certificates without downtime"
  4 of 7 items Done · 2 in progress · 1 not started · 3 days left
  At risk: APS-30 is not started and is on the Goal path
```

Costs one new fetch: Jira's Agile API (`/rest/agile/1.0/sprint/{id}`) exposes a
sprint's `goal`, which the current JQL-only client never asks for. This also
gives `pm today` and `pm report` a spine they currently lack.

### Definition of Done — the commitment we skipped

The Definition of Done **is** in the Guide, as the Increment's commitment, and
it is the one the tool ignores while enforcing the one that is not in the Guide.

```yaml
definition_of_done:            # a checklist, per product or one for all
  - "Acceptance criteria demonstrated"
  - "Unit and integration tests pass in CI"
  - "Documentation updated"
  - "Deployed to staging"
```

`pm done` would check items claiming Done against it, and the weekly report
would describe the Increment in those terms. Together with the DoR reframing
above, this puts the Scrum-correct pair in place instead of only the optional
half.

### Product Goal — what a product is currently missing

The portfolio proposal gives each product a name, an abbreviation and a project.
The 2020 Guide would give it a **Product Goal**, and the roadmap section of the
report should be framed against it rather than being a list of Epics.

```yaml
products:
  - name: "Data Exchange"
    abbrev: "DX"
    project: "APS"
    product_goal: "Any tenant can exchange data with a partner in under a day"
```

One config key, and the report gains the sentence directors actually want.

A fourth, lower priority: nothing supports the **Sprint Retrospective**. Worth
noting that the Retrospective belongs to the Scrum Team, not the PM, so tooling
should at most supply flow metrics into it and never produce its output.

---

## Migration, by risk

**Free — prose only, no behaviour change.** "committed" to "forecast"; "owner"
to "assignee" in the README; "backlog" to "Product Backlog" where the Product
Backlog is what is meant; describing the BA as a Scrum Team member rather than a
pipeline stage. Applied in this change.

**Cheap, with aliases — one release of overlap.** `pm standup` becomes
`pm daily`, with `standup` accepted silently. The `standup:` config block and
the `standup_moved` / `standup_wip` scopes gain `daily_*` names, with the old
keys still read. `missing-epic` becomes `missing-parent` and `linked-to-epic`
becomes `linked-to-parent`, with the old names accepted in
`ready.blocking_criteria` and `lint.required_fields`. Report titles change to
"Daily Scrum" and "Product Backlog Lint". Nobody's config breaks; the
`CHANGELOG` carries the deprecations.

**Needs your decision.** Reframing `pm ready` as a working agreement and a
refinement worklist. Adding the Definition of Done and the
`too-big-for-a-sprint` check. Adding the Sprint Goal fetch. Changing
`--to ba` to `--to <person>`. Each of these changes what the tool asserts about
your process, which is not mine to decide.

## What I would not rename

**`workstream`.** Scrum has no word for a slice of one Product Backlog — it
deliberately stops at Product, Product Backlog and Product Owner. Inventing a
Scrum-sounding term would be worse than an honest non-Scrum one, and
`workstream` is already load-bearing in the config, the CLI and your Jira
Components. **`portfolio`** and **`product`** are likewise organisational
words; `product` at least maps cleanly onto Scrum's Product.
