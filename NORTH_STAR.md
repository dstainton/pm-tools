# pm-tools North Star

## Purpose

pm-tools is a local-first product-management assistant that helps product managers understand their products, recover and sustain healthy backlogs, make evidence-based decisions, and communicate progress with less administrative effort.

It should bring the next useful fact, question, or proposed action to the product manager rather than making them repeatedly search Jira and other systems. It supports product judgement; it does not replace it.

## Who it serves

Primarily a product manager working with Jira and, optionally, Confluence and SharePoint. It must be useful to someone joining an unfamiliar team whose backlog is stale, incompletely classified, or inconsistently maintained, as well as someone operating an established product.

## Jobs to be done

1. **Understand:** Discover the complete product and delivery picture, including work outside existing workstream filters.
2. **Recover:** Assess an inherited backlog, identify uncertainty and hygiene problems, recommend classification and remediation, and retain human control of changes.
3. **Steward:** Keep backlog health, product commitments, risks, and decisions visible over time.
4. **Decide:** Connect needs and evidence to strategy, priorities, trade-offs, and measurable outcomes.
5. **Communicate:** Prepare concise, traceable updates for teams, stakeholders, and leadership.

## Product principles

- **Product value before Jira hygiene.** A perfectly formatted issue is not evidence that the work is worthwhile. Judge completeness against the item's maturity.
- **Facts and inferences stay distinct.** Deterministic calculations and source facts must not be replaced or embellished by model output. Show evidence, provenance, uncertainty, and missing data.
- **Incomplete data is normal.** Missing component, label, estimate, parent, or stale content is a condition to understand, not a reason to omit the issue or manufacture a value.
- **Useful before fully configured.** Begin with the available Jira project, then refine product and workstream boundaries progressively. Avoid requiring users to know the answers setup is meant to discover.
- **Low cognitive and administrative load.** Default to prioritized, actionable findings and small review batches. Do not make the manager memorize follow-ups or manually repeat work the tool can safely prepare.
- **Local-first and privacy-conscious.** Preserve existing local execution and model choices; treat retrieved Jira and document content as untrusted data. Avoid introducing hosted services or external disclosure without explicit approval.
- **Safe by default.** Reads and proposals are default. Writes must be previewed, explicitly approved, auditable, and checked for conflicts. No autonomous bulk closure or deletion.
- **Extend rather than duplicate.** Prefer shared retrieval, normalized facts, and existing commands over overlapping clients, pipelines, and reporting systems.
- **Explain the limits.** No false confidence in estimates, forecasts, model classifications, or data freshness.

## Reusable product knowledge

A local-first, source-grounded PM knowledge graph is the long-term shared foundation for discovery, dependency and roadmap analysis, decision history, risk, stakeholder insight and evidence-backed reporting. Preserve original sources, exact citations, temporal context and human approval. The graph supplements, not replaces, Jira/Confluence or the product manager's judgement. A GraphRAG implementation is a means, not the outcome: benchmark product-management accuracy before adopting infrastructure.

See [PM Knowledge Graph](docs/PM-KNOWLEDGE-GRAPH.md) and [Discovery Evaluation](docs/DISCOVERY-EVALUATION.md).

## What success looks like

A new product manager can connect Jira, establish an honest baseline, discover unclaimed and outdated work, review prioritized evidence-backed suggestions, and improve the backlog without losing history or control.

An established product manager can quickly see what changed, what needs a decision, why planned work matters, whether the delivery system is improving, and whether the product is delivering outcomes.

Development success means focused changes that improve those jobs, remain understandable, preserve compatibility where practical, and pass automated tests.

## Not the product

pm-tools is not a replacement for Jira, Confluence, or SharePoint; a general-purpose project-management suite; an autonomous issue-closing or prioritization authority; an agent software factory; an employee surveillance or individual productivity scoring system; or a mechanism for equating story-point throughput with product value.

A feature that doesn't advance the jobs above must be justified as a deliberate change to this North Star, not introduced opportunistically.
