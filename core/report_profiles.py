"""What each role's report contains.

Privacy stays in `core.audience`: who may be named, and what a partner may
see. A profile chooses the sections, the attention block, documents, metrics,
and the file identity. `analyst`, `developer`, and `service-designer` share
the work privacy shape and do not share a report.
"""

from core import audience


# Generated section roles, in prompt order. Progress and Roadmap stay
# available for a profile that asks for them. The product-management report
# does not: Epic rows already carry that state.
SECTION_ORDER = (
    "changed",
    "progress",
    "roadmap",
    "decisions",
    "dependencies",
    "waiting",
    "risks",
)

_PM_SECTIONS = ("changed", "decisions", "dependencies", "waiting", "risks")

PROFILES = {
    "pm": {
        "privacy": "pm",
        "display": None,
        "sections": _PM_SECTIONS,
        "attention": "pm",
        "epics": True,
        "documents": True,
        "docs_before_epics": False,
        "doc_mode": "all",
        "doc_hints": (),
        "doc_rest_cap": None,
        "registers": ("decision", "risk", "adr", "dependency"),
        "elevate": (),
        "metrics": "pulse",
        "sources": "compact",
        "goal": True,
        "increment": False,
        "brief_documents": True,
        "brief_doc_heading": "Documents changed",
        "brief_doc_hints": (),
    },
    "work": {
        "privacy": "work",
        "display": None,
        "sections": _PM_SECTIONS,
        "attention": "pm",
        "epics": True,
        "documents": True,
        "docs_before_epics": False,
        "doc_mode": "all",
        "doc_hints": (),
        "doc_rest_cap": None,
        "registers": ("decision", "risk", "adr", "dependency"),
        "elevate": (),
        "metrics": "pulse",
        "sources": "compact",
        "goal": True,
        "increment": False,
        "brief_documents": False,
        "brief_doc_heading": "Documents changed",
        "brief_doc_hints": (),
    },
    "analyst": {
        "privacy": "work",
        "display": "Business analyst",
        "sections": ("changed", "decisions", "dependencies", "waiting", "risks"),
        "attention": "analyst",
        "epics": True,
        "documents": True,
        "docs_before_epics": True,
        "doc_mode": "prefer",
        "doc_hints": ("requirement", "requirements", "story", "spec",
                      "acceptance", "criteria", "backlog"),
        "doc_rest_cap": 5,
        "registers": ("decision", "dependency", "risk"),
        "elevate": ("decision",),
        "metrics": "none",
        "sources": "compact",
        "goal": True,
        "increment": False,
        "brief_documents": True,
        "brief_doc_heading": "Requirement documents changed",
        "brief_doc_hints": ("requirement", "requirements", "story", "spec",
                            "acceptance", "criteria"),
    },
    "developer": {
        "privacy": "work",
        "display": "Developer",
        "sections": ("changed", "decisions", "dependencies", "risks"),
        "attention": "developer",
        "epics": True,
        "documents": True,
        "docs_before_epics": True,
        "doc_mode": "only",
        "doc_hints": ("adr", "architecture", "technical decision", "design decision"),
        "doc_rest_cap": 0,
        "registers": ("adr", "decision", "dependency"),
        "elevate": ("adr", "decision"),
        "metrics": "sprint",
        "sources": "compact",
        "goal": True,
        "increment": False,
        "brief_documents": True,
        "brief_doc_heading": "ADRs and technical decisions",
        "brief_doc_hints": ("adr", "architecture", "technical", "decision"),
    },
    "service-designer": {
        "privacy": "work",
        "display": "Service designer",
        "sections": ("changed", "decisions", "waiting", "risks"),
        "attention": "service",
        "epics": True,
        "documents": True,
        "docs_before_epics": True,
        "doc_mode": "prefer",
        "doc_hints": ("research", "journey", "blueprint", "service",
                      "experience", "design"),
        "doc_rest_cap": 3,
        "registers": ("decision", "risk"),
        "elevate": ("decision",),
        "metrics": "none",
        "sources": "compact",
        "goal": True,
        "increment": False,
        "brief_documents": True,
        "brief_doc_heading": "Changed service documentation",
        "brief_doc_hints": ("research", "journey", "blueprint", "service",
                            "experience", "design"),
    },
    "leadership": {
        "privacy": "leadership",
        "display": None,
        "sections": ("dependencies", "waiting", "risks"),
        "attention": "leadership",
        "epics": True,
        "documents": False,
        "docs_before_epics": False,
        "doc_mode": "all",
        "doc_hints": (),
        "doc_rest_cap": None,
        "registers": ("decision", "risk"),
        "elevate": (),
        "metrics": "headline",
        "sources": "short",
        "goal": True,
        "increment": False,
        "brief_documents": False,
        "brief_doc_heading": "Documents changed",
        "brief_doc_hints": (),
    },
    "partner": {
        "privacy": "partner",
        "display": None,
        "sections": (),
        "attention": "partner",
        "epics": True,
        "documents": False,
        "docs_before_epics": False,
        "doc_mode": "all",
        "doc_hints": (),
        "doc_rest_cap": None,
        "registers": ("decision",),
        "elevate": (),
        "metrics": "none",
        "sources": "none",
        "goal": False,
        "increment": False,
        "brief_documents": False,
        "brief_doc_heading": "Documents changed",
        "brief_doc_hints": (),
    },
}


def known():
    return tuple(PROFILES)


def get(profile_id):
    profile = PROFILES.get(profile_id)
    if profile is None:
        names = ", ".join(PROFILES)
        raise SystemExit(f"Unknown report profile {profile_id}. Use one of: {names}.")
    return {"id": profile_id, **profile}


def resolve(cfg, args):
    """Profile for this run.

    `--audience` wins, then `role`, then `audiences.default`, then `pm`.
    `work` stays the generic internal report. A role name is a profile, not
    a privacy shape.
    """
    chosen = getattr(args, "audience", None) if args is not None else None
    if not chosen:
        role = cfg.get("role") if isinstance(cfg, dict) else None
        role = role.strip() if isinstance(role, str) else ""
        if role:
            if role not in PROFILES:
                names = ", ".join(audience.ROLES)
                raise SystemExit(f"Unknown role {role}. Use one of: {names}.")
            chosen = role
        else:
            chosen = audience.settings(cfg)["default"] or "pm"
    if chosen not in PROFILES:
        names = ", ".join(PROFILES)
        raise SystemExit(f"Unknown audience {chosen}. Use one of: {names}.")
    return chosen


def privacy(profile_id):
    return get(profile_id)["privacy"]


def names_people(profile_id):
    return audience.names_people(privacy(profile_id))


def display_name(cfg, profile_id):
    profile = get(profile_id)
    if profile["display"]:
        return profile["display"]
    return audience.display_name(cfg, profile["privacy"])


def sections(profile_id):
    """Heading roles this profile asks the model to write, in prompt order."""
    wanted = set(get(profile_id)["sections"])
    return tuple(role for role in SECTION_ORDER if role in wanted)


def sources_mode(profile_id, args):
    chosen = getattr(args, "sources", None) if args is not None else None
    if chosen in ("full", "compact"):
        return chosen
    return get(profile_id)["sources"]


def page_blob(page):
    labels = " ".join(str(label) for label in (page.get("labels") or []))
    return " ".join((
        str(page.get("kind") or ""),
        str(page.get("type") or ""),
        str(page.get("title") or ""),
        str(page.get("summary") or ""),
        labels,
    )).lower()


def page_matches(page, hints):
    if not hints:
        return True
    blob = page_blob(page)
    return any(hint in blob for hint in hints)


def select_pages(pages, profile):
    """Pages this profile prints, preferred kinds first."""
    pages = list(pages or [])
    if not profile.get("documents"):
        return []
    hints = profile.get("doc_hints") or ()
    mode = profile.get("doc_mode") or "all"
    if mode == "all" or not hints:
        return pages
    matched = [page for page in pages if page_matches(page, hints)]
    rest = [page for page in pages if page not in matched]
    if mode == "only":
        return matched
    cap = profile.get("doc_rest_cap")
    if cap is not None:
        rest = rest[:cap]
    return matched + rest
