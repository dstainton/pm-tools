"""Deterministic, evidence-aware clarification prompts for discovery.

Questions are proposals, not conclusions, and do not modify sources.
"""


def _status(evidence, kind):
    matches = [item for item in evidence if item.get("kind") == kind]
    return matches[0] if matches else {"state": "not configured"}


def build(report):
    """Prioritized, bounded questions anchored to known gaps and source states."""
    result = []
    for product in report.get("products", []):
        if product.get("implicit"):
            continue
        if not product.get("goal"):
            result.append({
                "entity": product["name"], "abbrev": product["abbrev"],
                "field": "product goal",
                "question": "What outcome should this product achieve?",
                "basis": "No product goal in configuration",
                "source_state": _status(product.get("evidence") or [], "Confluence")["state"],
            })
    for ws in report.get("workstreams", []):
        evidence = ws.get("evidence") or []
        page = _status(evidence, "Confluence")
        epics = _status(evidence, "Jira Epics")
        references = []
        if page.get("state") == "retrieved":
            references.append("Confluence page " + page.get("reference", "unknown"))
        if epics.get("state") == "retrieved":
            references.extend(item.get("key", "unknown")
                              for item in (epics.get("items") or [])[:3])
        result.append({
            "entity": ws["name"], "abbrev": ws["abbrev"],
            "field": "purpose and responsibilities",
            "question": "What is this workstream responsible for, and what is outside its remit?",
            "basis": "Membership anchors describe association, not ownership; "
                     "purpose and boundaries are unconfirmed",
            "source_state": "Confluence: {}; Jira Epics: {}".format(
                page["state"], epics["state"]),
            "references": references,
        })
    # A small question queue, not an undifferentiated profile questionnaire.
    return result[:5]


def attach(report):
    report["clarifications"] = build(report)
    return report
