"""`pm review` — model-based judgement checks (the smart cousins of lint).

Where `pm lint` uses cheap, certain rules, `pm review` asks the local model to
make judgement calls that rules can't:

  pm review titles     Idea 1 — flag genuinely ambiguous / unclear titles and
                       suggest a clearer rewrite.
  pm review criteria   Idea 2 — judge whether a story's acceptance criteria are
                       complete and testable, and list what's missing.
  pm review all        Both of the above.

Everything here is an OPINION for a human to weigh, not a verdict. Output is
framed as "flagged for your review" and always includes the model's reasoning
so you can disagree at a glance. Because it is a judgement call, findings are
never presented as errors.

The model is asked for structured JSON so we can build a clean table and, if a
call misfires, skip that batch rather than sink the run.
"""

import datetime as dt

from core import sources, model, workstreams


# ---------------------------------------------------------------------------
#  Prompts — short, one example, JSON last. Written for Qwen3.8 Q3_K_M.
# ---------------------------------------------------------------------------
# A 3-bit Qwen3.8 follows a tiny schema and a worked example much more
# reliably than a long "be a meticulous PM" brief. Both prompts keep the
# phrase "JSON array" so tests and the fake model can recognise them.

TITLES_PROMPT = """\
Flag only Jira titles a teammate cannot understand without opening the ticket.

A good title names the work. Flag a title if it is one or two vague words, \
or if it does not say what will change. Do not flag a title that is already \
clear.

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

Do not add keys that are not in the list. Do not write any text outside the \
JSON array.
"""

CRITERIA_PROMPT = """\
Flag only stories whose acceptance criteria are missing, vague, or not \
testable. Good criteria state an observable outcome and cover the happy path \
plus one obvious error case. Do not flag a story whose criteria are already \
solid.

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

Do not add keys that are not in the list. Do not write any text outside the \
JSON array.
"""

TITLES_USER_TAIL = "Return the JSON array now."
CRITERIA_USER_TAIL = "Return the JSON array now."


# ---------------------------------------------------------------------------
#  Building the batches we send to the model
# ---------------------------------------------------------------------------

def _batches(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def build_titles_input(issues):
    lines = []
    for n, iss in enumerate(issues, 1):
        lines.append(f"{n}. {iss['key']}: {iss['summary']}")
    lines.append("")
    lines.append(TITLES_USER_TAIL)
    return "\n".join(lines)


def build_criteria_input(issues):
    lines = []
    for n, iss in enumerate(issues, 1):
        ac = iss["acceptance_criteria"].strip()
        if not ac:
            # Fall back to the description so the model has something to judge.
            # Keep it short: Q3_K_M loses the instruction if the body is long.
            ac = sources.short(iss["description"], 280) or "(none provided)"
        lines.append(f"{n}. {iss['key']}: {iss['summary']}\n"
                     f"   Acceptance criteria / description: {ac}")
    lines.append("")
    lines.append(CRITERIA_USER_TAIL)
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
#  Running one aspect (titles or criteria) over a workstream's issues
# ---------------------------------------------------------------------------

def review_aspect(model_cfg, aspect, issues, batch_size):
    """Return (findings, errors) for one aspect over one workstream."""
    if aspect == "titles":
        prompt, builder, keys = TITLES_PROMPT, build_titles_input, ("problem", "suggestion")
        candidates = issues
    else:  # criteria — only look at story-type issues
        prompt, builder = CRITERIA_PROMPT, build_criteria_input
        keys = ("problem", "missing")
        candidates = [i for i in issues
                      if (i["issuetype"] or "").lower() in ("story", "bug")]

    valid_keys = {i["key"] for i in candidates}
    findings, errors = [], []

    for batch in _batches(candidates, batch_size):
        user_content = builder(batch)
        data, err = model.call_model_json(model_cfg, prompt, user_content)
        if err:
            errors.append(err)
            continue
        for obj in data:
            key = obj.get("key", "").strip()
            # Guard against the model inventing keys not in this batch.
            if key not in valid_keys:
                continue
            findings.append({
                "key": key,
                "aspect": aspect,
                "problem": obj.get(keys[0], "").strip(),
                "detail": obj.get(keys[1], "").strip(),
            })
    return findings, errors


# ---------------------------------------------------------------------------
#  Output
# ---------------------------------------------------------------------------

def build_markdown(cfg, aspect, results, any_errors):
    today = dt.date.today().isoformat()
    nice = {"titles": "Title clarity", "criteria": "Acceptance criteria",
            "all": "Title clarity and acceptance criteria"}
    lines = [
        f"# Backlog Review — {nice.get(aspect, aspect)}",
        f"_Model-assisted review run on {today}. Every item below is a "
        "suggestion for your judgement, not a verdict — read the reasoning and "
        "keep or dismiss as you see fit._",
        "",
    ]

    if any_errors:
        lines.append("> ⚠️ Some batches could not be parsed from the model and "
                     "were skipped. Re-run to retry, or lower `review.batch_size` "
                     "in the config.")
        lines.append("")

    # Summary count per workstream.
    lines.append("## Summary")
    lines.append("")
    lines.append("| Workstream | Flagged for review |")
    lines.append("|-----------|-------------------:|")
    total = 0
    for ws, findings, _lookup in results:
        lines.append(f"| {ws['abbrev']} | {len(findings)} |")
        total += len(findings)
    lines.append(f"| **Total** | **{total}** |")
    lines.append("")

    label = {"titles": ("Why unclear", "Suggested rewrite"),
             "criteria": ("What's weak", "Criteria to add")}

    for ws, findings, lookup in results:
        lines.append(f"## {ws['name']} ({ws['abbrev']})")
        lines.append("")
        if not findings:
            lines.append("_Nothing flagged. Looks good._")
            lines.append("")
            continue
        for f in findings:
            iss = lookup.get(f["key"], {})
            col1, col2 = label.get(f["aspect"], ("Problem", "Suggestion"))
            title = sources.short(iss.get("summary", ""), 100)
            url = iss.get("url", "")
            lines.append(f"### {f['key']}: {title}")
            if url:
                lines.append(f"[Open in Jira]({url})")
            lines.append("")
            lines.append(f"- **{col1}:** {f['problem']}")
            lines.append(f"- **{col2}:** {f['detail']}")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
#  Entry point
# ---------------------------------------------------------------------------

def run(cfg, args):
    review_cfg = cfg.get("review", {})
    batch_size = review_cfg.get("batch_size", 8)
    aspect = getattr(args, "aspect", "all")
    aspects = ["titles", "criteria"] if aspect == "all" else [aspect]

    any_errors = False
    # We build one report per aspect so titles and criteria stay separate.
    for asp in aspects:
        results = []
        for ws in cfg["_workstreams"]:
            jql = workstreams.scope_jql(cfg, ws, "review")
            if not jql:
                print(f"Skipping {ws['abbrev']}: nothing in its review scope.")
                results.append((ws, [], {}))
                continue

            print(f"Reviewing {asp}: {ws['name']} ({ws['abbrev']}) ...")
            issues = sources.fetch_jira_detailed(cfg["jira"], jql)
            lookup = {i["key"]: i for i in issues}

            findings, errors = review_aspect(cfg["model"], asp, issues,
                                             batch_size)
            if errors:
                any_errors = True
                print(f"  ({len(errors)} batch(es) could not be parsed)")
            print(f"  {len(issues)} issues reviewed — "
                  f"{len(findings)} flagged.")
            results.append((ws, findings, lookup))

        report = build_markdown(cfg, asp, results, any_errors)
        out_path = f"review_{asp}_{dt.date.today().isoformat()}.md"
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"Done. {asp.capitalize()} review written to: {out_path}\n")
