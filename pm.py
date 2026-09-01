#!/usr/bin/env python3
"""
Product Manager Helper CLI — `pm`.

One tool, several commands, all sharing a single config.yaml and your defined
workstreams. Runs entirely against your own Jira / Confluence / SharePoint and
your local model — nothing leaves your machine.

Commands:
  pm init              Create a starter config at ~/.pm/config.yaml.
  pm report            Weekly state-of-product report (uses the local model).
  pm lint              Deterministic backlog quality checks (no model).
  pm review            Model-based judgement checks (title clarity, AC quality).
  pm ready             Definition-of-Ready gate: pass/fail per ticket.
  pm standup           Daily movement + work-in-progress snapshot (no model).

Common options (work on every command except init):
  --config PATH        Path to the config file. If omitted, pm searches:
                       1) $PM_CONFIG, 2) ./config.yaml, 3) ~/.pm/config.yaml,
                       4) the config.yaml shipped next to this file.
  --workstream NAMES   Only run for these workstream(s), by abbreviation.
                       Comma-separated, case-insensitive. e.g. --workstream SDX
                       or --workstream sdx,itk. Omit to run all of them.

Examples:
  pm init
  pm report
  pm lint --severity error
  pm review titles --workstream SDX
  pm ready --deep --workstream sdx,itk
  pm standup --days 3 --by workstream
"""

import argparse
import os
import sys

# Make sure the package folder is importable no matter where we're run from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import load_config, filter_workstreams        # noqa: E402
from commands import (report, lint, review, ready, init,        # noqa: E402
                      standup)


def resolve_config_path(explicit):
    """Find the config file. Order of preference:

    1. --config given on the command line.
    2. $PM_CONFIG environment variable.
    3. config.yaml in the current working directory.
    4. ~/.pm/config.yaml  (the usual home for a global CLI's config).
    5. config.yaml shipped next to this script (the bundled default).

    Returns the first that exists, or exits with guidance if none do.
    """
    candidates = []
    if explicit:
        candidates.append(explicit)
    if os.environ.get("PM_CONFIG"):
        candidates.append(os.environ["PM_CONFIG"])
    candidates.append(os.path.join(os.getcwd(), "config.yaml"))
    candidates.append(os.path.expanduser("~/.pm/config.yaml"))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "config.yaml"))

    for path in candidates:
        if path and os.path.exists(path):
            return path

    sys.exit(
        "No config file found. Get started with:\n"
        "  pm init                     # creates ~/.pm/config.yaml\n\n"
        "Or point pm at an existing config by any of:\n"
        "  * running from a folder containing config.yaml\n"
        "  * setting PM_CONFIG=/path/to/config.yaml\n"
        "  * passing --config /path/to/config.yaml"
    )


def build_parser():
    parser = argparse.ArgumentParser(
        prog="pm", description="Product Manager Helper CLI")

    # Options shared by the config-driven subcommands (everything but init).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=None,
                        help="Path to the config file (default: auto-discover; "
                             "see --help notes)")
    common.add_argument("--workstream", "-w", default=None, metavar="NAMES",
                        help="Only run for these workstream abbrev(s), "
                             "comma-separated (e.g. SDX or sdx,itk). "
                             "Default: all workstreams.")

    sub = parser.add_subparsers(dest="command", required=True,
                                metavar="{init,report,lint,review,ready,standup}")

    # init is special: no config needed (it creates one), so no `common`.
    p_init = sub.add_parser("init",
                            help="Create a starter config at ~/.pm/config.yaml")
    p_init.add_argument("--force", action="store_true",
                        help="Overwrite an existing config")
    p_init.add_argument("--path", default=None,
                        help="Write to a specific path instead of ~/.pm")
    p_init.set_defaults(func=init.run, needs_config=False)

    p_report = sub.add_parser("report", parents=[common],
                              help="Weekly state-of-product report")
    p_report.set_defaults(func=report.run, needs_config=True)

    p_lint = sub.add_parser("lint", parents=[common],
                            help="Deterministic backlog quality checks")
    p_lint.add_argument("--json", action="store_true",
                        help="Write findings as JSON instead of Markdown")
    p_lint.add_argument("--severity", choices=["error", "warn", "review"],
                        help="Only show findings at or above this severity")
    p_lint.set_defaults(func=lint.run, needs_config=True)

    p_review = sub.add_parser("review", parents=[common],
                              help="Model-based judgement checks")
    p_review.add_argument("aspect", nargs="?", default="all",
                          choices=["titles", "criteria", "all"],
                          help="What to review (default: all)")
    p_review.set_defaults(func=review.run, needs_config=True)

    p_ready = sub.add_parser("ready", parents=[common],
                             help="Definition-of-Ready gate (pass/fail)")
    p_ready.add_argument("--deep", action="store_true",
                         help="Also run the model reviews as blocking checks")
    p_ready.set_defaults(func=ready.run, needs_config=True)

    p_standup = sub.add_parser("standup", parents=[common],
                               help="Daily movement + work-in-progress snapshot")
    p_standup.add_argument("--days", type=int, default=1,
                           help="How many days back to count as 'moved' "
                                "(default: 1)")
    p_standup.add_argument("--by", choices=["assignee", "workstream"],
                           default="assignee",
                           help="Group in-progress work by owner (default) "
                                "or by workstream")
    p_standup.add_argument("--print", action="store_true",
                           help="Also echo the snapshot to the terminal")
    p_standup.set_defaults(func=standup.run, needs_config=True)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    # init runs before any config discovery — it's what creates the config.
    if not getattr(args, "needs_config", True):
        args.func(args)
        return

    config_path = resolve_config_path(getattr(args, "config", None))
    cfg = load_config(config_path)

    # Narrow the workstreams once, centrally, so every command respects
    # --workstream without needing its own logic. Commands read the result
    # from cfg['_workstreams'].
    selected = filter_workstreams(cfg, getattr(args, "workstream", None))
    cfg["_workstreams"] = selected
    if getattr(args, "workstream", None):
        names = ", ".join(w["abbrev"] for w in selected)
        print(f"(scope: {names})\n")

    args.func(cfg, args)


if __name__ == "__main__":
    main()
