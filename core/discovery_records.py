"""Canonical read-only evidence records for Phase 2C.

These are source observations, not product ownership decisions. Original source
payloads remain separate; derived taxonomy records may reference evidence IDs.
"""
from datetime import datetime


def _date(value):
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("timestamps must be strings or null")
    return value


def jira_issue(issue, project=None):
    """Normalize a Jira issue without assuming a fixed issue-type hierarchy.

    The configured hierarchy resolver may enrich `hierarchy_level` later.
    Labels and components are directly assigned on this issue; do not inherit
    parent values into these fields.
    """
    fields = issue.get("fields") or {}
    key = issue.get("key")
    if not key:
        raise ValueError("Jira evidence requires issue.key")
    kind = fields.get("issuetype") or {}
    parent = fields.get("parent") or {}
    status = fields.get("status") or {}
    components = fields.get("components") or []
    labels = fields.get("labels") or []
    if not isinstance(labels, list) or not isinstance(components, list):
        raise ValueError("Jira labels and components must be lists")
    return {
        "evidence_id": "jira:" + str(key),
        "source": "jira",
        "source_id": str(issue.get("id") or key),
        "project": str(project or (fields.get("project") or {}).get("key") or ""),
        "issue_key": str(key),
        "issue_type_id": str(kind.get("id") or ""),
        "issue_type": kind.get("name") or "",
        "hierarchy_level": kind.get("hierarchyLevel"),
        "parent_key": parent.get("key"),
        "status": status.get("name"),
        "status_category": (status.get("statusCategory") or {}).get("key"),
        "labels_direct": list(labels),
        "components_direct": [
            {"id": str(c.get("id") or ""), "name": c.get("name") or ""}
            for c in components
        ],
        "created_at": _date(fields.get("created")),
        "updated_at": _date(fields.get("updated")),
        "resolved_at": _date(fields.get("resolutiondate")),
        "summary": fields.get("summary") or "",
        "classification_state": "observed",
        "ownership_confirmed": False,
    }


def confluence_page(page, scope_id=None):
    """Normalize a Confluence page without treating its space as ownership."""
    page_id = page.get("id")
    if not page_id:
        raise ValueError("Confluence evidence requires page.id")
    ancestors = [str(a["id"]) for a in (page.get("ancestors") or [])
                 if isinstance(a, dict) and a.get("id")]
    return {
        "evidence_id": "confluence:" + str(page_id),
        "source": "confluence",
        "source_id": str(page_id),
        "space": (page.get("space") or {}).get("key"),
        "scope_id": scope_id,
        "title": page.get("title") or "",
        "ancestor_ids": ancestors,
        "updated_at": _date((page.get("version") or {}).get("when")),
        "created_at": _date(((page.get("history") or {}).get("createdDate"))),
        "classification_state": "observed",
        "ownership_confirmed": False,
    }
