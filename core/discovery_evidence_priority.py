"""Evidence ranking and provenance grouping for offline discovery.

All source records remain indexed. These helpers affect which passages are
reviewed, not source retention or verified configuration. Jira comments and
changelog rows belong to their parent issue for evidence-independence counts.
"""

# Lower is preferable for capability and product relationship discovery.
PRIORITY = {
    ("confluence", "confluence_page"): 0,
    ("confluence", "confluence_blogpost"): 0,
    ("confluence", "confluence_blog"): 0,
    ("jira", "issue"): 1,
    ("confluence", "confluence_comment"): 2,
    ("jira", "comment"): 3,
    ("jira", "change"): 4,
}


def priority(source, kind):
    return PRIORITY.get((source, kind), 5)


def parent_group(project, source, kind, source_key, citation):
    """Stable independent document group, not a count of FTS rows.

    Jira issues, comments and changes share the Jira issue key. The fallback
    handles historical fixtures where source_key is not populated consistently.
    Other documents retain independent citation identities.
    """
    if source == "jira" and kind in ("issue", "comment", "change"):
        key = str(source_key or "").strip()
        if not key and str(citation or "").startswith("jira:"):
            key = str(citation).split(":", 1)[1].split("#", 1)[0]
        return (project, "jira_issue", key or citation)
    if source == "confluence":
        key = str(citation or "")
        if key.startswith("confluence:"):
            key = key.split("#", 1)[0]
            return (project, "confluence_page", key)
    return (project, source, str(citation))


def is_historical(source, kind):
    return source == "jira" and kind == "change"
