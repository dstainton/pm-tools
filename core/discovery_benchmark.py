"""Deterministic Phase 2A benchmark: no model calls or source-system access."""
import argparse
import json
import sys

ROLES = {"product", "service", "capability", "workstream", "team",
         "stakeholder", "initiative", "decision", "source_document",
         "source_section", "jira_issue", "jira_component"}
PREDICATES = {"provides", "depends_on", "part_of", "used_by", "owned_by",
              "implements", "tracked_by", "historical_name", "replaces",
              "contradicts", "has_purpose", "has_boundary"}
POLARITIES = {"positive", "negative"}
MODALITIES = {"actual", "planned", "proposed", "historical", "unknown"}


def _require(test, msg):
    if not test:
        raise ValueError(msg)


def _norm(value):
    return " ".join(value.lower().split())


def _entity_key(row):
    return (row["id"], _norm(row["name"]), tuple(sorted(row["roles"])))


def _claim_key(row):
    return (row["subject_id"], row["predicate"], _norm(row["object"]),
            row["polarity"], row["modality"])


def _validate_entities(rows, case_id):
    _require(isinstance(rows, list), case_id + ": entities must be array")
    ids = set()
    for item in rows:
        _require(isinstance(item, dict), case_id + ": invalid entity")
        _require(all(isinstance(item.get(k), str) and item[k].strip()
                     for k in ("id", "name")), case_id + ": entity requires id/name")
        roles = item.get("roles")
        _require(isinstance(roles, list) and bool(roles) and
                 set(roles) <= ROLES and len(set(roles)) == len(roles),
                 case_id + ": invalid entity roles")
        _require(item["id"] not in ids, case_id + ": duplicate entity ID")
        ids.add(item["id"])
    return ids


def _validate_claims(rows, ids, case_id, source=None):
    _require(isinstance(rows, list), case_id + ": claims must be array")
    for item in rows:
        _require(isinstance(item, dict), case_id + ": invalid claim")
        _require(item.get("subject_id") in ids,
                 case_id + ": claim subject not in entity IDs")
        _require(item.get("predicate") in PREDICATES, case_id + ": unknown predicate")
        _require(isinstance(item.get("object"), str) and bool(item["object"].strip()),
                 case_id + ": missing claim object")
        _require(item.get("polarity") in POLARITIES, case_id + ": invalid polarity")
        _require(item.get("modality") in MODALITIES, case_id + ": invalid modality")
        quote = item.get("evidence_quote")
        _require(isinstance(quote, str) and bool(quote.strip()),
                 case_id + ": evidence_quote required")
        if source is not None:
            _require(item.get("citation") == source["citation"],
                     case_id + ": citation does not match reference source")
            _require(_norm(quote) in _norm(source["quote"]),
                     case_id + ": evidence_quote is not in the source span")


def _score(predicted, expected):
    actual = set(predicted)
    gold = set(expected)
    correct = len(actual & gold)
    return {"true_positive": correct, "false_positive": len(actual - gold),
            "false_negative": len(gold - actual)}


def _combine(parts):
    totals = {k: sum(item[k] for item in parts) for k in
              ("true_positive", "false_positive", "false_negative")}
    tp, fp, fn = (totals[k] for k in
                  ("true_positive", "false_positive", "false_negative"))
    totals["precision"] = (tp / (tp + fp)) if tp + fp else (1.0 if not fn else 0.0)
    totals["recall"] = (tp / (tp + fn)) if tp + fn else 1.0
    return totals


def evaluate(reference, predictions):
    _require(reference.get("schema_version") == 1 and
             predictions.get("schema_version") == 1, "Unsupported schema version")
    cases = reference.get("cases")
    outputs = predictions.get("predictions")
    _require(isinstance(cases, list) and bool(cases), "Empty/missing reference cases")
    _require(isinstance(outputs, list), "Missing predictions")
    known = {}
    for item in cases:
        cid = item.get("case_id")
        _require(isinstance(cid, str) and cid and cid not in known, "Invalid case ID")
        _require(item.get("split") in ("development", "holdout"),
                 cid + ": invalid split")
        _require(item.get("illustrative_only") is not True and
                 isinstance(item.get("reviewed_by"), str) and
                 bool(item["reviewed_by"].strip()) and
                 isinstance(item.get("reviewed_at"), str) and
                 bool(item["reviewed_at"].strip()),
                 cid + ": requires human-reviewed reference, not illustrative data")
        src = item.get("source")
        _require(isinstance(src, dict) and all(
            isinstance(src.get(k), str) and bool(src[k].strip())
            for k in ("project", "citation", "revision", "quote")),
            cid + ": source metadata incomplete")
        _require(all(isinstance(src.get(k), int) and src[k] >= 0
                     for k in ("start", "end")) and src["end"] > src["start"],
                 cid + ": invalid source span")
        expected = item.get("expected")
        _require(isinstance(expected, dict), cid + ": missing expected")
        ids = _validate_entities(expected.get("entities"), cid)
        _validate_claims(expected.get("claims"), ids, cid, source=src)
        known[cid] = item
    seen, entity_stats, claim_stats = set(), [], []
    for result in outputs:
        cid = result.get("case_id")
        _require(cid in known and cid not in seen, "Unknown/duplicate prediction case")
        seen.add(cid)
        ids = _validate_entities(result.get("entities"), cid)
        _validate_claims(result.get("claims"), ids, cid,
                         source=known[cid]["source"])
        expected = known[cid]["expected"]
        entity_stats.append(_score(map(_entity_key, result["entities"]),
                                   map(_entity_key, expected["entities"])))
        claim_stats.append(_score(map(_claim_key, result["claims"]),
                                  map(_claim_key, expected["claims"])))
    # Missing cases are scored as abstentions, not silently ignored.
    for cid in set(known) - seen:
        expected = known[cid]["expected"]
        entity_stats.append(_score([], map(_entity_key, expected["entities"])))
        claim_stats.append(_score([], map(_claim_key, expected["claims"])))
    return {"cases": len(known), "predicted_cases": len(seen),
            "coverage": len(seen)/len(known),
            "entities": _combine(entity_stats), "claims": _combine(claim_stats),
            "warning": "Tuple matching does not establish semantic entailment or citation support."}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Review-labelled PM discovery benchmark")
    parser.add_argument("command", choices=["evaluate"])
    parser.add_argument("--reference", required=True)
    parser.add_argument("--predictions", required=True)
    args = parser.parse_args(argv)
    try:
        with open(args.reference, encoding="utf-8") as stream:
            ref = json.load(stream)
        with open(args.predictions, encoding="utf-8") as stream:
            pred = json.load(stream)
        print(json.dumps(evaluate(ref, pred), indent=2))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print("Benchmark invalid: {}".format(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
