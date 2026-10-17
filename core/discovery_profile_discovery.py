"""Offline candidate product/workstream discovery, independent of configured taxonomy.

Evidence is selected from the existing authorized FTS store and Jira inventory.
Names and descriptions are hypotheses: nothing changes configuration or source
records. Scope is always the chosen Jira project.
"""
import json
import math
import re
import sqlite3
from collections import Counter

from core import discovery_fts

CAPABILITY = re.compile(
    r"\b(?:purpose|objective|goal|provides?|consumes?|capabilit\w*|responsib\w*|"
    r"scope|boundar\w*|supports?|enables?|used by|out of scope|integrat\w*)\b", re.I)
HEADING = re.compile(
    r"\b(?P<label>Product|Workstream|Capability|Service)\s*(?:\d{1,2})?\s*:\s*"
    r"(?P<name>[A-Z][A-Za-z0-9][A-Za-z0-9 /&+().-]{2,65})", re.I)
END = re.compile(
    r"\s+(?:Owner|Purpose|Provides|Consumes|Used by|Scope|Responsibilities|"
    r"Boundaries|Outcomes|Dependencies)\s*:", re.I)
GENERIC = {"legacy", "other", "miscellaneous", "general", "none", "unassigned",
           "backlog", "development", "testing", "bug", "support", "documentation"}


def _normal(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def _name(value):
    name = re.sub(r"\s+", " ", str(value or "")).strip(" :;.,-")
    # Labels in a flattened page must not swallow the next labelled section.
    name = END.split(name, maxsplit=1)[0].strip(" :;.,-")
    name = re.split(r"\\s+(?:High-Level Objective|High Level Objective|Owner|Purpose|Provides|Consumes|Used by|Together they)\\b", name, maxsplit=1, flags=re.I)[0].strip(" :;.,-")
    name = re.sub(r"\s+\((?:ITK|SDX|APS|P2P|ADR|BCDC)\)$", "", name)
    if not 3 <= len(name) <= 66 or _normal(name) in GENERIC:
        return None
    if len(name.split()) > 8 or name.isdigit():
        return None
    return name


def _passages(text, name, limit=3):
    """Return readable, bounded windows around exact full-name mentions."""
    raw = str(text or "")
    match_expr = re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)", re.I)
    found = []
    for match in match_expr.finditer(raw):
        left = max(0, match.start() - 260)
        right = min(len(raw), match.end() + 460)
        fragment = " ".join(raw[left:right].split())
        signal = len(CAPABILITY.findall(fragment))
        found.append((signal, -match.start(), fragment[:750]))
        if len(found) >= 25:
            break
    found.sort(reverse=True)
    return [item[2] for item in found[:limit]]


def _configured(cfg):
    names = {}
    for kind, key in (("product", "products"), ("workstream", "workstreams")):
        for entry in cfg.get(key) or []:
            name = _name(entry.get("name"))
            if name:
                names[_normal(name)] = {"name": name, "kind": kind}
    return names


def _components(db, project):
    """Count issue-level component assignments, never comments or changelogs."""
    try:
        cursor = db.execute(
            "SELECT issue_key, payload FROM jira_raw_issues WHERE project=?", (project,))
    except sqlite3.OperationalError:
        return {}
    counts = {}
    for key, raw in cursor:
        try:
            items = json.loads(raw).get("fields", {}).get("components") or []
        except (ValueError, TypeError, AttributeError):
            continue
        for name in {x.get("name", "").strip() for x in items
                     if isinstance(x, dict) and isinstance(x.get("name"), str)}:
            clean = _name(name)
            if not clean:
                continue
            record = counts.setdefault(_normal(clean), {
                "name": clean, "issues": set(), "citations": set()})
            record["issues"].add(key)
            if len(record["citations"]) < 3:
                record["citations"].add("jira:" + key)
    return counts


def _explicit_names(db, project):
    """Extract conservative labelled names from already indexed published pages."""
    found = {}
    rows = db.execute(
        """SELECT citation, title, body FROM discovery_fts_documents
           WHERE project=? AND source='confluence'
             AND kind IN ('confluence_page','confluence_blog','confluence_blogpost')
           ORDER BY citation""", (project,))
    for citation, title, body in rows:
        for match in HEADING.finditer((title or "") + "\n" + (body or "")):
            name = _name(match.group("name"))
            if not name:
                continue
            kind = match.group("label").lower()
            record = found.setdefault(_normal(name), {
                "name": name, "labels": set(), "citations": set()})
            record["labels"].add(kind)
            record["citations"].add(citation)
    return found


def _evidence(db, project, names):
    """Choose distinct parent documents, preferring direct capability material.

    Only published Confluence page bodies and Jira issue bodies are primary
    profile evidence. A page may support multiple named candidates, but it
    is not multiplied by comment/changelog volume.
    """
    prepared = {
        key: {"name": row["name"],
              "expression": re.compile(r"(?<!\w)" + re.escape(row["name"]) + r"(?!\w)", re.I),
              "documents": {}}
        for key, row in names.items()
    }
    rows = db.execute(
        """SELECT source, kind, source_key, citation, title, body
           FROM discovery_fts_documents
           WHERE project=? AND (
             (source='confluence' AND kind IN
               ('confluence_page','confluence_blog','confluence_blogpost'))
             OR (source='jira' AND kind='issue'))
           ORDER BY citation""", (project,))
    for source, kind, source_key, citation, title, body in rows:
        header = str(title or "")
        content = str(body or "")
        for key, prepared_row in prepared.items():
            matcher = prepared_row["expression"]
            if not matcher.search(header) and not matcher.search(content):
                continue
            passages = _passages(content, prepared_row["name"], limit=2)
            if not passages:
                passages = [header[:500]]
            # A named primary source is stronger than a merely related issue.
            signal = max((len(CAPABILITY.findall(p)) for p in passages), default=0)
            title_hit = bool(matcher.search(header))
            class_rank = 0 if source == "confluence" else 1
            score = (class_rank, -int(title_hit), -min(signal, 10), citation)
            if source == "jira":
                grouping = "jira:" + str(source_key)
            else:
                grouping = "confluence:" + str(source_key)
            record = {"citation": citation, "source": source, "kind": kind,
                      "title": header[:160], "excerpt": passages[0],
                      "score": score}
            previous = prepared_row["documents"].get(grouping)
            if previous is None or score < previous["score"]:
                prepared_row["documents"][grouping] = record
    return prepared


def _reconcile(candidate, cfg):
    configured = _configured(cfg)
    named = configured.get(_normal(candidate["name"]))
    if not named:
        return {"status": "not_configured", "configured_kind": None}
    labels = candidate["observed_labels"]
    conflict = bool(labels and named["kind"] not in labels and
                    ({"product", "workstream", "capability", "service"} & set(labels)))
    return {"status": "kind_conflict" if conflict else "configured_match",
            "configured_kind": named["kind"]}


def discover(db_path, cfg, project, max_candidates=40, evidence_per_candidate=5):
    """Offline candidate inventory, all candidates unconfirmed and cited."""
    if not project:
        raise ValueError("A Jira project is required for offline profile discovery")
    if max_candidates < 1 or evidence_per_candidate < 1:
        raise ValueError("Discovery limits must be positive")
    db = sqlite3.connect(str(db_path))
    try:
        discovery_fts._init(db)
        names = {}
        configured = _configured(cfg)
        for key, item in configured.items():
            names[key] = {"name": item["name"], "configured_kind": item["kind"],
                          "sources": set(), "component_issues": 0, "labels": set(),
                          "seed_citations": set()}
            names[key]["sources"].add("configuration")
        components = _components(db, project)
        for key, item in components.items():
            entry = names.setdefault(key, {
                "name": item["name"], "configured_kind": None,
                "sources": set(), "component_issues": 0, "labels": set(),
                "seed_citations": set()})
            entry["sources"].add("jira_component")
            entry["component_issues"] = len(item["issues"])
            entry["seed_citations"].update(item["citations"])
        explicit = _explicit_names(db, project)
        for key, item in explicit.items():
            entry = names.setdefault(key, {
                "name": item["name"], "configured_kind": None,
                "sources": set(), "component_issues": 0, "labels": set(),
                "seed_citations": set()})
            entry["sources"].add("confluence_label")
            entry["labels"].update(item["labels"])
            entry["seed_citations"].update(item["citations"])
        # Reject component-only singletons. Configuration is a search hint,
        # never evidence of owning a capability.
        names = {
            key: value for key, value in names.items()
            if value["sources"] != {"jira_component"} or value["component_issues"] >= 2
        }
        prepared = _evidence(db, project, names)
        all_candidates = []
        for key, entry in names.items():
            ranked = sorted(prepared[key]["documents"].values(), key=lambda x: x["score"])
            if not ranked:
                continue
            published = sum(1 for r in ranked if r["source"] == "confluence")
            jira = len(ranked) - published
            explicit_label = bool(entry["labels"])
            # Cap sheer volume so that popular but generic components cannot
            # overwhelm explicit, descriptive capability documentation.
            rank = (10 if explicit_label else 0) + (4 if published else 0) + (
                2 if entry["configured_kind"] else 0) + min(
                    5, math.log2(1 + entry["component_issues"])) + min(3, jira)
            labels = sorted(entry["labels"])
            guess = (labels[0] if len(labels) == 1 else None)
            candidate = {
                "name": entry["name"], "project": project,
                "status": "unconfirmed", "observed_labels": labels,
                "candidate_kind": guess, "configured_kind": entry["configured_kind"],
                "found_via": sorted(entry["sources"]),
                "component_issue_count": entry["component_issues"],
                "published_documents": published, "jira_issues": jira,
                "source_count": len(ranked),
                "seed_citations": sorted(entry["seed_citations"])[:6],
                "evidence": [{k: v for k, v in row.items() if k != "score"}
                             for row in ranked[:evidence_per_candidate]],
                "score": round(rank, 2)}
            candidate["reconciliation"] = _reconcile(candidate, cfg)
            all_candidates.append(candidate)
        all_candidates.sort(key=lambda x: (-x["score"], -x["published_documents"],
                                            -x["source_count"], x["name"].casefold()))
        return {"project": project, "total_candidates": len(all_candidates),
                "candidates": all_candidates[:max_candidates],
                "unreviewed_candidates": max(0, len(all_candidates) - max_candidates),
                "discovery_method": "labelled_confluence_and_jira_components",
                "model_review": None, "config_unchanged": True,
                "notes": [
                    "Names, observed labels and membership are unconfirmed.",
                    "Components do not establish product ownership.",
                    "Only indexed published page bodies and Jira issues provide primary evidence.",
                    "Candidates beyond the display cap are not yet included in this report.",
                ]}
    finally:
        db.close()
