"""Local embedding-based broad taxonomy classifier for already indexed evidence.

Classifier does not use keyword gates: every in-scope source observation
is processed, including title-only issues. The result is a ranking of
semantic categories, not a calibrated probability or verified assertion.
"""
import argparse
import hashlib
import json
import math
import sqlite3
from pathlib import Path

import requests

from core.config import SECTION_DEFAULTS, load_config

TAXONOMY = {
    "organization": "Evidence describing organizational structure, products, services, workstreams, teams, ownership and accountabilities.",
    "capabilities": "Evidence describing functionality, capabilities, service responsibilities, constraints and exclusions.",
    "architecture": "Evidence describing software architecture, APIs, interoperability, protocols, systems and integration patterns.",
    "governance": "Evidence describing rules, standards, privacy, authorization policy, compliance and governance.",
    "delivery": "Evidence describing planned work, sprint delivery, defects, operations, maintenance, timelines and milestones.",
    "relationships": "Evidence describing dependencies, consumers, providers, ownership, hierarchy and interactions among services or teams.",
    "decisions": "Evidence describing decisions, rejected alternatives, proposals, lifecycle changes, supersession and historical context.",
    "other": "Evidence with no clear connection to organizational knowledge or work, or insufficient context to determine a category.",
}


def _prefix(content, task):
    if task not in ("classification", "clustering"):
        raise ValueError("task must be classification or clustering")
    return "task: {} | query: {}".format(task, content)


def _cosine(a, b):
    if len(a) != len(b) or not a:
        raise ValueError("Embedding dimensions differ or embedding is empty")
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
    if not norm or not math.isfinite(dot / norm):
        raise ValueError("Invalid embedding magnitude")
    return dot / norm


def _embeddings(endpoint, model, texts, timeout):
    """Send one input per request for FLM backends without reliable batching."""
    output = []
    for value in texts:
        result = requests.post(endpoint, json={
            "model": model, "input": value, "encoding_format": "float"
        }, timeout=timeout)
        result.raise_for_status()
        data = result.json().get("data")
        if not isinstance(data, list) or len(data) != 1:
            raise ValueError("Expected one embedding per request")
        vector = data[0].get("embedding")
        if (not isinstance(vector, list) or not vector or
                not all(isinstance(x, (int, float)) and math.isfinite(x)
                        for x in vector)):
            raise ValueError("Malformed embedding response")
        output.append(vector)
    return output

def _init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS discovery_classifications (
        doc_id TEXT NOT NULL, classifier_key TEXT NOT NULL,
        source_digest TEXT NOT NULL, categories_json TEXT NOT NULL,
        PRIMARY KEY (doc_id, classifier_key))""")


def classify(db_path, project, endpoint=None, model=None, task=None,
             batch_size=None, timeout=None, limit=None, on_progress=None,
             taxonomy_version=None):
    defaults = SECTION_DEFAULTS["classification"]
    endpoint = endpoint or defaults["endpoint"]
    model = model or defaults["model"]
    task = task or defaults["task"]
    batch_size = batch_size or defaults["batch_size"]
    timeout = timeout or defaults["timeout"]
    if not endpoint.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise ValueError("Classification endpoint must be a local loopback URL")
    if not 1 <= batch_size <= 64:
        raise ValueError("batch_size must be 1..64")
    taxonomy_version = taxonomy_version or defaults["taxonomy_version"]
    labels = list(TAXONOMY)
    classifier_key = hashlib.sha256(json.dumps(
        [model, endpoint, task, taxonomy_version, TAXONOMY],
        sort_keys=True).encode("utf-8")).hexdigest()
    db = sqlite3.connect(str(db_path))
    try:
        _init(db)
        rows = db.execute("""SELECT doc_id, title, body, digest, citation, kind
            FROM discovery_fts_documents WHERE project=? ORDER BY doc_id""",
            (project,)).fetchall()
        if limit is not None:
            if limit < 1:
                raise ValueError("limit must be positive")
            rows = rows[:limit]
        cached = db.execute("""SELECT doc_id, source_digest
            FROM discovery_classifications WHERE classifier_key=?""",
            (classifier_key,)).fetchall()
        known = dict(cached)
        pending = [r for r in rows if known.get(r[0]) != r[3]]
        if not pending:
            return {"total": len(rows), "classified": 0, "cached": len(rows),
                    "failed": 0, "model": model, "taxonomy_version": taxonomy_version}
        prototype_texts = [_prefix("Category {}: {}".format(x, TAXONOMY[x]), task)
                           for x in labels]
        prototypes = _embeddings(endpoint, model, prototype_texts, timeout)
        count = failures = 0
        for at in range(0, len(pending), batch_size):
            batch = pending[at:at + batch_size]
            inputs = []
            for doc_id, title, body, digest, citation, kind in batch:
                # Titles are a separate metadata signal, clearly labelled.
                content = "Title: {}\nEvidence: {}".format(title, body) if body.strip() else (
                    "Title only, no description: {}".format(title))
                inputs.append(_prefix(content, task))
            try:
                vectors = _embeddings(endpoint, model, inputs, timeout)
            except (requests.RequestException, ValueError):
                # A failed request leaves units unclassified, eligible for retry.
                failures += len(batch)
                if on_progress:
                    on_progress(count, failures)
                continue
            with db:
                for record, vector in zip(batch, vectors):
                    scored = sorted(
                        ((label, _cosine(vector, proto)) for label, proto
                         in zip(labels, prototypes)),
                        key=lambda item: (-item[1], item[0]))
                    # Do not treat raw similarity as a calibrated probability.
                    result = {
                        "ranked_categories": [{"name": cat, "similarity": round(score, 6)}
                                              for cat, score in scored],
                        "top_categories": [cat for cat, score in scored[:2]],
                        "uncalibrated": True,
                        "title_only": not bool(record[2].strip()),
                        "citation": record[4], "kind": record[5],
                    }
                    db.execute("""INSERT OR REPLACE INTO discovery_classifications
                        (doc_id,classifier_key,source_digest,categories_json)
                        VALUES (?,?,?,?)""",
                        (record[0], classifier_key, record[3], json.dumps(result)))
                    count += 1
            if on_progress:
                on_progress(count, failures)
        return {"total": len(rows), "classified": count,
                "cached": len(rows) - len(pending), "failed": failures,
                "model": model, "taxonomy_version": taxonomy_version,
                "classification_key": classifier_key}
    finally:
        db.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Classify local source evidence with EmbeddingGemma")
    parser.add_argument("--db", required=True)
    parser.add_argument("--config", help="pm-tools YAML config with classification section")
    parser.add_argument("--project", required=True)
    parser.add_argument("--endpoint")
    parser.add_argument("--model")
    parser.add_argument("--task", choices=("clustering", "classification"))
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--limit", type=int, help="Optional bounded smoke test")
    args = parser.parse_args(argv)
    cfg = (load_config(args.config).get("classification")
           if args.config else SECTION_DEFAULTS["classification"])
    report = classify(args.db, args.project,
                      endpoint=args.endpoint or cfg["endpoint"],
                      model=args.model or cfg["model"],
                      task=args.task or cfg["task"],
                      batch_size=args.batch_size or cfg["batch_size"],
                      timeout=cfg["timeout"],
                      taxonomy_version=cfg["taxonomy_version"], limit=args.limit)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
