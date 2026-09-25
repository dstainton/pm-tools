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

from core import output, sources, model, prompts, workstreams


# ---------------------------------------------------------------------------
#  Prompts — short, one example, JSON last. Written for Qwen3.8 Q3_K_M.
# ---------------------------------------------------------------------------
# A 3-bit Qwen3.8 follows a tiny schema and a worked example much more
# reliably than a long "be a meticulous PM" brief. Both prompts keep the
# phrase "JSON array" so tests and the fake model can recognise them.

TITLES_PROMPT = prompts.get(None, "review.titles")
CRITERIA_PROMPT = prompts.get(None, "review.criteria")
TITLES_USER_TAIL = prompts.get(None, "review.titles_tail")
CRITERIA_USER_TAIL = prompts.get(None, "review.criteria_tail")


# ---------------------------------------------------------------------------
#  Building the batches we send to the model
# ---------------------------------------------------------------------------

def _batches(items, size):
    size = max(1, int(size or 8))
    for i in range(0, len(items), size):
        yield items[i:i + size]


def candidates_for(aspect, issues, cfg=None):
    if aspect == "titles":
        return list(issues)
    story_types = ["story", "bug"]
    if cfg is not None:
        story_types = [t.lower() for t in (cfg.get("lint") or {}).get("story_types", story_types)]
    return [i for i in issues if (i.get("issuetype") or "").lower() in story_types]


def call_count(aspects, issues, batch_size):
    total = 0
    size = max(1, int(batch_size or 8))
    for aspect in aspects:
        count = len(candidates_for(aspect, issues))
        if count:
            total += (count + size - 1) // size
    return total


def build_titles_input(issues, cfg=None):
    lines = []
    for n, iss in enumerate(issues, 1):
        lines.append(f"{n}. {iss['key']}: {iss['summary']}")
    lines.append("")
    lines.append(prompts.get(cfg, "review.titles_tail"))
    return "\n".join(lines)


def build_criteria_input(issues, cfg=None):
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
    lines.append(prompts.get(cfg, "review.criteria_tail"))
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
#  Running one aspect (titles or criteria) over a workstream's issues
# ---------------------------------------------------------------------------

def review_aspect(model_cfg, aspect, issues, batch_size, cfg=None):
    """Return (findings, errors) for one aspect over one workstream."""
    if aspect == "titles":
        prompt = prompts.get(cfg, "review.titles")
        builder, keys = build_titles_input, ("problem", "suggestion")
        candidates = candidates_for(aspect, issues, cfg)
    else:  # criteria — only look at story-type issues
        prompt = prompts.get(cfg, "review.criteria")
        builder = build_criteria_input
        keys = ("problem", "missing")
        candidates = candidates_for(aspect, issues, cfg)

    valid_keys = {i["key"] for i in candidates}
    findings, errors = [], []

    for batch in _batches(candidates, batch_size):
        detail = model_cfg.get("_progress_detail")
        if detail:
            model.tick(model_cfg, detail)
        user_content = builder(batch, cfg)
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

def evaluate(cfg, aspects, batch_size=None):
    """Ask the model. Returns [(aspect, results, any_errors)]. Writes nothing."""
    if batch_size is None:
        batch_size = cfg.get("review", {}).get("batch_size", 8)
    produced = []
    for asp in aspects:
        any_errors = False
        prepared = []
        for ws in cfg["_workstreams"]:
            jql = workstreams.scope_jql(cfg, ws, "review")
            if not jql:
                print(f"Skipping {ws['abbrev']}: nothing in its review scope.")
                prepared.append((ws, []))
                continue
            print(f"Reviewing {asp}: {ws['name']} ({ws['abbrev']}) ...")
            prepared.append((ws, sources.fetch_jira_detailed(cfg["jira"], jql)))
        total = sum(call_count([asp], issues, batch_size)
                    for _ws, issues in prepared)
        model.announce(cfg["model"], total, f"pm review {asp}")
        results = []
        for ws, issues in prepared:
            lookup = {i["key"]: i for i in issues}
            cfg["model"]["_progress_detail"] = f"{ws['abbrev']}, {asp}"
            findings, errors = review_aspect(cfg["model"], asp, issues,
                                             batch_size, cfg)
            cfg["model"].pop("_progress_detail", None)
            if errors:
                any_errors = True
                print(f"  ({len(errors)} batch(es) could not be parsed)")
            print(f"  {len(issues)} issues reviewed — "
                  f"{len(findings)} flagged.")
            results.append((ws, findings, lookup))

        produced.append((asp, results, any_errors))
    return produced


def run(cfg, args):
    review_cfg = cfg.get("review", {})
    batch_size = review_cfg.get("batch_size", 8)
    aspect = getattr(args, "aspect", "all")
    aspects = ["titles", "criteria"] if aspect == "all" else [aspect]
    for asp, results, any_errors in evaluate(cfg, aspects, batch_size):
        report = build_markdown(cfg, asp, results, any_errors)
        out_path = output.place(
            cfg, f"review_{asp}_{dt.date.today().isoformat()}.md",
            getattr(args, "out", None))
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"Done. {asp.capitalize()} review written to: {out_path}\n")
