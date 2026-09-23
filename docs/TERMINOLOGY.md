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

Rows whose action says "Shipped in 0.7.0" are done. The others are still open.

| We say | Scrum says | Where | Action |
|--------|-----------|-------|--------|
| `pm daily`, "Daily Scrum" | **Daily Scrum** | command, `daily:` config, `daily_moved` / `daily_wip` scopes, report title | Shipped in 0.7.0. No `standup` alias: nothing was installed yet |
| "committed points", "committed versus delivered" | **forecast** — in 2020 Scrum, "commitment" means the three commitments (Product Goal, Sprint Goal, Definition of Done); Developers *forecast* the work | both proposal docs | Say forecast. Fixed in this change |
| "Owner: A. Lee" | collides with **Product Owner** | `core/sources.py` report meta, README's `--by` description | Say "Assignee" — which is also Jira's actual field name |
| `audience: "directors"` | **stakeholders** | `config.yaml`, report header | Change the default, keep it configurable |
| "backlog quality checks" | **Product Backlog** — the tool checks the Product Backlog, never the Sprint Backlog | README, `pm lint` report title | Be specific |
| `missing-parent`, `linked-to-parent` | Epic is a Jira type, not Scrum — and `epic_types` is already configurable, so a site anchoring on Feature or Initiative gets a rule name that misdescribes it | lint rule, ready criterion | Shipped in 0.7.0. The old names are not accepted |
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
   under a size threshold — `too-big-for-a-sprint`, shipped in 0.8.0. It
   blocks only when the team lists it. It is not on by default.
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

Three Scrum concepts the tool had no notion of when this note was written.
All three shipped in 0.8.0, in the shape `docs/PLAN.md` tranche 2 settled:
the Sprint Goal line does not name an issue, Definition of Done is a
printed checklist, and Product Goal is one optional sentence.

### Sprint Goal — the Sprint's commitment

The Guide's Daily Scrum inspects progress **toward the Sprint Goal**, and the
Sprint Goal is one of the three commitments. `pm` never mentions it. A daily
snapshot that lists movement without saying whether the Sprint Goal is at risk
is a status report, not a Scrum artifact — and search results and Scrum trainers
alike make the same point about the Daily Scrum: it is the Developers'
re-planning session, not a report-out.

`pm today` prints the Sprint Goal Jira already stores, and under it, when
the sprint has an end date:

```text
Sprint ends in N days. Not started: K. Blocked: M.
```

Jira does not link issues to that goal text, so the line does not name an
issue or call one "on the goal path".

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

Shipped as a checklist, not a `pm done` command. `pm report` prints it in
the Increment section. A line may set `label:`, and `pm ready` warns when a
Done item lacks that label. Lines without a label are reminders only.

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

Shipped as optional `product_goal:`. `pm products add --goal` sets it.
`pm report` and `pm brief` print the sentence once. Empty means omit.
The 0.8.0 migration does not add the key to products that are already there.

A fourth, lower priority: nothing supports the **Sprint Retrospective**. Worth
noting that the Retrospective belongs to the Scrum Team, not the PM, so tooling
should at most supply flow metrics into it and never produce its output.

---

## Migration, by risk

**Free — prose only, no behaviour change.** "committed" to "forecast"; "owner"
to "assignee" in the README; "backlog" to "Product Backlog" where the Product
Backlog is what is meant; describing the BA as a Scrum Team member rather than a
pipeline stage. Applied in this change.

**Shipped in 0.7.0, with no aliases.** `pm daily` replaced `pm standup`. The
config block is `daily:`, and the scopes are `daily_moved` and `daily_wip`.
`missing-parent` and `linked-to-parent` replaced `missing-epic` and
`linked-to-epic`. Report titles are "Daily Scrum" and "Product Backlog Lint".
Nothing had been installed, so the old names are not still read.

**Shipped in 0.8.0.** `pm ready` is labelled a team working agreement and
keeps the pass/fail table. `too-big-for-a-sprint` blocks only when it is
listed in `ready.blocking_criteria`, against `ready.max_points` (default 8).
Definition of Done, Product Goal, and the Sprint Goal risk line are in the
commands above. `--to` takes a person.

## What I would not rename

**`workstream`.** Scrum has no word for a slice of one Product Backlog — it
deliberately stops at Product, Product Backlog and Product Owner. Inventing a
Scrum-sounding term would be worse than an honest non-Scrum one, and
`workstream` is already load-bearing in the config, the CLI and your Jira
Components. **`portfolio`** and **`product`** are likewise organisational
words; `product` at least maps cleanly onto Scrum's Product.
