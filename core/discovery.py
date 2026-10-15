"""Phase 2A: configuration-only product and workstream discovery.

Read configured facts; no Jira requests, models, or inferred ownership.
"""
from core import products, workstreams


def _project_origin(cfg, ws):
    if ws.get("project"):
        return "workstream"
    if ws.get("jira_project"):
        return "workstream legacy jira_project"
    parent = products.resolve_product(cfg, products.product_abbrev_of(ws))
    if parent and parent.get("project"):
        return "product"
    if (cfg.get("jira") or {}).get("project"):
        return "Jira default"
    return "unknown"


def inspect(cfg, selected=None, project=None):
    """Return deterministic configured facts and explicit unknowns."""
    streams = list(selected if selected is not None else cfg.get("workstreams") or [])
    configured = products.listed_products(cfg)
    # Keep selected workstreams in existing product order, but also show empty
    # configured products when no selector is applied.
    allowed = {products.product_abbrev_of(ws).lower() for ws in streams}
    has_selector = selected is not None
    entities = []
    for product in configured:
        key = product["abbrev"].lower()
        if has_selector and key not in allowed:
            continue
        entities.append((product, [ws for ws in streams
                                   if products.product_abbrev_of(ws).lower() == key]))
    unassigned = [ws for ws in streams if products.product_abbrev_of(ws).lower()
                  == products.UNASSIGNED_ABBREV.lower()]
    if unassigned:
        entities.append((products.unassigned_product(), unassigned))

    report = {"products": [], "workstreams": [], "scope_project": project,
              "coverage": "configured facts only; no Jira or document sources queried"}
    for product, children in entities:
        pseudo = product["abbrev"] == products.UNASSIGNED_ABBREV
        if project is not None:
            children = [ws for ws in children if workstreams.project_of(cfg, ws) == project]
            if not children and product.get("project") != project:
                continue
        goal = product.get("product_goal") or None
        report["products"].append({
            "name": product["name"], "abbrev": product["abbrev"],
            "project": product.get("project"),
            "goal": goal, "implicit": pseudo,
            "source": "implicit unassigned grouping" if pseudo else "config.products",
            "gaps": ([] if goal or pseudo else ["product goal"]),
            "workstreams": [ws["abbrev"] for ws in children],
        })
        for ws in children:
            anchors = workstreams.anchor_values(cfg, ws)
            mode = workstreams.membership_settings(cfg)["by"]
            report["workstreams"].append({
                "name": ws["name"], "abbrev": ws["abbrev"],
                "product": product["abbrev"],
                "project": workstreams.project_of(cfg, ws),
                "project_origin": _project_origin(cfg, ws),
                "anchor_mode": mode, "anchors": anchors,
                "legacy_jql_configured": any(ws.get(k) for keys in
                    workstreams.LEGACY_FIELDS.values() for k in keys),
                "source": "config.workstreams",
                "gaps": ["purpose", "responsibilities", "exclusions"],
            })
    if not report["products"] and project and (cfg.get("jira") or {}).get("project") == project:
        report["note"] = "Jira project configured but no matching product or workstream profiles"
    return report


def summary(report):
    lines = ["Product and workstream discovery", "",
             "Source coverage: " + (report["coverage"] if report.get("enriched") else
                                    "configuration only (no Jira or document retrieval)")]
    if report["scope_project"]:
        lines.append("Project: " + report["scope_project"])
    lines.append("{} product group(s), {} workstream(s)".format(
        len(report["products"]), len(report["workstreams"])))
    for product in report["products"]:
        lines.append("")
        lines.append("{} ({}){}".format(product["name"], product["abbrev"],
                                       " [implicit grouping]" if product["implicit"] else ""))
        lines.append("  Goal: " + (product["goal"] or "unknown"))
        children = [ws for ws in report["workstreams"]
                    if ws["product"] == product["abbrev"]]
        for ws in children:
            lines.append("  {} ({}), project: {} ({})".format(
                ws["name"], ws["abbrev"], ws["project"] or "unknown",
                ws["project_origin"]))
            lines.append("    Membership: {} {}".format(
                ws["anchor_mode"], ", ".join(ws["anchors"]) or
                ("legacy JQL configured" if ws["legacy_jql_configured"] else "unknown")))
            lines.append("    Purpose/responsibilities/boundaries: unknown")
    if not report["products"]:
        lines.append(report.get("note") or "No product or workstream configuration in scope.")
    if report.get("enriched"):
        lines.append("")
        lines.append("Evidence (examples only; not confirmed responsibilities):")
        for entity in report["products"] + report["workstreams"]:
            evidence = entity.get("evidence") or []
            for item in evidence:
                detail = item.get("detail") or (
                    "{} item(s) sampled".format(len(item.get("items") or []))
                    if item.get("items") is not None else item.get("title") or "")
                lines.append("  {}: {} {} {}".format(
                    entity["abbrev"], item["kind"], item["state"], detail))
    if "clarifications" in report:
        lines.append("")
        lines.append("Questions for review (no answers assumed):")
        for i, item in enumerate(report["clarifications"], 1):
            lines.append("  {}. {} ({}): {}".format(
                i, item["entity"], item["abbrev"], item["question"]))
    lines.append("")
    lines.append("Configured membership is not proof of business ownership.")
    return "\n".join(lines) + "\n"


def _evidence_lines(evidence):
    lines = ["- Evidence: {} ({})".format(
        evidence["kind"], evidence["state"])]
    if evidence.get("reference"):
        lines.append("  - Reference: " + evidence["reference"])
    if evidence.get("updated"):
        lines.append("  - Last updated: " + evidence["updated"])
    if evidence.get("title"):
        lines.append("  - Title: " + evidence["title"])
    if evidence.get("detail"):
        lines.append("  - Note: " + evidence["detail"])
    if evidence.get("excerpt"):
        lines.append("  - Excerpt (unverified): " + evidence["excerpt"])
    for item in evidence.get("items") or []:
        lines.append("  - {}: {} (updated {})".format(
            item["key"], item["title"], item["updated"]))
    return lines + [""]


def markdown(report):
    lines = ["# Product and workstream discovery", "",
             ("Phase 2B: bounded source examples, not confirmed ownership."
              if report.get("enriched") else
              "Phase 2A: configured facts only. No Jira, Confluence, SharePoint, "
              "or model was queried. Membership does not prove business ownership."),
             "", "- Coverage: " + report["coverage"],
             "- Project filter: " + (report["scope_project"] or "none"), "",
             "## Configured profiles", ""]
    if not report["products"]:
        lines.append(report.get("note") or "No configured profiles in scope.")
    for product in report["products"]:
        lines.extend(["### {} ({})".format(product["name"], product["abbrev"]), "",
                      "- Source: " + product["source"],
                      "- Product grouping: " + ("implicit (not a confirmed product)"
                                                if product["implicit"] else "configured"),
                      "- Explicit project: " + (product["project"] or "unknown"),
                      "- Product goal: " + (product["goal"] or "unknown"),
                      "- Product responsibilities: unknown",
                      "- Product exclusions: unknown", ""])
        for evidence in product.get("evidence") or []:
            lines.extend(_evidence_lines(evidence))
        for ws in [w for w in report["workstreams"]
                   if w["product"] == product["abbrev"]]:
            lines.extend(["#### {} ({})".format(ws["name"], ws["abbrev"]), "",
                          "- Source: " + ws["source"],
                          "- Jira project: {} (from {})".format(
                              ws["project"] or "unknown", ws["project_origin"]),
                          "- Membership rule: {} {}".format(
                              ws["anchor_mode"], ", ".join(ws["anchors"]) or
                              ("legacy JQL configured" if ws["legacy_jql_configured"]
                               else "unknown")),
                          "- Purpose: unknown",
                          "- Responsibilities: unknown",
                          "- Exclusions / boundaries: unknown",
                          "- Review state: not established", ""])
            for evidence in ws.get("evidence") or []:
                lines.extend(_evidence_lines(evidence))
    if "clarifications" in report:
        lines.extend(["## Clarification queue (unconfirmed)", "",
                      "Questions are based on missing confirmed definitions. "
                      "Supporting sources are examples, not verified decisions.", ""])
        for i, item in enumerate(report["clarifications"], 1):
            lines.extend(["### {}. {} ({})".format(
                i, item["entity"], item["abbrev"]), "",
                "- Question: " + item["question"],
                "- Missing definition: " + item["field"],
                "- Reason: " + item["basis"],
                "- Source state: " + item["source_state"]])
            if item.get("references"):
                lines.append("- Example references: " + ", ".join(item["references"]))
            lines.append("- Decision: **needs review**")
            lines.append("")
    lines.extend(["## Scope and limitations", "",
                  "- Source references above describe where configured facts came from, "
                  "not evidence of verified product responsibilities.",
                  ("- Source availability and timestamps are shown where retrieved; "
                   "Jira Epic examples are bounded and not exhaustive."
                   if report.get("enriched") else
                   "- No linked documents were read, and their availability or freshness "
                   "was not checked."),
                  "- Missing descriptions and boundaries are unknown, not inferred "
                  "from product names, components, or labels.",
                  "- No issue classifications or configuration changes are proposed.",
                  ""])
    return "\n".join(lines)
