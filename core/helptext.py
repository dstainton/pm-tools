"""Role-aware discovery, and a complete page for each command.

`pm` and `pm help` answer what to type. `pm <command> -h` answers how to
type it, including positionals, choices, and every flag. `--advanced` is
the same complete page.
"""

import argparse


# Product judgement argparse cannot know. Syntax stays on the parser.
CATALOGUE = {
    "today": {
        "summary": "Morning screen: Sprint Goal and a numbered list.",
        "examples": ("pm today", "pm today --all"),
        "related": ("do", "me", "daily"),
        "common": ("product", "workstream", "all"),
    },
    "do": {
        "summary": "Carry out item N from that list, after a preview.",
        "examples": ("pm do 2",),
        "related": ("today",),
        "common": ("yes", "dry_run"),
    },
    "note": {
        "summary": "Save a thought locally. Nothing is sent to Jira.",
        "examples": ('pm note "customer wants an SSO audit export"',),
        "related": ("inbox",),
        "common": ("product", "workstream"),
    },
    "inbox": {
        "summary": "List notes, edit one, file it in Jira, or drop it.",
        "examples": ("pm inbox", "pm inbox edit 1 --title \"Export the audit log\""),
        "related": ("note",),
        "common": ("criteria",),
    },
    "show": {
        "summary": "One issue: status, assignee, dates, and the link.",
        "examples": ("pm show APS-30",),
        "related": ("today", "ready"),
        "common": (),
    },
    "triage": {
        "summary": "What needs a person: blocked, mentioned, or a new bug.",
        "examples": ("pm triage",),
        "related": ("today", "ready"),
        "common": ("workstream",),
    },
    "daily": {
        "summary": "What moved since yesterday, and who has what.",
        "examples": ("pm daily",),
        "related": ("me", "today"),
        "common": ("workstream", "product", "days"),
    },
    "me": {
        "summary": "Your own open work, or what you finished in a window.",
        "examples": ("pm me", "pm me --sprint"),
        "related": ("today", "daily"),
        "common": ("sprint", "since", "days", "summary", "who"),
    },
    "lint": {
        "summary": "Backlog quality checks. Nothing is written.",
        "examples": ("pm lint --workstream SDX",),
        "related": ("ready", "refine"),
        "common": ("workstream", "product", "json"),
    },
    "ready": {
        "summary": "Pass or fail against the team's ready agreement.",
        "examples": ("pm ready", "pm ready --plan"),
        "related": ("refine", "lint", "report"),
        "common": ("workstream", "product", "plan"),
    },
    "refine": {
        "summary": "Draft clearer titles and acceptance criteria.",
        "examples": ("pm refine --workstream SDX",),
        "related": ("ready", "review"),
        "common": ("workstream", "apply"),
    },
    "review": {
        "summary": "Flag titles and criteria a teammate would not understand.",
        "examples": ("pm review --workstream SDX",),
        "related": ("refine", "ready"),
        "common": ("workstream", "apply"),
    },
    "coverage": {
        "summary": "Work that no workstream claims.",
        "examples": ("pm coverage",),
        "related": ("workstreams", "lint"),
        "common": ("workstream",),
    },
    "report": {
        "summary": "The report for your role. The header states the window.",
        "examples": ("pm report", "pm report --sprint",
                     "pm report --since 2026-09-01",
                     "pm report --sources full"),
        "related": ("brief", "metrics", "me"),
        "common": ("product", "workstream", "sprint", "since", "audience",
                   "publish", "json", "sources"),
    },
    "brief": {
        "summary": "What changed since you last met that group.",
        "examples": ('pm brief --for "Design review"',),
        "related": ("report",),
        "common": ("for_audience", "audience", "sprint", "since", "debrief"),
    },
    "metrics": {
        "summary": "Delivery facts. --sprint is the Sprint review.",
        "examples": ("pm metrics", "pm metrics --sprint"),
        "related": ("report", "ready"),
        "common": ("workstream", "product", "sprint", "weeks", "audience"),
    },
    "release-notes": {
        "summary": "What shipped since a date, or in a version.",
        "examples": ("pm release-notes --since 2026-08-01",),
        "related": ("report", "metrics"),
        "common": ("since", "version", "audience", "workstream"),
    },
    "publish": {
        "summary": "Send a Markdown file you have already read.",
        "examples": ("pm publish report.md",),
        "related": ("report", "brief"),
        "common": (),
    },
    "doctor": {
        "summary": "Check the settings, Jira, and the model.",
        "examples": ("pm doctor",),
        "related": ("setup",),
        "common": ("discover_fields",),
    },
    "setup": {
        "summary": "Fill in the settings file, one question at a time.",
        "examples": ("pm setup", "pm setup --section model"),
        "related": ("doctor", "init"),
        "common": ("path", "section", "confluence_space", "confluence_root",
                   "model_api_key", "yes"),
    },
    "products": {
        "summary": "List products, or add and remove them.",
        "examples": ("pm products", "pm products add --name \"Integration Platform\" --abbrev IP"),
        "related": ("workstreams",),
        "common": ("goal", "confluence_page", "name", "abbrev"),
    },
    "workstreams": {
        "summary": "List workstreams, check scope, or add and remove them.",
        "examples": ("pm workstreams", "pm workstreams check"),
        "related": ("products", "coverage"),
        "common": ("confluence_page", "components", "product"),
    },
    "schedule": {
        "summary": "List, add, or remove a weekday job.",
        "examples": ("pm schedule", "pm schedule add today --at 08:30"),
        "related": ("today", "warm"),
        "common": ("at",),
    },
    "warm": {
        "summary": "Fill the model cache before you need the answer.",
        "examples": ("pm warm",),
        "related": ("report", "review"),
        "common": ("audience",),
    },
    "update": {
        "summary": "Upgrade pm-tools and migrate the config.",
        "examples": ("pm update",),
        "related": ("doctor",),
        "common": ("dry_run",),
    },
    "init": {
        "summary": "Create a settings file.",
        "examples": ("pm init",),
        "related": ("setup",),
        "common": ("path", "force"),
    },
    "mcp": {
        "summary": "stdio MCP server for read-only commands. Off unless you opt in.",
        "examples": ("pm mcp --yes-i-understand",),
        "related": ("doctor",),
        "common": ("yes_i_understand",),
    },
    "help": {
        "summary": "Discover commands, or open one command's full help.",
        "examples": ("pm help", "pm help all", "pm help report", "pm help roles"),
        "related": (),
        "common": (),
    },
}

INTENTS = (
    ("Start the day", ("today", "do", "daily", "me", "note")),
    ("Shape the backlog", ("ready", "refine", "lint", "show", "inbox", "triage")),
    ("Report", ("report", "brief", "metrics", "release-notes")),
)

ROLE_COMMANDS = {
    "pm": ("today", "do", "ready", "refine", "show", "report", "brief", "me"),
    "developer": ("daily", "me", "show", "ready", "release-notes"),
    "service-designer": ("report", "brief", "show", "release-notes", "me"),
    "analyst": ("ready", "refine", "lint", "show", "inbox", "report", "me"),
    "leadership": ("report", "brief", "metrics"),
    "partner": ("report", "brief"),
}

ROLE_BLURB = {
    "pm": "Product management: the morning list, the backlog, and the weekly report.",
    "developer": "Developer: what moved, what is blocked, and what shipped. pm me is your own work.",
    "service-designer": "Service designer: changed service documentation, the report, and the design-review brief.",
    "analyst": "Business analyst: what is ready to plan, what still needs refinement, and the requirement report.",
    "leadership": "Leadership: the short portfolio report. No backlog writes.",
    "partner": "Partner: the external report. No internal backlog writes.",
}

_ROLE_DOCS = "https://github.com/dstainton/pm-tools/tree/main/docs/roles"

_ALL_INTENTS = INTENTS + (
    ("Setup", ("setup", "doctor", "products", "workstreams", "schedule",
               "warm", "update", "init", "mcp", "publish", "coverage", "help")),
)


def known_commands():
    return tuple(CATALOGUE)


def _entry(name):
    return CATALOGUE.get(name) or {
        "summary": "",
        "examples": (f"pm {name}",),
        "related": (),
        "common": (),
    }


def _blurb(parser, name):
    text = ""
    if parser is not None:
        text = (getattr(parser, "description", None) or "").strip()
        if not text:
            text = (getattr(parser, "_pm_blurb", None) or "").strip()
    return text or _entry(name)["summary"] or f"pm {name}"


def _matches(action, wanted):
    dest = getattr(action, "dest", "") or ""
    if dest in wanted:
        return True
    for option in getattr(action, "option_strings", ()) or ():
        flag = option.lstrip("-").replace("-", "_")
        if flag in wanted or option.lstrip("-") in wanted:
            return True
    return False


def _visible_actions(parser):
    for action in getattr(parser, "_actions", ()) or ():
        if getattr(action, "help", None) == argparse.SUPPRESS:
            continue
        if action.dest in ("help", "help_requested"):
            continue
        yield action


def _is_positional(action):
    return not (getattr(action, "option_strings", ()) or ())


def _required_positional(action):
    nargs = getattr(action, "nargs", None)
    if nargs in ("?", "*", argparse.REMAINDER):
        return False
    if nargs == argparse.OPTIONAL:
        return False
    return True


def _option_label(action):
    if _is_positional(action):
        meta = action.metavar or action.dest
        if isinstance(meta, (list, tuple)):
            meta = " ".join(str(part) for part in meta)
        label = str(meta)
        if action.choices:
            label += " {" + ",".join(str(choice) for choice in action.choices) + "}"
        if _required_positional(action):
            label += " (required)"
        return label
    parts = []
    for option in action.option_strings:
        meta = action.metavar
        if isinstance(meta, (list, tuple)):
            meta = " ".join(str(part) for part in meta)
        if action.choices and action.nargs != 0:
            choice = "{" + ",".join(str(choice) for choice in action.choices) + "}"
            parts.append(f"{option} {choice}")
        elif meta and action.nargs != 0:
            shown = f"[{meta}]" if action.nargs == "?" else str(meta)
            parts.append(f"{option} {shown}")
        else:
            parts.append(option)
    return ", ".join(parts)


def _help_line(action):
    text = (getattr(action, "help", None) or "").strip()
    if text == "==SUPPRESS==":
        return ""
    return text


def commands_for_role(role):
    if role in ROLE_COMMANDS:
        return ROLE_COMMANDS[role]
    return ROLE_COMMANDS["pm"]


def discovery_page(role=None, subs=None):
    """What to type. Role-aware when a config names a role."""
    chosen = role if role in ROLE_COMMANDS else None
    ordered = commands_for_role(chosen or "pm")
    lines = ["usage: pm", ""]
    if chosen:
        lines.append(ROLE_BLURB[chosen])
    else:
        lines.append("What should I type?")
    lines.append("")

    def intent_of(command):
        for title, members in INTENTS:
            if command in members:
                return title
        return "Other"

    current = None
    for name in ordered:
        title = intent_of(name)
        if title != current:
            lines.append(title)
            lines.append("")
            current = title
        summary = _entry(name)["summary"]
        parser = (subs or {}).get(name)
        if parser is not None and not summary:
            summary = _blurb(parser, name)
        lines.append(f"  pm {name}")
        if summary:
            lines.append(f"      {summary}")
        for example in _entry(name)["examples"]:
            if example != f"pm {name}":
                lines.append(f"      {example}")
                break
        lines.append("")
    lines.append("Run: pm help all")
    lines.append("Run: pm <command> -h")
    lines.append("Run: pm help roles")
    return "\n".join(lines).rstrip() + "\n"


def all_page(subs):
    lines = [
        "usage: pm <command> [options]",
        "",
        "Every command. pm <command> -h shows how to run it.",
        "",
    ]
    seen = set()
    ordered = []
    for _title, members in _ALL_INTENTS:
        for name in members:
            if name not in seen:
                seen.add(name)
                ordered.append(name)
    if subs:
        for name in subs:
            if name not in seen:
                ordered.append(name)
    current = None
    for name in ordered:
        title = next((label for label, members in _ALL_INTENTS if name in members), "Other")
        if title != current:
            lines.append(title)
            lines.append("")
            current = title
        parser = (subs or {}).get(name)
        summary = _entry(name)["summary"] or _blurb(parser, name)
        lines.append(f"  pm {name}")
        if summary:
            lines.append(f"      {summary}")
        lines.append("")
    lines.append("Run: pm <command> -h")
    lines.append("Run: pm help roles")
    return "\n".join(lines).rstrip() + "\n"


def roles_page():
    lines = [
        "usage: pm help roles",
        "",
        "A role chooses which commands to show first, and which report you get.",
        "Set role in the settings file. pm help with no config shows the product-management set.",
        "",
    ]
    for role, blurb in ROLE_BLURB.items():
        lines.append(role)
        lines.append(f"  {blurb}")
        joined = ", ".join(f"pm {name}" for name in ROLE_COMMANDS[role])
        lines.append(f"  {joined}")
        lines.append("")
    lines.append(f"Role guides: {_ROLE_DOCS}")
    lines.append("Run: pm help all")
    lines.append("Run: pm <command> -h")
    return "\n".join(lines).rstrip() + "\n"


def command_page(parser, name, advanced=False):
    """Everything needed to run the command. `--advanced` changes nothing."""
    del advanced
    if parser is None:
        return f"pm {name} -h\n"
    entry = _entry(name)
    lines = [_blurb(parser, name), ""]
    usage = parser.format_usage().strip()
    lines.append("Usage")
    lines.append(f"  {usage}")
    lines.append("")
    actions = list(_visible_actions(parser))
    positionals = [action for action in actions if _is_positional(action)]
    if positionals:
        lines.append("Positionals")
        lines.append("")
        for action in positionals:
            lines.append(f"  {_option_label(action)}")
            help_text = _help_line(action)
            if help_text:
                lines.append(f"      {help_text}")
        lines.append("")
    examples = [example for example in entry["examples"] if example != f"pm {name}"]
    if not examples:
        examples = list(entry["examples"])
    if examples:
        lines.append("Examples")
        lines.append("")
        for example in examples:
            lines.append(f"  {example}")
        lines.append("")
    flags = [action for action in actions if not _is_positional(action)]
    common = [action for action in flags if _matches(action, set(entry["common"]))]
    other = [action for action in flags if action not in common]
    if common:
        lines.append("Common options")
        lines.append("")
        for action in common:
            lines.append(f"  {_option_label(action)}")
            help_text = _help_line(action)
            if help_text:
                lines.append(f"      {help_text}")
        lines.append("")
    if other:
        lines.append("Other options")
        lines.append("")
        for action in other:
            lines.append(f"  {_option_label(action)}")
            help_text = _help_line(action)
            if help_text:
                lines.append(f"      {help_text}")
        lines.append("")
    if entry["related"]:
        lines.append("Related")
        lines.append("  " + ", ".join(f"pm {item}" for item in entry["related"]))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def regular_page():
    """Compatibility name for the discovery page with no role."""
    return discovery_page(None)


def advanced_page(subs):
    """Compatibility name. `--advanced` now lists every command."""
    return all_page(subs)
