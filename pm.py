#!/usr/bin/env python3
"""
Product Manager tools (`pm`).

One tool, several commands, all sharing a single config.yaml and your defined
workstreams. Runs entirely against your own Jira / Confluence / SharePoint and
your local model — nothing leaves your machine unless you run `pm mcp`.

Commands:
    pm init              Create a starter config at ~/.pm-tools/config.yaml.
    pm products          List, add, remove or check your products.
    pm workstreams       List, add, remove or check your workstreams.
    pm today             One bounded daily screen (the habit command).
    pm do N              Preview, then write, the action `pm today` numbered N.
    pm doctor            Verify config, Jira, statuses, fields, model, cache.
    pm report            Weekly state-of-product report (uses the local model).
                         role chooses pm, work, leadership, or partner.
                         --audience overrides that for one run. Comments since
                         that shape's last report.
    pm lint              Deterministic Product Backlog checks (no inference model used).
    pm triage            Queue of things waiting on a decision from you.
                         A mention quotes the comment.
    pm refine            BA queue: draft titles, criteria, estimates.
    pm review            Without --apply, the old model judgement. With --apply,
                         the refine worksheet. Deprecated.
    pm note              Capture a thought offline; file it later.
    pm coverage          Open issues no workstream claims, and unused components.
    pm inbox             List, edit, create or drop captured notes.
    pm metrics           Delivery numbers per product and workstream.
                         pm and work are the full tables. Leadership is the
                         headline. Partner metrics are refused.
    pm release-notes     Done issues since a date or in a fixVersion,
                         grouped by Epic. work lists items. Leadership lists
                         Epics. Partner lists visible work.
    pm brief             Meeting prep for one audience, or a debrief.
                         The first meeting uses role. A saved depth wins
                         after that. Prep quotes comments since you last met them.
    pm me                Your open work as it stands today, or a summary
                         over --sprint, --since, --days, or --summary.
                         Does not move the weekly-report memory.
    pm publish           Send a Markdown file to Confluence and/or Teams.
    pm schedule          Register read-only commands on a timer.
    pm warm              Fill the model cache ahead of time (read-only).
                         Order: review, page summaries, report, inbox.
    pm ready             Team working agreement: pass/fail per ticket.
    pm daily             Daily Scrum movement, comments from that window,
                         and work in progress (no inference model used).
    pm update            Upgrade pm-tools, then migrate the config with
                         the newly installed code. Adds settings it lacks
                         and lists what changed. Never replaces it.
    pm setup --review    Step through those new and changed settings.

Common options (every command except init and update):
  --config PATH        Path to the config file, before or after the command
                       name. Pass it once. If omitted, pm searches:
                       1) $PM_CONFIG, 2) ./config.yaml, 3) ~/.pm-tools/config.yaml,
                       4) the config.yaml shipped next to this file.
  --product NAMES      Only these products, by abbreviation or full name.
  --workstream NAMES   Only these workstreams, by abbreviation or full name.
                       Comma-separated, case-insensitive. e.g. --workstream SDX
                       or --workstream "Secure Data Exchange". Omit for all.
  --cached             Reuse a cached Jira fetch or model reply past its TTL.
  --refresh            Ignore cached Jira fetches and model replies.
  --out DIR            Write this run's files under DIR instead of
                       output.directory (default ~/.pm-tools/out).

Examples:
  pm init
  pm products add --name "Billing Platform" --abbrev BILL --project BILL
  pm workstreams add --name "Invoicing" --abbrev INV --components "Invoicing" \\
                     --product BILL
  pm workstreams check --show-jql
  pm today
  pm do 1 --dry-run
  pm doctor
  pm lint --product BILL
  pm lint --snooze APS-11 --until next-sprint --why "cosmetic"
  pm triage --apply 2 --yes
  pm refine -w SDX
  pm note "customer wants an SSO audit export"
  pm metrics --weeks 8
  pm metrics --sprint
  pm coverage
  pm release-notes --since 2026-08-01
  pm brief --for "Monthly portfolio review"
  pm report --publish --dry-run
  pm schedule add today --at 08:30
  pm schedule add warm --at 07:00
  pm ready --deep --workstream sdx,itk
  pm daily --days 3 --by workstream
"""

import argparse
import os
import sys

# Make sure the package folder is importable no matter where we're run from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import cache as fetch_cache                           # noqa: E402
from core import helptext as helptext_core                     # noqa: E402
from core import model as model_core                           # noqa: E402
from core import progress                                      # noqa: E402
from core.config import load_config, filter_workstreams        # noqa: E402
from core.paths import config_file                          # noqa: E402
from core.products import filter_by_product                    # noqa: E402
from commands import (report, lint, ready, init, setup, show,   # noqa: E402
                      daily, workstreams, products, doctor, today,
                      triage, refine, inbox, metrics, brief, publish,
                      schedule, update, coverage, release_notes, warm,
                      mcp_server, me)


def resolve_config_path(explicit):
    """Find the config file. Order of preference:

    1. --config given on the command line.
    2. $PM_CONFIG environment variable.
    3. config.yaml in the current working directory.
    4. ~/.pm-tools/config.yaml  (the usual home for a global CLI's config).
    5. config.yaml shipped next to this script (the bundled default).

    Returns the first that exists, or exits with guidance if none do.
    """
    candidates = []
    if explicit:
        candidates.append(explicit)
    if os.environ.get("PM_CONFIG"):
        candidates.append(os.environ["PM_CONFIG"])
    candidates.append(os.path.join(os.getcwd(), "config.yaml"))
    candidates.append(os.path.expanduser(config_file()))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "config.yaml"))

    for path in candidates:
        if path and os.path.exists(path):
            return path

    sys.exit(
        "No config file found. Get started with:\n"
        "  pm init                     # creates ~/.pm-tools/config.yaml\n\n"
        "Or point pm at an existing config by any of:\n"
        "  * running from a folder containing config.yaml\n"
        "  * setting PM_CONFIG=/path/to/config.yaml\n"
        "  * passing --config /path/to/config.yaml"
    )


def _prog_name():
    """`pm` or `pm-tools`, matching the command that was invoked."""
    name = os.path.splitext(os.path.basename(sys.argv[0]))[0]
    if name in ("pm", "pm-tools"):
        return name
    return "pm"


_SUBPARSERS = {}


class _HelpFlag(argparse.Action):
    """Print discovery help, or one command's complete page, then stop.

    Exits during parsing so a required argument does not block `pm do -h`.
    `--advanced` is the same complete page.
    """

    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings=option_strings, dest=dest, nargs=0, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        advanced = "--advanced" in sys.argv[1:]
        parts = parser.prog.split()
        name = parts[-1] if len(parts) >= 2 else ""
        if name and name != "help":
            text = helptext_core.command_page(parser, name, advanced=advanced)
        elif advanced:
            text = helptext_core.advanced_page(_SUBPARSERS)
        else:
            text = helptext_core.discovery_page(_optional_role(), _SUBPARSERS)
        sys.stdout.write(text)
        sys.stdout.flush()
        parser.exit(0)


def _optional_role(explicit=None):
    """The configured role when a settings file can be read. Never exits.

    Help does not need a valid config. A broken file still shows commands.
    """
    candidates = []
    if explicit:
        candidates.append(explicit)
    if os.environ.get("PM_CONFIG"):
        candidates.append(os.environ["PM_CONFIG"])
    candidates.append(os.path.join(os.getcwd(), "config.yaml"))
    candidates.append(os.path.expanduser(config_file()))
    for path in candidates:
        if not path or not os.path.exists(path):
            continue
        try:
            import yaml
            with open(path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except (OSError, yaml.YAMLError):
            return None
        if not isinstance(data, dict):
            return None
        role = data.get("role")
        role = role.strip() if isinstance(role, str) else ""
        return role or None
    return None


def selected_config(args):
    """The settings file from `--config`, before or after the command name."""
    local = getattr(args, "config", None)
    global_path = getattr(args, "config_global", None)
    if local and global_path:
        left = os.path.abspath(os.path.expanduser(local))
        right = os.path.abspath(os.path.expanduser(global_path))
        if left != right:
            sys.exit("Pass --config once.")
    return local or global_path


class _Parser(argparse.ArgumentParser):
    """Subcommands must not grow argparse's own -h. Ours prints the short page."""

    def __init__(self, *args, **kwargs):
        kwargs["add_help"] = False
        super().__init__(*args, **kwargs)


def build_parser():
    help_opts = argparse.ArgumentParser(add_help=False)
    help_opts.add_argument("-h", "--help", action=_HelpFlag, dest="help_requested",
                           help="Show what to type, or how to run this command")
    help_opts.add_argument("--advanced", action="store_true",
                           help="Same as the complete help page")

    parser = _Parser(
        prog=_prog_name(), description="pm-tools CLI", parents=[help_opts])
    parser.add_argument("--config", dest="config_global", default=None,
                        help="Settings file, before the command name")

    # Options shared by the config-driven subcommands (not init or update).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=None,
                        help="Path to the config file (default: auto-discover; "
                             "see --help notes)")
    common.add_argument("--product", "-p", default=None, metavar="NAMES",
                        help="Only these products, by abbreviation or full "
                             "name, comma-separated (e.g. IP or "
                             "\"Integration Platform\"). Default: all.")
    common.add_argument("--workstream", "-w", default=None, metavar="NAMES",
                        help="Only these workstreams, by abbreviation or full "
                             "name, comma-separated (e.g. SDX or "
                             "\"Secure Data Exchange\"). Default: all.")
    common.add_argument("--cached", action="store_true",
                        help="Reuse cached Jira fetches and model replies "
                             "even if they are stale")
    common.add_argument("--refresh", action="store_true",
                        help="Ignore cached Jira fetches and model replies")
    common.add_argument("--plain", action="store_true",
                        help="No colour, glyphs, or clickable links; a link "
                             "shows its address. One labelled fact per line. "
                             "NO_COLOR does this too.")
    common.add_argument("--out", default=None, metavar="DIR",
                        help="Write this run's files under DIR instead of "
                             "output.directory")

    write_opts = argparse.ArgumentParser(add_help=False)
    write_opts.add_argument("--yes", "-y", action="store_true",
                            help="Confirm the Jira write without a prompt")
    write_opts.add_argument("--dry-run", action="store_true",
                            help="Preview the Jira write and stop")

    sub = parser.add_subparsers(
        dest="command", required=False,
        metavar="{today,do,note,daily,report,brief,doctor,...}")

    # init is special: no config needed (it creates one), so no `common`.
    p_init = sub.add_parser("init", parents=[help_opts],
                            help="Create a starter config at ~/.pm-tools/config.yaml")
    p_init.add_argument("--force", action="store_true",
                        help="Overwrite an existing config")
    p_init.add_argument("--path", default=None,
                        help="Write to a specific path instead of ~/.pm-tools")
    p_init.set_defaults(func=init.run, needs_config=False)

    p_prod = sub.add_parser("products", parents=[help_opts, common],
                            help="List, add, remove or check your products")
    p_prod.add_argument("action", nargs="?", default="list",
                        choices=["list", "add", "remove", "check"],
                        help="What to do (default: list)")
    p_prod.add_argument("target", nargs="?",
                        help="The product abbrev, for `remove`")
    p_prod.add_argument("--name", help="Full product name, for `add`")
    p_prod.add_argument("--abbrev", help="Short name, for `add` / `remove`")
    p_prod.add_argument("--project",
                        help="Jira project this product lives in")
    p_prod.add_argument("--goal",
                        help="Product Goal sentence, for `add`")
    p_prod.add_argument("--confluence-space",
                        help="Confluence space key. On its own, the whole space")
    p_prod.add_argument("--confluence-page",
                        help="Folder or page title in one shared space, for `add`")
    p_prod.add_argument("--confluence-page-id",
                        help="That folder's id, when the title is not unique")
    p_prod.add_argument("--show-jql", action="store_true",
                        help="With `check`, print the JQL pm generates")
    p_prod.set_defaults(func=products.run, needs_config=True)

    p_ws = sub.add_parser("workstreams", parents=[help_opts, common],
                          help="List, add, remove or check your workstreams")
    p_ws.add_argument("action", nargs="?", default="list",
                      choices=["list", "add", "remove", "check"],
                      help="What to do (default: list)")
    p_ws.add_argument("target", nargs="?",
                      help="The workstream abbrev, for `remove`")
    p_ws.add_argument("--name", help="Full workstream name, for `add`")
    p_ws.add_argument("--abbrev", help="Short name, for `add` / `remove`")
    p_ws.add_argument("--components", metavar="NAMES",
                      help="Jira Component name(s) that identify the "
                           "workstream, comma-separated")
    p_ws.add_argument("--project",
                      help="Jira project, if it differs from jira.project")
    p_ws.add_argument("--confluence-space",
                      help="Confluence space key. With no page, every changed "
                           "page in that space")
    p_ws.add_argument("--confluence-page",
                      help="Folder or page title in one shared space, for `add`")
    p_ws.add_argument("--confluence-page-id",
                      help="That folder's id, when the title is not unique")
    p_ws.add_argument("--confluence-labels", metavar="LABELS",
                      help="Confluence labels to gather, comma-separated")
    p_ws.add_argument("--sharepoint-query",
                      help="Search term for its SharePoint documents")
    p_ws.add_argument("--show-jql", action="store_true",
                      help="With `check`, print the JQL pm generates")
    p_ws.set_defaults(func=workstreams.run, needs_config=True)

    p_today = sub.add_parser("today", parents=[help_opts, common],
                             help="Bounded daily screen across the portfolio")
    p_today.add_argument("--all", action="store_true",
                         help="Include triage kinds (mentions, new bugs) "
                              "in this same numbered list")
    p_today.add_argument("--json", action="store_true",
                         help="Print the numbered actions as JSON")
    p_today.set_defaults(func=today.run_today, needs_config=True)

    p_do = sub.add_parser("do", parents=[help_opts, common, write_opts],
                          help="Preview, then write, the numbered action "
                               "from `pm today`")
    p_do.add_argument("number", type=int, help="The number from the last "
                      "`pm today` (e.g. 1)")
    p_do.set_defaults(func=today.run_do, needs_config=True)

    p_doctor = sub.add_parser("doctor", parents=[help_opts, common],
                              help="Verify config, Jira, statuses, fields, model, cache")
    p_doctor.add_argument("--discover-fields", action="store_true",
                          help="List custom-field IDs that look like story "
                               "points, start date, or acceptance criteria")
    p_doctor.add_argument("--yes", "-y", action="store_true",
                          help="With --discover-fields, write blank field IDs")
    p_doctor.add_argument("--prompts", nargs="?", const="all", metavar="ID",
                          help="Show where each prompt comes from, or one prompt's text")
    p_doctor.add_argument("--queries", nargs="?", const="all", metavar="ID",
                          help="Show each query and check it against Jira")
    p_doctor.set_defaults(func=doctor.run, needs_config=True)

    p_setup = sub.add_parser(
        "setup", parents=[help_opts],
        help="Fill in the config one step at a time",
        description="Fill in the config one step at a time. "
                    "--section model lists local servers and can install "
                    "Ollama or Lemonade. --section confluence records one "
                    "shared space, the team page, or one folder. "
                    "--section registers adds one register. --review steps "
                    "through settings an update added or changed.")
    p_setup.add_argument("--path", default=None, help="Config file to edit")
    p_setup.add_argument("--section", default=None,
                         choices=["jira", "model", "workstreams", "confluence",
                                  "registers"],
                         help="Fix one section")
    p_setup.add_argument("--site", default=None, help="Jira site, e.g. dpdd")
    p_setup.add_argument("--email", default=None, help="Atlassian email")
    p_setup.add_argument("--token-env", default=None,
                         help="Write the token as ${ENV:NAME}")
    p_setup.add_argument("--token", default=None,
                         help="Paste a token (prefer --token-env)")
    p_setup.add_argument("--project", default=None, help="Jira project key")
    p_setup.add_argument(
        "--model-endpoint", default=None,
        help="OpenAI-compatible base or chat URL, written when blank "
             "or still the shipped default")
    p_setup.add_argument(
        "--model-name", default=None,
        help="Model id, written when blank or still qwen3:4b")
    p_setup.add_argument(
        "--model-api-key", default=None,
        help="Bearer token for the local server, written when blank")
    p_setup.add_argument(
        "--model-api-key-env", default=None,
        help="Write the model API key as ${ENV:NAME}")
    p_setup.add_argument("--confluence-space", default=None,
                         help="Shared Confluence space key or name, written when blank")
    p_setup.add_argument("--confluence-team-page", "--confluence-root",
                         dest="confluence_team_page", default=None,
                         help="Your team page title in that space, written when blank")
    p_setup.add_argument("--workstream", default=None,
                         help="With --section confluence, the workstream folder to set")
    p_setup.add_argument("--product", default=None,
                         help="With --section confluence, the product folder to set. "
                              "With --section registers, the product the register belongs to")
    p_setup.add_argument("--confluence-page", default=None,
                         help="Folder title to write on that product or workstream")
    p_setup.add_argument("--drop-content-type", default=None,
                         help="Remove one rejected type from confluence.content_types")
    p_setup.add_argument("--register-type", default=None,
                         choices=["decision", "risk", "adr"],
                         help="Register type to add or update")
    p_setup.add_argument("--register-name", default=None,
                         help="Register name to add or update")
    p_setup.add_argument("--register-title", default=None,
                         help="Summary page title, when page id is not set")
    p_setup.add_argument("--under", default=None,
                         help="Page the register title sits under")
    p_setup.add_argument("--page-id", default=None,
                         help="Confluence page id of the register summary")
    p_setup.add_argument("--review", action="store_true",
                         help="Step through new settings, changed defaults, "
                              "and old names in a config you already have")
    p_setup.add_argument("--all", action="store_true",
                         help="With --review, step through every setting")
    p_setup.add_argument("--yes", action="store_true",
                         help="Write the flags and do not prompt or install")
    p_setup.set_defaults(func=setup.run, needs_config=False)

    p_show = sub.add_parser("show", parents=[help_opts, common],
                            help="One issue: status, assignee, dates, link")
    p_show.add_argument("key", help="Issue key, e.g. APS-30")
    p_show.add_argument("--json", action="store_true")
    p_show.set_defaults(func=show.run, needs_config=True)

    p_mcp = sub.add_parser(
        "mcp", parents=[help_opts, common],
        help="stdio MCP server for read-only commands (off by default)")
    p_mcp.add_argument("--yes-i-understand", action="store_true",
                       help="Start the server. Tool results leave the machine "
                            "when the client is Copilot.")
    p_mcp.set_defaults(func=mcp_server.run, needs_config=True)

    p_report = sub.add_parser("report", parents=[help_opts, common, write_opts],
                              help="Weekly state-of-product report, with "
                                   "comments since the last report")
    p_report.add_argument("--publish", action="store_true",
                          help="Also send the report to Confluence and/or Teams")
    p_report.add_argument("--since", metavar="YYYY-MM-DD",
                          help="Start of the window. Does not move last-report memory.")
    p_report.add_argument("--sprint", nargs="?", const="open", default=None,
                          metavar="SPRINT",
                          help="This Sprint (open), a number (138), or last")
    p_report.add_argument("--audience",
                          choices=["pm", "work", "leadership", "partner",
                                   "analyst", "developer", "service-designer"],
                          help="Who the report is for (default: role, else "
                               "audiences.default, else pm). work is the "
                               "generic internal report.")
    p_report.add_argument("--sources", choices=["compact", "full"], default=None,
                          help="compact keeps inline citations (default). "
                               "full adds the source tables.")
    p_report.add_argument("--json", action="store_true",
                          help="Also write the gathered report as JSON")
    p_report.set_defaults(func=report.run, needs_config=True)

    p_lint = sub.add_parser("lint", parents=[help_opts, common, write_opts],
                            help="Deterministic backlog quality checks")
    p_lint.add_argument("--json", action="store_true",
                        help="Write findings as JSON instead of Markdown")
    p_lint.add_argument("--severity", choices=["error", "warn", "review"],
                        help="Only show findings at or above this severity")
    p_lint.add_argument("--fail-on", choices=["error", "warn", "review"],
                        help="Exit non-zero if a finding is at or above "
                             "this severity")
    p_lint.add_argument("--snooze", metavar="KEY",
                        help="Hide findings on KEY until --until")
    p_lint.add_argument("--accept", metavar="KEY",
                        help="Accept findings on KEY (hidden unless --all)")
    p_lint.add_argument("--assign", metavar="KEY",
                        help="Hand KEY to --to <person> (and set Jira assignee)")
    p_lint.add_argument("--until",
                        help="With --snooze: YYYY-MM-DD, 14d, 2w, or next-sprint")
    p_lint.add_argument("--why",
                        help="Reason that sticks with the decision")
    p_lint.add_argument("--to",
                        help="Person to assign the finding to (a name, not a role)")
    p_lint.add_argument("--rule",
                        help="Limit the decision to one lint rule (default: *)")
    p_lint.add_argument("--all", action="store_true",
                        help="Show snoozed, accepted and assigned findings too")
    p_lint.set_defaults(func=lint.run, needs_config=True)

    p_triage = sub.add_parser("triage", parents=[help_opts, common, write_opts],
                              help="Queue of things waiting on a decision from you")
    p_triage.add_argument("--apply", type=int, metavar="N",
                          help="Do the numbered triage action")
    p_triage.set_defaults(func=triage.run, needs_config=True)

    p_refine = sub.add_parser("refine", parents=[help_opts, common, write_opts],
                              help="Draft titles, criteria and estimates for "
                                   "items that fail the ready agreement")
    p_refine.add_argument("--apply", action="store_true",
                          help="Write the kept drafts from the worksheet")
    p_refine.set_defaults(func=refine.run, needs_config=True)

    p_review = sub.add_parser("review", parents=[help_opts, common, write_opts],
                              help="Without --apply, the old model judgement; "
                                   "with --apply, a refine worksheet "
                                   "(deprecated)")
    p_review.add_argument("aspect", nargs="?", default="all",
                          choices=["titles", "criteria", "all"],
                          help="What to review (default: all)")
    p_review.add_argument("--apply", action="store_true",
                          help="Write the kept drafts from the worksheet")
    p_review.set_defaults(func=refine.run, needs_config=True)

    p_note = sub.add_parser("note", parents=[help_opts, common],
                            help="Capture a thought offline")
    p_note.add_argument("text", nargs="*",
                        help="The note (quote it if it has spaces)")
    p_note.set_defaults(func=inbox.run_note, needs_config=True)

    p_inbox = sub.add_parser(
        "inbox", parents=[help_opts, common, write_opts],
        help="List, edit, create or drop captured notes",
        description="List, edit, create or drop captured notes. "
                    "edit writes inbox.json only.")
    p_inbox.add_argument("action", nargs="?", default="list",
                         choices=["list", "edit", "create", "drop"],
                         help="What to do (default: list)")
    p_inbox.add_argument("target", nargs="?", type=int,
                         help="Note number, for edit / create / drop")
    p_inbox.add_argument("--title", help="Title to store or to file")
    p_inbox.add_argument("--criteria",
                         help="Acceptance criteria to store or to file")
    p_inbox.add_argument("--issuetype", help="Override the suggested type")
    p_inbox.set_defaults(func=inbox.run_inbox, needs_config=True)

    p_metrics = sub.add_parser(
        "metrics", parents=[help_opts, common],
        help="Delivery metrics per product and workstream",
        description="Delivery metrics per product and workstream. "
                    "--sprint reports the open sprint.")
    p_metrics.add_argument("--weeks", type=int, default=None,
                           help="How many weeks back (default: metrics.weeks or 8)")
    p_metrics.add_argument("--sprint", nargs="?", const="open", default=None,
                           metavar="SPRINT",
                           help="Open sprint, a sprint number, or last")
    p_metrics.add_argument("--audience",
                           choices=["pm", "work", "leadership", "partner",
                                    "analyst", "developer", "service-designer"],
                           help="pm, work, analyst, developer, and "
                                "service-designer show the full tables; "
                                "leadership a headline; partner is refused")
    p_metrics.add_argument("--json", action="store_true",
                           help="Write the numbers as JSON")
    p_metrics.set_defaults(func=metrics.run, needs_config=True)

    p_brief = sub.add_parser("brief", parents=[help_opts, common, write_opts],
                             help="Meeting prep for one audience, or a debrief. "
                                  "Prep includes comments since you last met them")
    p_brief.add_argument("--for", dest="for_audience", metavar="AUDIENCE",
                         help="Who the page is for (memory is per audience)")
    p_brief.add_argument("--debrief", metavar="FILE",
                         help="Turn meeting notes into decisions and actions")
    p_brief.add_argument("--apply", action="store_true",
                         help="With --debrief, create the action tickets")
    p_brief.add_argument("--publish", action="store_true",
                         help="Also send the brief to Confluence and/or Teams")
    p_brief.add_argument("--audience",
                         choices=["pm", "work", "leadership", "partner",
                                  "analyst", "developer", "service-designer"],
                         help="How deep the prep goes (default: the level saved "
                              "for this meeting, else role)")
    p_brief.add_argument("--since", metavar="YYYY-MM-DD",
                         help="Start of the window. Does not move last-met memory.")
    p_brief.add_argument("--sprint", nargs="?", const="open", default=None,
                         help="This Sprint (open), a number (138), or last")
    p_brief.set_defaults(func=brief.run, needs_config=True)

    p_publish = sub.add_parser("publish", parents=[help_opts, common, write_opts],
                               help="Send a Markdown file to Confluence and/or Teams")
    p_publish.add_argument("file", nargs="?",
                           help="The Markdown file to send")
    p_publish.set_defaults(func=publish.run, needs_config=True)

    p_sched = sub.add_parser("schedule", parents=[help_opts, common],
                             help="Register read-only commands on a timer")
    p_sched.add_argument("action", nargs="?", default="list",
                         choices=["list", "add", "remove"],
                         help="What to do (default: list)")
    p_sched.add_argument("target", nargs="?",
                         help="The command to add or the job to remove")
    p_sched.add_argument("--at", metavar="HH:MM",
                         help="Weekday time, e.g. 08:30")
    p_sched.add_argument("--weekly", metavar="DAY@HH:MM",
                         help="One day a week, e.g. fri@16:00")
    p_sched.add_argument("--audience", choices=["pm", "work", "leadership", "partner"],
                         help="With add report, the audience. Partner is refused.")
    p_sched.add_argument("--for", dest="for_audience",
                         help="With `add brief`, the audience name")
    p_sched.add_argument("--fail-on", choices=["error", "warn", "review"],
                         help="With `add lint`, pass --fail-on through")
    p_sched.add_argument("--fail-under", type=float, default=None,
                         metavar="N",
                         help="With `add ready`, pass --fail-under through")
    p_sched.set_defaults(func=schedule.run, needs_config=True)

    p_warm = sub.add_parser(
        "warm", parents=[help_opts, common],
        help="Fill the model cache ahead of time (read-only)",
        description="Fill the model cache so a later command only catches up. "
                    "Read-only: no Jira writes, no report. With no flag, warms "
                    "review, page summaries, the report, then the inbox. "
                    "Review also covers ready --deep.")
    p_warm.add_argument("--review", action="store_true",
                        help="Warm pm review (and pm ready --deep)")
    p_warm.add_argument("--report", action="store_true",
                        help="Warm pm report")
    p_warm.add_argument("--deep", action="store_true",
                        help="Same model work as --review")
    p_warm.add_argument("--audience",
                        help="Comma-separated levels to warm (default: audiences.warm)")
    p_warm.add_argument("--pages", action="store_true",
                        help="Summarise Confluence pages changed in the report window")
    p_warm.add_argument("--inbox", action="store_true",
                        help="Warm suggestions for notes already in the inbox")
    p_warm.set_defaults(func=warm.run, needs_config=True)

    p_ready = sub.add_parser(
        "ready", parents=[help_opts, common],
        help="Team working agreement (pass/fail)",
        description="Team working agreement: pass/fail per ticket. "
                    "too-big-for-a-sprint blocks only when it is listed.")
    p_ready.add_argument("--plan", action="store_true",
                         help="Planning view: ready work, refinement gaps, "
                              "decisions, dependencies, and recent throughput")
    p_ready.add_argument("--deep", action="store_true",
                         help="Also run the model reviews as blocking checks")
    p_ready.add_argument("--fail-under", type=float, default=None,
                         metavar="N",
                         help="Exit non-zero when fewer than N percent of "
                              "items are ready")
    p_ready.set_defaults(func=ready.run, needs_config=True)

    p_daily = sub.add_parser("daily", parents=[help_opts, common],
                             help="Daily Scrum movement, comments from that "
                                  "window, and work in progress")
    p_daily.add_argument("--days", type=int, default=1,
                         help="How many days back to count as 'moved' "
                              "(default: 1)")
    p_daily.add_argument("--by", choices=["assignee", "workstream"],
                         default="assignee",
                         help="Group in-progress work by assignee (default) "
                              "or by workstream")
    p_daily.add_argument("--print", action="store_true",
                         help="Also echo the snapshot to the terminal")
    p_daily.set_defaults(func=daily.run, needs_config=True)

    p_me = sub.add_parser(
        "me", parents=[help_opts, common],
        help="Your open work as it stands, or a summary over a window",
        description="Your open work as it stands today. "
                    "--sprint, --since, --days, or --summary is that window. "
                    "This does not move the weekly report memory.")
    p_me.add_argument("--sprint", nargs="?", const="open", default=None,
                      help="This Sprint (open), a number (138), or last")
    p_me.add_argument("--since", metavar="YYYY-MM-DD",
                      help="Start of the window")
    p_me.add_argument("--days", type=int, default=None,
                      help="How many days back")
    p_me.add_argument("--summary", action="store_true",
                      help="Use me.summary (sprint, or a number of days)")
    p_me.add_argument("--who", default=None, metavar="NAME",
                      help="Someone else's work. Only when the report shape is pm.")
    p_me.add_argument("--audience", choices=["pm", "work", "leadership", "partner"],
                      help="With --who, confirms the shape is pm")
    p_me.set_defaults(func=me.run, needs_config=True)

    p_cover = sub.add_parser(
        "coverage", parents=[help_opts, common],
        help="Open issues no workstream claims, overlaps, and unused "
             "components",
        description="Open issues no workstream claims, issues two or more "
                    "workstreams claim, and components no workstream names. "
                    "Exits 1 when unclaimed work exists.")
    p_cover.set_defaults(func=coverage.run, needs_config=True)

    p_notes = sub.add_parser(
        "release-notes", parents=[help_opts, common],
        help="Done issues since a date or in a fixVersion",
        description="Done issues since a date or in a fixVersion, grouped by "
                    "product and workstream. Comments from that window sit "
                    "on the bullets. The model drafts prose when it is up "
                    "and does not choose the issues.")
    p_notes.add_argument("--since", metavar="YYYY-MM-DD",
                         help="Include issues resolved on or after this date")
    p_notes.add_argument("--version", metavar="NAME",
                         help="Include issues in this fixVersion")
    p_notes.add_argument("--audience", choices=["pm", "work", "leadership", "partner"],
                         help="pm and work list items, leadership lists Epics, "
                              "partner lists visible work")
    p_notes.set_defaults(func=release_notes.run, needs_config=True)

    p_update = sub.add_parser(
        "update", parents=[help_opts],
        help="Upgrade pm-tools and migrate the config")
    p_update.add_argument("--config", default=None,
                          help="Config file to migrate (default: ~/.pm-tools/config.yaml)")
    p_update.add_argument("--code-only", action="store_true",
                          help="Upgrade the program and leave the config untouched")
    p_update.add_argument("--config-only", action="store_true",
                          help="Migrate the config and leave the program as it is")
    p_update.add_argument("--dry-run", action="store_true",
                          help="Show what would change and write nothing")
    p_update.set_defaults(func=update.run, needs_config=False)

    p_help = sub.add_parser(
        "help", parents=[help_opts],
        help="What to type, every command, or one command's syntax")
    p_help.add_argument("topic", nargs="?", default=None,
                        help="all, roles, or a command name")
    p_help.set_defaults(needs_config=False)

    global _SUBPARSERS
    _SUBPARSERS = {}
    for action in sub._choices_actions:
        child = sub.choices.get(action.dest)
        if child is None:
            continue
        child._pm_blurb = action.help or ""
        _SUBPARSERS[action.dest] = child
    parser._pm_subs = _SUBPARSERS
    return parser


def configure_stdio():
    """Print UTF-8, including on a Windows console that is still cp1252.

    An arrow or a warning mark would otherwise abort the command mid-line.
    """
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except (AttributeError, OSError):
            pass
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def main():
    configure_stdio()
    parser = build_parser()
    args = parser.parse_args()

    command = getattr(args, "command", None)
    advanced = "--advanced" in sys.argv[1:]
    if command in (None, "help"):
        topic = getattr(args, "topic", None) if command == "help" else None
        role = _optional_role(getattr(args, "config_global", None))
        if advanced or topic == "all":
            page = helptext_core.all_page(parser._pm_subs)
        elif topic == "roles":
            page = helptext_core.roles_page()
        elif topic:
            child = parser._pm_subs.get(topic)
            if child is None:
                sys.exit(f"Unknown command {topic}. Run: pm help all")
            page = helptext_core.command_page(child, topic)
        else:
            page = helptext_core.discovery_page(role, parser._pm_subs)
        print(page, end="")
        return
    if advanced:
        sys.exit(f"pm {command} -h --advanced lists every flag.")

    chosen = selected_config(args)
    if command == "update":
        args.config = chosen

    # init runs before any config discovery — it's what creates the config.
    if not getattr(args, "needs_config", True):
        args.func(args)
        return

    config_path = resolve_config_path(chosen)
    cfg = load_config(config_path)
    # `pm workstreams add/remove` edits this file, and every command mentions it
    # when something is misconfigured, so keep the resolved path to hand.
    cfg["_config_path"] = config_path

    if getattr(args, "cached", False) and getattr(args, "refresh", False):
        sys.exit("Choose one of --cached or --refresh, not both.")
    cache_mode = "default"
    if getattr(args, "refresh", False):
        cache_mode = "refresh"
    elif getattr(args, "cached", False):
        cache_mode = "cached"
    fetch_cache.attach(cfg, mode=cache_mode)
    model_core.attach(cfg, mode=cache_mode)

    # Narrow the workstreams once, centrally, so every command respects
    # --product and --workstream without needing its own logic. Commands
    # read the result from cfg['_workstreams'].
    selected = filter_workstreams(cfg, getattr(args, "workstream", None))
    product_sel = getattr(args, "product", None)
    action = getattr(args, "action", None)
    skip_product_filter = (
        args.command in ("do", "note", "publish", "schedule")
        or (args.command in ("workstreams", "products")
            and action in ("add", "remove"))
        or (args.command == "inbox" and action in ("edit", "create", "drop"))
        or (args.command == "brief" and getattr(args, "debrief", None))
        or (args.command == "lint"
            and (getattr(args, "snooze", None)
                 or getattr(args, "accept", None)
                 or getattr(args, "assign", None)))
    )
    if product_sel and not skip_product_filter:
        selected = filter_by_product(cfg, selected, product_sel)
    cfg["_workstreams"] = selected

    scope_bits = []
    if product_sel and not skip_product_filter:
        names = [s.strip() for s in product_sel.split(",") if s.strip()]
        scope_bits.append("product " + ", ".join(names))
    if getattr(args, "workstream", None):
        scope_bits.append(", ".join(w["abbrev"] for w in selected))
    if scope_bits:
        print(f"(scope: {' / '.join(scope_bits)})\n")

    with progress.running():
        args.func(cfg, args)


if __name__ == "__main__":
    main()
