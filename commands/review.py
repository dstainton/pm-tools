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
#  Prompts — each asks for a JSON array so the output is machine-readable
# ---------------------------------------------------------------------------

TITLES_PROMPT = """You are a meticulous product manager reviewing Jira issue \
titles for clarity. A good title names the WHAT and, where useful, the WHO or \
WHERE, so a teammate understands the work without opening the ticket.

You will be given a numbered list of issues (key and title). Identify only the \
titles that are genuinely ambiguous, vague, or unclear — do NOT flag titles \
that are already clear. For each one you flag, return an object with:
  "key":      the issue key exactly as given
  "problem":  one short sentence on why the title is unclear
  "suggestion": a clearer rewritten title (keep it concise)

Return ONLY a JSON array of these objects, nothing else. If every title is \
clear, return an empty array: []
Do not invent issues or keys that are not in the list."""

CRITERIA_PROMPT = """You are a meticulous product manager reviewing whether \
user stories have complete, testable acceptance criteria (AC). Good AC state \
observable outcomes — what must be true for the story to be done — and cover \
the main success path plus obvious edge/error cases.

You will be given a numbered list of stories, each with its title and its \
current acceptance criteria / description text. Flag only stories whose AC are \
MISSING, vague, or clearly incomplete — do NOT flag stories whose AC are \
already solid. For each one you flag, return an object with:
  "key":     the issue key exactly as given
  "problem": one short sentence on what is missing or weak
  "missing": a short list (as a single string) of the specific criteria you \
would add

Return ONLY a JSON array of these objects, nothing else. If every story's AC \
are solid, return an empty array: []
Do not invent issues or keys that are not in the list."""


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
    return "\n".join(lines)


def build_criteria_input(issues):
    lines = []
    for n, iss in enumerate(issues, 1):
        ac = iss["acceptance_criteria"].strip()
        if not ac:
            # Fall back to the description so the model has something to judge.
            ac = sources.short(iss["description"], 500) or "(none provided)"
        lines.append(f"{n}. {iss['key']}: {iss['summary']}\n"
                     f"   Acceptance criteria / description: {ac}")
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
    batch_size = review_cfg.get("batch_size", 15)
    aspect = getattr(args, "aspect", "all")
    aspects = ["titles", "criteria"] if aspect == "all" else [aspect]

    any_errors = False
    # We build one report per aspect so titles and criteria stay separate.
    for asp in aspects:
        results = []
        for ws in cfg["_workstreams"]:
            jql = workstreams.resolve_jql(
                cfg["jira"], ws, "review_jql", fallback_field="lint_jql")
            if not jql:
                print(f"Skipping {ws['abbrev']}: no matching workstream epics/review scope.")
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
