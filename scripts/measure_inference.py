"""Count the model calls each pm-tools command actually makes.

Not a unit test, and not run by CI. This backs the measured table in
`docs/INFERENCE_PLAN.md`: it runs each command as a real subprocess against
the end-to-end fake Jira (which also serves `/v1/chat/completions`) and counts
the POSTs that reach the model endpoint. Counting `call_model` sites in the
source gives a different, wrong answer, because batching and issue-type
filtering decide the count at run time.

    python3 scripts/measure_inference.py
"""

import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tests"))

from fake_jira import FakeJira                              # noqa: E402
from test_cli_end_to_end import (CONFIG, PROJECT_COMPONENTS,  # noqa: E402
                                 backlog, pages)

PM = os.path.join(REPO, "pm.py")

SCENARIOS = [
    ("today", ["today"]),
    ("lint", ["lint"]),
    ("daily", ["daily"]),
    ("triage", ["triage"]),
    ("metrics", ["metrics"]),
    ("metrics --sprint", ["metrics", "--sprint"]),
    ("coverage", ["coverage"]),
    ("ready", ["ready"]),
    ("ready --deep", ["ready", "--deep"]),
    ("refine", ["refine"]),
    ("review all", ["review", "all"]),
    ("report", ["report"]),
    ("brief --debrief", ["brief", "--for", "board", "--debrief", "notes.txt"]),
    ("release-notes", ["release-notes", "--since", "2020-01-01"]),
]


def write_config(folder, url):
    path = os.path.join(folder, "config.yaml")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(CONFIG.format(url=url, membership="  epic_types: [Epic]",
                               sdx_component='"Secure Data Exchange"'))
    with open(os.path.join(folder, "notes.txt"), "w", encoding="utf-8") as fh:
        fh.write("Board asked about rotation timing.\nWe committed to October.\n")
    return path


def run(folder, config, *args):
    return subprocess.run(
        [sys.executable, PM, *args, "--config", config],
        cwd=folder, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=300)


def chat_calls(jira):
    return [c for c in jira.calls
            if c[0] == "POST" and c[1].startswith("/v1/chat/completions")]


def prompt_chars(call):
    body = call[2] or {}
    return sum(len(str(m.get("content") or ""))
               for m in body.get("messages") or [])


def main():
    rows = []
    with FakeJira(backlog(), PROJECT_COMPONENTS, pages()) as jira:
        for label, args in SCENARIOS:
            with tempfile.TemporaryDirectory() as folder:
                config = write_config(folder, jira.url)
                jira.calls.clear()
                proc = run(folder, config, *args)
                calls = chat_calls(jira)
                sizes = [prompt_chars(c) for c in calls]
                rows.append({
                    "command": f"pm {label}",
                    # lint, coverage and ready exit 1 when they find something.
                    "exit": proc.returncode,
                    "model_calls": len(calls),
                    "prompt_chars_total": sum(sizes),
                    "prompt_chars_max": max(sizes) if sizes else 0,
                })

        # Inbox is measured as a sequence: its cost scales with the number of
        # notes, and the second run shows that nothing is remembered.
        with tempfile.TemporaryDirectory() as folder:
            config = write_config(folder, jira.url)
            for n in range(5):
                run(folder, config, "note", f"captured thought number {n}")
            for label, args in (("inbox (5 notes)", ["inbox"]),
                                ("inbox (same 5, 2nd run)", ["inbox"]),
                                ("inbox create 1",
                                 ["inbox", "create", "1", "--dry-run"])):
                jira.calls.clear()
                proc = run(folder, config, *args)
                rows.append({"command": f"pm {label}",
                             "exit": proc.returncode,
                             "model_calls": len(chat_calls(jira)),
                             "prompt_chars_total": 0,
                             "prompt_chars_max": 0})

    width = max(len(r["command"]) for r in rows)
    print(f"{'command'.ljust(width)}  exit  model_calls  prompt_chars")
    print("-" * (width + 31))
    for row in rows:
        print(f"{row['command'].ljust(width)}  {row['exit']:>4}  "
              f"{row['model_calls']:>11}  {row['prompt_chars_total']:>12}")
    return rows


if __name__ == "__main__":
    data = main()
    out = os.environ.get("PM_MEASURE_JSON")
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        print(f"\nWrote {out}")
