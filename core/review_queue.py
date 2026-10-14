"""Deterministic, issue-level investigation queue for backlog assessment.

Ordering is intended for *review*, never product implementation priority.
Each issue appears in at most one queue group.
"""

GROUPS = (
    ("stalled-unassigned", "Stalled in-progress work without an assignee",
     "Confirm whether active delivery is blocked and who can resolve it."),
    ("overdue", "Overdue open work",
     "Verify the commitment, date, and stakeholder implications."),
    ("stalled-active", "Other stalled in-progress work",
     "Check whether work is progressing outside Jira or needs intervention."),
    ("multiple-workstreams", "Conflicting workstream claims",
     "Clarify accountable product or workstream ownership."),
    ("unclaimed-active", "Active issues outside configured workstreams",
     "Determine whether current work belongs in the configured scope."),
    ("unclaimed-old", "Unclaimed issues not updated in over a year",
     "Review relevance and disposition before changing metadata."),
    ("unclaimed-other", "Other unclaimed issues",
     "Identify workstream membership or consciously leave outside scope."),
    ("other", "Other backlog quality review",
     "Check the item's maturity before deciding whether fields need attention."),
)


def build(inventory, assessment_result, sample_limit=12):
    """Return mutually exclusive, evidence-backed review groups.

    Uses only normalized issues and the deterministic assessment findings.
    No inference of obsolescence, stakeholder importance, or delivery priority.
    """
    by_key = {}
    for finding in assessment_result.get("findings") or []:
        key = finding.get("key")
        if key:
            by_key.setdefault(key, set()).add(finding["rule"])
    groups = {name: [] for name, _, _ in GROUPS}
    for issue in inventory.get("issues") or []:
        key = issue.get("key")
        if not key:
            continue
        flags = by_key.get(key, set())
        if not flags:
            continue
        status = str(issue.get("status_category") or "").lower()
        updated_age = next((f.get("updated_age_days") for f in
                            assessment_result["findings"]
                            if f.get("key") == key), None)
        if "stalled-active" in flags and "unassigned-person" in flags:
            name = "stalled-unassigned"
        elif "overdue" in flags:
            name = "overdue"
        elif "stalled-active" in flags:
            name = "stalled-active"
        elif "multiple-workstreams" in flags:
            name = "multiple-workstreams"
        elif "unclaimed-workstream" in flags and status == "indeterminate":
            name = "unclaimed-active"
        elif "unclaimed-workstream" in flags and (
                updated_age is not None and updated_age > 365):
            name = "unclaimed-old"
        elif "unclaimed-workstream" in flags:
            name = "unclaimed-other"
        else:
            name = "other"
        groups[name].append({
            "key": key, "url": issue.get("url") or "",
            "title": issue.get("summary") or "(no summary)",
            "status": issue.get("status") or issue.get("status_category") or "Unknown",
            "updated_age_days": updated_age,
            "rules": sorted(flags),
        })
    result = []
    for name, title, rationale in GROUPS:
        rows = groups[name]
        if not rows:
            continue
        rows.sort(key=lambda row: (
            -(row["updated_age_days"] if row["updated_age_days"] is not None else -1),
            row["key"]))
        result.append({
            "id": name, "title": title, "rationale": rationale,
            "count": len(rows), "sample": rows[:sample_limit],
        })
    return result
