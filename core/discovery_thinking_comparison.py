"""Controlled comparison of concept classification with thinking disabled/enabled.

Uses identical candidate edges and bypasses response cache to avoid mode leakage.
Results remain unconfirmed. This does not establish model thinking capability.
"""
import time

from core import discovery_local_model


def compare(graph, cfg, max_edges=8):
    if max_edges < 1:
        raise ValueError("max_edges must be positive")
    base = dict(cfg.get("model") or {})
    if not base.get("endpoint") or not base.get("name"):
        raise ValueError("Local model endpoint and name are required")
    edges = list(graph.get("relationships") or [])[:max_edges]
    outputs = {"off": [], "on": []}
    stats = {}
    for label, thinking in (("off", False), ("on", True)):
        model_cfg = dict(base, enable_thinking=thinking)
        started = time.monotonic()
        for edge in edges:
            try:
                judgement = discovery_local_model.classify(
                    edge, model_cfg, use_cache=False)
            except (ValueError, TypeError, KeyError, IndexError, OSError) as exc:
                judgement = {"status": "model_error", "type": "unresolved",
                             "citations": [], "error": str(exc)[:200]}
            outputs[label].append(judgement)
        stats[label] = {
            "valid": sum(x.get("status") != "model_error" for x in outputs[label]),
            "repaired": sum(x.get("repair_attempted") is True for x in outputs[label]),
            "failures": sum(x.get("status") == "model_error" for x in outputs[label]),
            "seconds": round(time.monotonic() - started, 2),
        }
    comparisons = []
    for edge, off, on in zip(edges, outputs["off"], outputs["on"]):
        comparisons.append({
            "from": edge["from"], "to": edge["to"],
            "project": edge["project"],
            "evidence_citations": [x["citation"] for x in (edge.get("evidence") or [])[:8]],
            "off": off, "on": on,
        })
    return {
        "model_name": base["name"],
        "reviewed": len(comparisons),
        "total_edges": len(graph.get("relationships") or []),
        "modes": stats,
        "different_types": sum(
            item["off"].get("type") != item["on"].get("type") for item in comparisons),
        "comparisons": comparisons,
        "limitation": "Different outcomes are not proof of greater accuracy; manually assess evidence support.",
    }
