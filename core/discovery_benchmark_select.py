"""Build a PRIVATE, unreviewed benchmark candidate pack from the offline index.

This is *sampling* rather than model-generated ground truth. It never
sends data to Jira, Confluence, a model, or GitHub.
"""
import argparse
import json
import os
import sqlite3
from pathlib import Path

BUCKETS = (
    ("service-definitions", ("Capability 1:", "Capability 2:", "Capability 3:",
                             "Capability 4:", "What it IS", "What it is NOT"), 5),
    ("p2p", ("Secure Data Exchange", "SDX", "P2P", "privacy zone",
             "token exchange"), 5),
    ("platform", ("APS Platform", "API Gateway", "API Directory",
                   "API Services Portal", "Kong"), 4),
    ("toolkit", ("Integration Toolkit", "ITK", "DevHub", "Backstage"), 4),
    ("decisions-and-dependencies", ("decision", "superseded", "depends on",
                                     "out of scope", "SSO", "ADR"), 4),
    ("negative-or-ambiguous", ("interest-holder", "research", "operational",
                               "component", "https"), 4),
)


def _source_labels(db, project, source, source_key):
    if source != "jira":
        return {"label_status": "not_indexed"}
    try:
        row = db.execute(
            "SELECT payload FROM jira_raw_issues WHERE project=? AND issue_key=?",
            (project, source_key)).fetchone()
    except sqlite3.OperationalError:
        row = None
    if not row:
        return {"label_status": "not_available"}
    try:
        fields = json.loads(row[0]).get("fields") or {}
        labels = fields.get("labels")
    except (ValueError, TypeError, AttributeError):
        return {"label_status": "unreadable"}
    if not isinstance(labels, list):
        return {"label_status": "not_available"}
    return {"jira_labels": sorted(set(str(x) for x in labels if x)),
            "label_status": "available"}


def _best_span(body, terms, radius=1000):
    lowered = body.casefold()
    offsets = [(lowered.find(term.casefold()), term) for term in terms]
    offsets = [(n, term) for n, term in offsets if n >= 0]
    if not offsets:
        return 0, min(len(body), 2 * radius)
    # Prefer descriptive mentions that anchor meaningful evidence.
    anchors = ("What it IS", "What it is NOT", "depends on",
               "out of scope", "decision", "Capability ")
    preferred = [(n, term) for n, term in offsets
                 if any(term.casefold().startswith(a.casefold()) for a in anchors)]
    at = min(preferred or offsets, key=lambda v: v[0])[0]
    start = max(0, at - radius // 2)
    return start, min(len(body), at + radius * 2)


def select(db_path, project, target=26):
    if not 6 <= target <= 100:
        raise ValueError("target must be from 6 to 100")
    db = sqlite3.connect(str(db_path))
    try:
        # Read-only: no FTS migrations or table creation.
        rows = db.execute(
            """SELECT source,source_key,citation,title,body,digest,updated_at,kind
               FROM discovery_fts_documents
               WHERE project=? AND (
                 (source='confluence' AND kind IN
                  ('confluence_page','confluence_blogpost','confluence_blog'))
                 OR (source='jira' AND kind='issue'))
               ORDER BY citation""", (project,)).fetchall()
        sources = []
        for source, key, citation, title, body, digest, updated, kind in rows:
            if not body:
                continue
            # Distinguish narrative from short tag-only Jira issue bodies.
            meaningful = len(body.strip()) >= (120 if source == "jira" else 160)
            sources.append({"source": source, "source_key": key,
                            "citation": citation, "title": title, "body": body,
                            "digest": digest, "updated": updated, "kind": kind,
                            "meaningful": meaningful})
        # Allocate separate quotas so narrative Confluence pages cannot crowd
        # out Jira issue evidence. Scarcity is reported, never backfilled with
        # unrelated sources to make a numeric target appear complete.
        jira_target = max(2, target // 3)
        confluence_target = target - jira_target
        quotas = {"jira": jira_target, "confluence": confluence_target}
        per_source = {"jira": 0, "confluence": 0}
        picked, used = [], set()
        for bucket, terms, count in BUCKETS:
            for source_type in ("confluence", "jira"):
                # Bucket quotas are proportional but do not force all buckets
                # to contain both sources when a category has no relevant issues.
                bucket_limit = max(1, round(count * quotas[source_type] / target))
                scored = []
                for row in sources:
                    if row["source"] != source_type or row["citation"] in used:
                        continue
                    title = row["title"].casefold()
                    body = row["body"].casefold()
                    matches = sum(term.casefold() in body or term.casefold() in title
                                  for term in terms)
                    if not matches:
                        continue
                    positive = sum(x in body for x in (
                        "what it is", "purpose", "provides", "depends on",
                        "responsib", "out of scope", "does not", "decision"))
                    warning = sum(x in title for x in (
                        "archived", "draft", "questionnaire", "assessment",
                        "sprint goals", "meeting notes"))
                    rank = (matches * 2 + min(positive, 4) * 3
                            + (3 if row["meaningful"] else -6)
                            - warning * 6)
                    scored.append((-rank, row["citation"], row))
                scored.sort()
                allowed = min(bucket_limit, max(0, quotas[source_type] -
                                              per_source[source_type]))
                for _, _, row in scored[:allowed]:
                    picked.append((bucket, terms, row))
                    used.add(row["citation"])
                    per_source[source_type] += 1
        # Fill remaining quotas with highest-quality eligible documents,
        # without reusing citations or allowing one source to displace another.
        for source_type in ("confluence", "jira"):
            if per_source[source_type] >= quotas[source_type]:
                continue
            remaining = []
            for row in sources:
                if row["source"] != source_type or row["citation"] in used:
                    continue
                if not row["meaningful"]:
                    continue
                body = row["body"].casefold()
                title = row["title"].casefold()
                mentions = sum(x in body for x in (
                    "secure data exchange", "aps platform", "integration toolkit",
                    "api directory", "api gateway", "token exchange"))
                substantive = sum(x in body for x in (
                    "provides", "purpose", "depends on", "does not",
                    "out of scope", "responsib", "decision"))
                if mentions == 0 or substantive == 0:
                    continue
                deprecated = sum(x in title for x in (
                    "archived", "questionnaire", "accessibility assessment"))
                rank = mentions * 2 + min(substantive, 4) * 3 - deprecated * 10
                remaining.append((-rank, row["citation"], row))
            remaining.sort()
            for _, _, row in remaining[:quotas[source_type] - per_source[source_type]]:
                picked.append(("additional-evidence", ("provides", "depends on",
                               "purpose", "Secure Data Exchange"), row))
                used.add(row["citation"])
                per_source[source_type] += 1
        # No padding with unsupported classifications. Report coverage shortfall.
        cases = []
        for n, (bucket, terms, row) in enumerate(picked, 1):
            start, end = _best_span(row["body"], terms)
            source_info = {
                "project": project, "citation": row["citation"],
                "revision": row["digest"], "start": start, "end": end,
                "quote": row["body"][start:end],
                "title": row["title"], "kind": row["kind"],
                "updated_at": row["updated"],
            }
            source_info.update(_source_labels(
                db, project, row["source"], row["source_key"]))
            cases.append({
                "case_id": "candidate-{:03d}".format(n),
                "split": "unassigned",
                "bucket": bucket,
                "illustrative_only": True,
                "review_status": "pending_human_annotation",
                "source": source_info,
                "expected": {"entities": [], "claims": []},
                "review_questions": [
                    "Is this a real product, service, capability, workstream, or a negative example?",
                    "What exact quote supports each proposed entity and claim?",
                    "Are any labels informative, misleading, missing or historical?",
                    "What is planned, operational, excluded or superseded?",
                ],
            })
        return {"schema_version": 1, "project": project, "requested": target,
                "selected": len(cases), "source_counts": per_source,
                "source_targets": quotas, "cases": cases,
                "review_status": "NOT_GROUND_TRUTH",
                "warning": "Unreviewed PRIVATE source extracts; not accepted benchmark annotations."}
    finally:
        db.close()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Create a private, unreviewed APS benchmark candidate pack")
    parser.add_argument("--db", required=True, help="Existing local SQLite evidence index")
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", required=True, help="Private local JSON output")
    parser.add_argument("--target", type=int, default=26)
    args = parser.parse_args(argv)
    output = Path(args.output).expanduser().resolve()
    if output.exists():
        parser.error("output exists; refusing to overwrite a previous review pack")
    try:
        result = select(args.db, args.project, args.target)
        output.parent.mkdir(parents=True, exist_ok=True)
        # Refuse symlinks and best-effort owner-only file permissions.
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        with os.fdopen(os.open(str(output), flags, 0o600), "w", encoding="utf-8") as file:
            json.dump(result, file, indent=2, ensure_ascii=False)
        print("Selected {} unreviewed local source excerpts: {}".format(
            result["selected"], output))
        print("No human-reviewed reference answers have been created.")
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
