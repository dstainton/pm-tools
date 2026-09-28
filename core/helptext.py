"""Two help pages: typical commands, and every command.

Role guides in docs/roles stay the long form. This module is what `pm`,
`pm help`, and `pm <command> -h` print.
"""


REGULAR = (
    ("setup", "Fill in the settings file, one question at a time.", "pm setup"),
    ("today", "The morning screen: Sprint Goal and a numbered list.", "pm today"),
    ("do", "Carry out item N from that list, after showing the change.", "pm do 2"),
    ("note", "Save a thought for later.", 'pm note "customer wants an SSO audit export"'),
    ("daily", "What moved since yesterday, and who has what.", "pm daily"),
    ("report", "The weekly file. --sprint is the open Sprint.", "pm report --sprint"),
    ("brief", "What changed since you last met that group.", 'pm brief --for "Leadership"'),
    ("doctor", "Check the settings, Jira, and the model.", "pm doctor"),
)

EXAMPLES = {
    "setup": "pm setup",
    "today": "pm today",
    "do": "pm do 2",
    "note": 'pm note "customer wants an SSO audit export"',
    "inbox": "pm inbox",
    "show": "pm show APS-30",
    "triage": "pm triage",
    "daily": "pm daily",
    "me": "pm me",
    "lint": "pm lint --workstream SDX",
    "ready": "pm ready --workstream SDX",
    "refine": "pm refine --workstream SDX",
    "review": "pm review --workstream SDX",
    "coverage": "pm coverage",
    "report": "pm report --sprint",
    "brief": 'pm brief --for "Leadership"',
    "metrics": "pm metrics",
    "release-notes": "pm release-notes --since 2026-08-01",
    "publish": "pm publish report.md",
    "doctor": "pm doctor",
    "products": "pm products",
    "workstreams": "pm workstreams check",
    "schedule": "pm schedule add today --at 08:30",
    "warm": "pm warm",
    "update": "pm update",
    "init": "pm init",
    "mcp": "pm mcp --yes-i-understand",
    "help": "pm help --advanced",
}

GROUPS = (
    ("Everyday", ("today", "do", "show", "note", "inbox", "triage", "daily", "me")),
    ("Backlog", ("lint", "ready", "refine", "review", "coverage")),
    ("Reporting", ("report", "brief", "metrics", "release-notes", "publish")),
    ("Setup", ("setup", "doctor", "products", "workstreams", "schedule", "warm",
               "update", "init", "mcp")),
)

# Dest names or option strings included on `pm <command> -h`.
COMMON = {
    "setup": ("path", "section", "confluence_space", "confluence_team_page",
              "model_api_key", "yes"),
    "today": ("config", "product", "workstream"),
    "do": ("config", "yes", "dry_run"),
    "note": ("config",),
    "inbox": ("config", "criteria"),
    "show": ("config",),
    "triage": ("config", "workstream"),
    "daily": ("config", "workstream", "product"),
    "me": ("config", "sprint", "since", "days", "summary", "who", "audience"),
    "lint": ("config", "workstream", "product"),
    "ready": ("config", "workstream", "product"),
    "refine": ("config", "workstream", "apply"),
    "review": ("config", "workstream", "apply"),
    "coverage": ("config", "workstream"),
    "report": ("config", "product", "workstream", "sprint", "since", "audience", "publish"),
    "brief": ("config", "for_audience", "audience", "sprint", "since", "debrief"),
    "metrics": ("config", "workstream", "product", "sprint", "weeks", "audience"),
    "release-notes": ("config", "since", "version", "audience", "workstream"),
    "publish": ("config",),
    "doctor": ("config",),
    "products": ("goal", "confluence_page", "name", "abbrev"),
    "workstreams": ("confluence_page", "components", "product"),
    "schedule": ("config",),
    "warm": ("config", "audience"),
    "update": ("config", "dry_run"),
    "init": ("path", "force"),
    "mcp": ("yes_i_understand",),
}


def _blurb(parser):
    if parser is None:
        return ""
    text = (getattr(parser, "description", None) or "").strip()
    if text:
        return text
    return (getattr(parser, "_pm_blurb", None) or "").strip()


def _matches(action, wanted):
    dest = getattr(action, "dest", "") or ""
    if dest in wanted:
        return True
    for option in getattr(action, "option_strings", ()) or ():
        flag = option.lstrip("-").replace("-", "_")
        if flag in wanted or option.lstrip("-") in wanted:
            return True
    return False


def regular_page():
    lines = [
        "usage: pm",
        "",
        "Typical commands. pm help --advanced lists every command.",
        "Guides for each role: docs/roles/",
        "",
    ]
    for name, blurb, example in REGULAR:
        lines.append(f"  pm {name}")
        lines.append(f"      {blurb}")
        lines.append(f"      {example}")
        lines.append("")
    lines.append("pm help --advanced")
    lines.append("pm <command> -h")
    return "\n".join(lines).rstrip() + "\n"


def advanced_page(subs):
    lines = [
        "usage: pm <command> [options]",
        "",
        "Every command, with one example. pm <command> -h shows the usual flags.",
        "pm <command> -h --advanced shows every flag.",
        "",
    ]
    for title, names in GROUPS:
        lines.append(title)
        lines.append("")
        for name in names:
            parser = subs.get(name)
            blurb = _blurb(parser)
            example = EXAMPLES.get(name, f"pm {name}")
            lines.append(f"  pm {name}")
            if blurb:
                lines.append(f"      {blurb}")
            lines.append(f"      {example}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def command_page(parser, name, advanced=False):
    if advanced or parser is None:
        if parser is None:
            return f"pm {name} -h --advanced\n"
        return parser.format_help()
    blurb = _blurb(parser) or f"pm {name}"
    lines = [blurb, "", f"  {EXAMPLES.get(name, 'pm ' + name)}", ""]
    wanted = COMMON.get(name, ())
    shown = False
    if wanted:
        lines.append("Usual flags:")
        lines.append("")
        for action in getattr(parser, "_actions", ()):
            if not _matches(action, wanted):
                continue
            options = ", ".join(getattr(action, "option_strings", ()) or ())
            if not options and getattr(action, "dest", "") not in ("help",):
                options = action.dest
            help_text = (getattr(action, "help", None) or "").strip()
            if options:
                lines.append(f"  {options}")
                if help_text and help_text != "==SUPPRESS==":
                    lines.append(f"      {help_text}")
                shown = True
        lines.append("")
    if not shown:
        lines.append("pm " + name + " -h --advanced lists every flag.")
        lines.append("")
    else:
        lines.append(f"pm {name} -h --advanced lists every flag.")
    return "\n".join(lines).rstrip() + "\n"
