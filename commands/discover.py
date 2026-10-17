"""Read-only discovery of configured products and workstreams."""
import json
from core import discovery, output, progress


def run(cfg, args):
    chosen = cfg.get("_workstreams")
    # Explicit selector is already applied by pm.py, but without selection
    # all declared products (including those with no workstreams) are visible.
    selected = chosen if (getattr(args, "product", None) or
                          getattr(args, "workstream", None)) else None
    report = discovery.inspect(cfg, selected=selected,
                               project=getattr(args, "project", None))
    if getattr(args, "inventory", False):
        from core import discovery_inventory
        progress.start("Inventorying configured Confluence scopes")
        report = discovery_inventory.build(cfg, report)
        progress.finish()
    if getattr(args, "jira_inventory", False):
        from core import discovery_jira_checkpoint
        from core import paths
        import os
        selected_project = getattr(args, "project", None)
        projects = ([selected_project] if selected_project else
                    [p.get("project") for p in (cfg.get("products") or [])] +
                    [w.get("project") or w.get("jira_project")
                     for w in (cfg.get("workstreams") or [])] +
                    [(cfg.get("jira") or {}).get("project")])
        projects = list(dict.fromkeys(str(p) for p in projects if p))
        db_file = os.path.join(paths.local_dir(cfg), "discovery_jira.sqlite")
        os.makedirs(os.path.dirname(db_file), exist_ok=True)
        progress.start("Collecting Jira inventory")
        try:
            report["jira_inventory"] = discovery_jira_checkpoint.crawl(
                cfg, projects, db_file)
        finally:
            progress.finish()
    if getattr(args, "jira_refresh", False):
        from core import discovery_jira_checkpoint
        from core import paths
        import os
        selected_project = getattr(args, "project", None)
        projects = ([selected_project] if selected_project else
                    [p.get("project") for p in (cfg.get("products") or [])] +
                    [w.get("project") or w.get("jira_project")
                     for w in (cfg.get("workstreams") or [])] +
                    [(cfg.get("jira") or {}).get("project")])
        projects = list(dict.fromkeys(str(p) for p in projects if p))
        db_file = os.path.join(paths.local_dir(cfg), "discovery_jira.sqlite")
        os.makedirs(os.path.dirname(db_file), exist_ok=True)
        progress.start("Refreshing Jira inventory")
        try:
            report["jira_refresh"] = discovery_jira_checkpoint.refresh(
                cfg, projects, db_file)
        finally:
            progress.finish()
    for flag, name, module_name, title in (
            ("jira_history", "jira_history", "discovery_jira_history",
             "Collecting Jira changelogs"),
            ("jira_comments", "jira_comments", "discovery_jira_comments",
             "Collecting Jira comments")):
        if not getattr(args, flag, False):
            continue
        from core import paths
        import importlib
        import os
        import time
        db_file = os.path.join(paths.local_dir(cfg), "discovery_jira.sqlite")
        if not os.path.exists(db_file):
            report[name] = {"coverage": "unavailable", "remaining": 0,
                            "completed": 0, "detail": "Run --jira-inventory first"}
            continue
        collector = importlib.import_module("core." + module_name)
        limit = getattr(args, "jira_limit", None)
        if limit is not None and limit <= 0:
            raise SystemExit("--jira-limit must be a positive number of issues.")
        previous_remaining = None
        total_completed = 0
        total_attempted = 0
        errors = []
        started = time.monotonic()
        import sqlite3
        with sqlite3.connect(db_file) as conn:
            initial_total = conn.execute(
                "SELECT COUNT(DISTINCT issue_key) FROM jira_raw_issues").fetchone()[0]
        progress.start(title)
        try:
            while True:
                def on_batch(current, batch_size):
                    count = total_attempted + current
                    estimated_total = max(initial_total, count + batch_size)
                    elapsed = max(0.001, time.monotonic() - started)
                    rate = count / elapsed
                    percent = 100 * count / estimated_total if estimated_total else 100
                    eta = (estimated_total - count) / rate if rate else 0
                    progress.note("{:,}/{:,} processed ({:.1f}%), {:.1f}/s, ETA {:.0f}s".format(
                        count, estimated_total, percent, rate, eta))
                batch_size = min(20, limit - total_attempted) if limit is not None else 20
                if batch_size <= 0:
                    break
                batch = collector.collect(cfg, db_file, max_issues=batch_size,
                                          on_progress=on_batch)
                total_attempted += batch["attempted"]
                total_completed += batch["completed"]
                errors.extend(batch.get("errors") or [])
                remaining = batch["remaining"]
                progress.note("{:,} completed, {:,} remaining".format(
                    total_completed, remaining))
                if remaining == 0 or batch["attempted"] == 0:
                    break
                if limit is not None and total_attempted >= limit:
                    break
                # A failed item must not be retried indefinitely in this invocation.
                if previous_remaining is not None and remaining >= previous_remaining:
                    break
                previous_remaining = remaining
            report[name] = {"coverage": "complete" if remaining == 0 else "partial",
                            "attempted": total_attempted, "completed": total_completed,
                            "remaining": remaining, "errors": errors}
            if errors:
                report[name]["detail"] = "{} failed requests; first: {} ({})".format(
                    len(errors), errors[0]["issue"], errors[0]["detail"])
            elif remaining and limit is not None and total_attempted >= limit:
                report[name]["detail"] = "Requested limit of {} attempts reached".format(limit)
            elif remaining and previous_remaining is not None and remaining >= previous_remaining:
                report[name]["detail"] = "Collection made no further progress"
        finally:
            progress.finish()
    if getattr(args, "jira_reconcile", False):
        from core import discovery_jira_reconcile
        from core import paths
        import os
        project = getattr(args, "project", None)
        projects = ([project] if project else
                    [p.get("project") for p in (cfg.get("products") or [])] +
                    [w.get("project") or w.get("jira_project")
                     for w in (cfg.get("workstreams") or [])] +
                    [(cfg.get("jira") or {}).get("project")])
        projects = list(dict.fromkeys(str(p) for p in projects if p))
        db_file = os.path.join(paths.local_dir(cfg), "discovery_jira.sqlite")
        if not os.path.exists(db_file):
            report["jira_reconcile"] = {"coverage": "unavailable", "projects": [],
                                        "detail": "Run --jira-inventory first"}
        else:
            progress.start("Reconciling Jira inventory")
            try:
                report["jira_reconcile"] = discovery_jira_reconcile.reconcile(
                    cfg, projects, db_file)
            finally:
                progress.finish()
    if getattr(args, "jira_structure", False):
        from core import discovery_jira_structure
        selected_project = getattr(args, "project", None)
        projects = ([selected_project] if selected_project else
                    [p.get("project") for p in (cfg.get("products") or [])] +
                    [w.get("project") or w.get("jira_project")
                     for w in (cfg.get("workstreams") or [])] +
                    [(cfg.get("jira") or {}).get("project")])
        progress.start("Inspecting Jira project configuration")
        try:
            report["jira_structure"] = discovery_jira_structure.inspect(
                cfg, [p for p in projects if p])
        finally:
            progress.finish()
    if (getattr(args, "index_jira", False) or getattr(args, "search_evidence", None)
            or getattr(args, "search_concept", None)):
        from core import discovery_fts, paths
        import os
        db_file = os.path.join(paths.local_dir(cfg), "discovery_jira.sqlite")
        if not os.path.isfile(db_file):
            raise SystemExit("Jira evidence database missing. Run --jira-inventory first.")
        if getattr(args, "index_jira", False):
            progress.start("Indexing collected Jira evidence offline")
            try:
                report["jira_index"] = discovery_fts.index_jira(
                    db_file, on_progress=lambda processed:
                    progress.note("{:,} Jira issues indexed".format(processed)))
            finally:
                progress.finish()
        if getattr(args, "search_concept", None):
            from core import discovery_concepts
            report["concept_matches"] = discovery_concepts.search_concept(
                db_file, args.search_concept, project=getattr(args, "project", None))
        if getattr(args, "search_evidence", None):
            report["evidence_matches"] = discovery_fts.search(
                db_file, args.search_evidence,
                project=getattr(args, "project", None))
    if getattr(args, "confluence_crawl", False):
        from core import discovery_confluence_checkpoint, paths
        import os
        db_file = os.path.join(paths.local_dir(cfg), "discovery_jira.sqlite")
        progress.start("Crawling Confluence scopes")
        def show_crawl(item):
            progress.note("[{}/{}] {}: {} ({} this run, offset {})".format(
                item["index"], item["total"], item["name"], item["status"],
                item["processed"], item["offset"]))
        try:
            # The combined crawl+index request is an explicit full-source
            # operation. Resume checkpoint pages until all authorized scopes
            # are complete or collection stops making forward progress.
            # Larger bounded rounds avoid resolving each page-tree root after
            # every four HTTP pages. Total combined cap remains 20,000 rows.
            rounds = 40 if getattr(args, "index_confluence", False) else 1
            previous = None
            for _ in range(rounds):
                batch = discovery_confluence_checkpoint.crawl(
                    cfg, db_file, max_rows=500 if rounds > 1 else 100,
                    on_progress=show_crawl)
                report["confluence_crawl"] = batch
                if not batch or all(row["status"] == "complete" for row in batch):
                    break
                state = tuple((str(row.get("scope")), row.get("offset", 0),
                               row["status"]) for row in batch)
                if state == previous:
                    break
                previous = state
        finally:
            progress.finish()
    if getattr(args, "index_confluence", False):
        from core import discovery_confluence_index, paths
        import os
        db_file = os.path.join(paths.local_dir(cfg), "discovery_jira.sqlite")
        progress.start("Indexing scoped Confluence page content")
        try:
            report["confluence_index"] = discovery_confluence_index.index(cfg, db_file)
        finally:
            progress.finish()
    if (getattr(args, "discover_profiles", False)
            or getattr(args, "discover_profiles_model", False)):
        from core import discovery_profile_discovery, paths
        import os
        db_file = os.path.join(paths.local_dir(cfg), "discovery_jira.sqlite")
        if not os.path.isfile(db_file):
            raise SystemExit("Local evidence index missing; index Jira or Confluence first.")
        scope = getattr(args, "project", None) or (cfg.get("jira") or {}).get("project")
        if not scope:
            raise SystemExit("--project is required when no default Jira project is configured.")
        progress.start("Discovering candidate profiles from indexed evidence")
        try:
            report["profile_discovery"] = discovery_profile_discovery.discover(
                db_file, cfg, project=scope,
                max_candidates=getattr(args, "profile_max_candidates", 40))
        finally:
            progress.finish()
        if getattr(args, "discover_profiles_model", False):
            from core import discovery_profile_model
            progress.start("Extracting source-cited profile claims with local model")
            try:
                discovery_profile_model.review(
                    report["profile_discovery"], cfg,
                    max_candidates=getattr(args, "profile_model_limit", 6))
            finally:
                progress.finish()
    if (getattr(args, "concept_graph", False) or getattr(args, "concept_graph_model", False)
            or getattr(args, "concept_graph_thinking_compare", False)):
        from core import discovery_concept_graph, paths
        import os
        db_file = os.path.join(paths.local_dir(cfg), "discovery_jira.sqlite")
        if not os.path.isfile(db_file):
            raise SystemExit("Local evidence index missing; index Jira or Confluence first.")
        progress.start("Discovering typed concept relationships")
        try:
            report["concept_graph"] = discovery_concept_graph.discover(
                db_file, project=getattr(args, "project", None))
            from core import discovery_profile_leads
            report["profile_leads"] = discovery_profile_leads.build(
                db_file, cfg, project=getattr(args, "project", None))
        finally:
            progress.finish()
    if (getattr(args, "concept_graph_model", False)
            or getattr(args, "concept_graph_thinking_compare", False)):
        from core import discovery_local_model
        progress.start("Reviewing source-cited relationships with local model")
        try:
            from core import discovery_contextual_candidates
            contextual = discovery_contextual_candidates.candidates(
                db_file, project=getattr(args, "project", None), limit=None)
            report["contextual_candidates"] = contextual
            existing = report["concept_graph"]["relationships"]
            seen = {(e["project"], frozenset((e["from"].casefold(), e["to"].casefold())))
                    for e in existing}
            extra = [e for e in contextual if
                     (e["project"], frozenset((e["from"].casefold(), e["to"].casefold())))
                     not in seen]
            review_graph = dict(report["concept_graph"], relationships=existing + extra)
            if getattr(args, "concept_graph_thinking_compare", False):
                from core import discovery_thinking_comparison
                report["thinking_comparison"] = discovery_thinking_comparison.compare(
                    review_graph, cfg, max_edges=8)
            else:
                report["model_graph_review"] = discovery_local_model.review(
                    review_graph, cfg, max_edges=getattr(args, "concept_graph_max_edges", 24))
        finally:
            progress.finish()
    if getattr(args, "evaluate_terms", False):
        from core import discovery_term_evaluation, paths
        import os
        db_file = os.path.join(paths.local_dir(cfg), "discovery_jira.sqlite")
        if not os.path.isfile(db_file):
            raise SystemExit("Local evidence index missing; index Jira or Confluence first.")
        progress.start("Evaluating cited terminology candidates")
        try:
            report["term_evaluations"] = discovery_term_evaluation.evaluate(
                db_file, project=getattr(args, "project", None))
        finally:
            progress.finish()
    if getattr(args, "term_relationships", False):
        from core import discovery_term_relationships, paths
        import os
        db_file = os.path.join(paths.local_dir(cfg), "discovery_jira.sqlite")
        if not os.path.isfile(db_file):
            raise SystemExit("Local evidence index missing; index Jira or Confluence first.")
        report["term_relationships"] = discovery_term_relationships.propose(
            db_file, project=getattr(args, "project", None))
    if getattr(args, "concept_clusters", False):
        from core import discovery_concept_clusters, paths
        import os
        db_file = os.path.join(paths.local_dir(cfg), "discovery_jira.sqlite")
        report["concept_clusters"] = discovery_concept_clusters.clusters(
            db_file, project=getattr(args, "project", None))
    if getattr(args, "alias_candidates", False):
        from core import discovery_alias_candidates, paths
        import os
        db_file = os.path.join(paths.local_dir(cfg), "discovery_jira.sqlite")
        if not os.path.isfile(db_file):
            raise SystemExit("Local Jira evidence index missing; run --index-jira first.")
        report["alias_candidates"] = discovery_alias_candidates.stage(
            db_file, project=getattr(args, "project", None))
    if getattr(args, "enrich", False):
        from core import discovery_evidence
        progress.start("Gathering bounded discovery evidence")
        report = discovery_evidence.enrich(cfg, report)
        progress.finish()
    if getattr(args, "propose", False):
        from core import discovery_proposals
        if not getattr(args, "enrich", False):
            raise SystemExit("--propose requires --enrich to establish source evidence.")
        report = discovery_proposals.propose(cfg, report)
    if getattr(args, "questions", False):
        from core import discovery_questions
        report = discovery_questions.attach(report)
    print(discovery.summary(report), end="")
    if report.get("confluence_crawl") is not None:
        for item in report["confluence_crawl"]:
            scope = item.get("scope") or {}
            label = (scope.get("root_title") or scope.get("root_id")
                     or scope.get("space") or "unknown")
            note = ("; covered by completed ancestor {}".format(item["covered_by"])
                    if item.get("covered_by") else "")
            print("Confluence crawl: {} [{}] ({} rows this round, offset {}; "
                  "{} new, {} duplicates, {} ancestry metadata warnings){}{}".format(
                      item["status"], label, item["processed"],
                      item.get("offset", 0), item.get("new_pages", 0),
                      item.get("duplicates", 0),
                      item.get("ancestry_metadata_warnings", 0), note,
                      "; " + item["error"] if item.get("error") else ""))
    if report.get("confluence_index") is not None:
        entry = report["confluence_index"]
        print("Confluence evidence: {} pages/blogs, {} comments indexed; {} content and {} comments changed; inventory {}, complete: {}, errors: {}".format(
            entry["indexed"], entry["comments_indexed"], entry["changed"],
            entry["comments_changed"], entry["inventory_coverage"],
            entry["complete"], len(entry["errors"])))
        print("  Drafts excluded: {}; published pages recovered via v2: {}".format(
            len(entry.get("drafts_skipped") or []), len(entry.get("v2_fallbacks") or [])))
        for item in entry.get("drafts_skipped") or []:
            print("  Draft excluded: {} ({})".format(item["id"], item["title"]))
        for item in entry.get("v2_fallbacks") or []:
            print("  Published v2 fallback: {} ({})".format(item["id"], item["title"]))
        for item in entry["errors"][:10]:
            print("  {}: {}".format(item["id"], item["detail"]))
        for scope in entry["scopes"]:
            if scope.get("status") != "complete":
                print("  Incomplete scope: {} ({})".format(
                    (scope.get("scope") or scope).get("root_title")
                    or (scope.get("scope") or scope).get("root_id")
                    or (scope.get("scope") or scope).get("space"),
                    scope.get("detail") or scope["status"]))
    if report.get("profile_leads") is not None:
        leads = report["profile_leads"]
        kinds = leads.get("indexed_kind_counts") or {}
        jira_issues = kinds.get("jira:issue", 0)
        jira_comments = kinds.get("jira:comment", 0)
        jira_changes = kinds.get("jira:change", 0)
        print("Offline evidence: {} indexed records, including {} Jira issues, "
              "{} Jira comments, {} Jira changes and {} Confluence records".format(
                  leads["indexed_documents_scanned"], jira_issues, jira_comments,
                  jira_changes, leads["indexed_source_counts"].get("confluence", 0)))
        print("  Jira supporting records: {} (not additional issues)".format(
            leads.get("jira_supporting_records", jira_comments + jira_changes)))
        for entity in leads["entities"]:
            print("  {} ({}): {} relevant parent sources from {} matching "
                  "evidence records, {} descriptive lead(s)".format(
                      entity["name"], entity["kind"], entity["documents_matched"],
                      entity.get("evidence_records_matched", entity["documents_matched"]),
                      len(entity["leads"])))
    if report.get("profile_discovery") is not None:
        item = report["profile_discovery"]
        print("Candidate profiles: {} found ({} displayed; {} beyond limit), "
              "all unconfirmed".format(
                  item["total_candidates"], len(item["candidates"]),
                  item["unreviewed_candidates"]))
        for row in item["candidates"][:15]:
            print("  {}: {} [Confluence {}, Jira {}; {}; {}]".format(
                row["name"], row["candidate_kind"] or "kind unknown",
                row["published_documents"], row["jira_issues"],
                row["reconciliation"]["status"],
                ", ".join(row["found_via"])))
        if item.get("model_review") is not None:
            review = item["model_review"]
            print("Profile model reviewed {} of {} candidates (unconfirmed)".format(
                review["reviewed"], review["total_candidates"]))
            for row in review["results"]:
                result = row["result"]
                print("  {}: {} cited claims [{}]".format(
                    row["name"], len(result["claims"]), result["status"]))
    if report.get("concept_graph") is not None:
        graph = report["concept_graph"]
        print("Candidate concept identities: {} (showing {})".format(
            graph["identity_total"], min(100, len(graph["identities"]))))
        print("Typed candidate relationships: {} (showing {})".format(
            graph["relationship_total"], min(100, len(graph["relationships"]))))
        for edge in graph["relationships"][:100]:
            print("  {} --{}--> {} [{}; {} independent source(s)]".format(
                edge["from"], edge["type"], edge["to"],
                edge["project"], edge["independent_sources"]))
    if report.get("thinking_comparison") is not None:
        comparison = report["thinking_comparison"]
        print("Thinking comparison: {} candidates, same evidence, no cached responses".format(
            comparison["reviewed"]))
        for mode in ("off", "on"):
            stats = comparison["modes"][mode]
            print("  {}: {} valid, {} repaired, {} failures, {:.1f}s".format(
                mode, stats["valid"], stats["repaired"], stats["failures"], stats["seconds"]))
        print("  Different relationships: {}".format(comparison["different_types"]))
    if report.get("model_graph_review") is not None:
        item = report["model_graph_review"]
        print("Contextual candidates: {} (not yet confirmed)".format(
            len(report.get("contextual_candidates", []))))
        print("Local model reviewed {} of {} evidence candidates (unconfirmed)".format(
            item["reviewed"], item["total_edges"]))
        for edge in item["results"]:
            print("  {} -> {}: {} [{}]".format(
                edge["from"], edge["to"], edge["model"]["type"],
                edge["model"]["status"]))
    if report.get("term_evaluations") is not None:
        item = report["term_evaluations"]
        print("Terminology candidate evaluations: {}".format(item["pairs_generated"]))
        for entry in item["evaluations"]:
            print("  {} <> {} [{}; {} cited passages; {}]".format(
                entry["a"], entry["b"], entry["assessment"],
                entry["evidence_count"], entry["project"]))
    if report.get("term_relationships") is not None:
        item = report["term_relationships"]
        print("Offline source evidence: {} indexed documents examined (not live retrieval)".format(
            item["examined_documents"]))
        print("Candidate terminology relationships: {} (showing {})".format(
            item["total_candidates"], len(item["relationships"])))
        for relation in item["relationships"]:
            citation = relation["evidence"][0]["citation"]
            print("  {}: {} -> {} [{}; {} source(s); {}]".format(
                relation["relationship"], relation["from"], relation["to"],
                relation["project"], relation["evidence_count"], citation))
    if report.get("concept_clusters") is not None:
        entries = report["concept_clusters"]
        print("Concept candidate clusters: {}".format(len(entries)))
        for item in entries:
            print("  {}: {} ({} citations; aliases: {}{})".format(
                item["project"], item["canonical"], item["evidence_count"],
                ", ".join(item["aliases"]),
                "; ambiguous: " + ", ".join(item["ambiguous_aliases"])
                if item["ambiguous_aliases"] else ""))
    if report.get("alias_candidates") is not None:
        entries = report["alias_candidates"]
        print("Unconfirmed alias candidates: {}".format(len(entries)))
        for entry in entries[:50]:
            print("  {} ({}): {} = {} [{} evidence references]".format(
                entry["project"], entry["status"], entry["canonical"],
                entry["alias"], len(entry["citations"])))
        if len(entries) > 50:
            print("  ... {} additional candidates retained and exported".format(len(entries) - 50))
    if report.get("jira_index") is not None:
        result = report["jira_index"]
        print("Offline evidence index: {} documents ({} changed; {} issues scanned)".format(
            result["documents_total"], result["documents_updated"], result["issues_processed"]))
    if report.get("concept_matches") is not None:
        matches = report["concept_matches"]
        print("Concept evidence matches: {}".format(len(matches)))
        for item in matches:
            print("  {} [{} via {}{}]: {}".format(
                item["citation"], item["kind"], item["matched_term"],
                " (alias evidence: {})".format(item["alias_evidence"])
                if item["alias_evidence"] else "", item["excerpt"]))
    if report.get("evidence_matches") is not None:
        matches = report["evidence_matches"]
        print("Evidence matches: {}".format(len(matches)))
        for item in matches:
            print("  {} [{}] {}: {}".format(
                item["citation"], item["kind"], item["title"], item["excerpt"]))
    if report.get("inventory") is not None:
        from core import discovery_inventory
        print(discovery_inventory.summary(report))
    if report.get("jira_inventory") is not None:
        inv = report["jira_inventory"]
        print("Jira inventory: " + inv["coverage"])
        for scope in inv["projects"]:
            print("  {}: {} ({} stored issues, {} pages this run){}".format(
                scope["project"], scope["status"], scope["stored"],
                scope["fetched_pages"], "; " + scope["detail"]
                if scope.get("detail") else ""))
    if report.get("jira_refresh") is not None:
        refresh = report["jira_refresh"]
        print("Jira incremental refresh: " + refresh["coverage"])
        for project in refresh["projects"]:
            print("  {}: {} ({} changed issues){}".format(
                project["project"], project["status"], project["updated"],
                "; " + project["detail"] if project.get("detail") else ""))
    if report.get("jira_history") is not None:
        history = report["jira_history"]
        print("Jira changelog history: {} ({} issues completed; {} remaining){}".format(
            history["coverage"], history["completed"], history["remaining"],
            "; " + history["detail"] if history.get("detail") else ""))
        for error in history.get("errors") or []:
            print("  {}: {}".format(error["issue"], error["detail"]))
    if report.get("jira_comments") is not None:
        comments = report["jira_comments"]
        print("Jira comments: {} ({} issues completed; {} remaining){}".format(
            comments["coverage"], comments["completed"], comments["remaining"],
            "; " + comments["detail"] if comments.get("detail") else ""))
    if report.get("jira_reconcile") is not None:
        inv = report["jira_reconcile"]
        print("Jira reconciliation: " + inv["coverage"])
        for scope in inv["projects"]:
            print("  {}: {} ({} absent candidates){}".format(
                scope["project"], scope["status"], scope["missing_candidates"],
                "; " + scope["detail"] if scope.get("detail") else ""))
    if report.get("jira_structure") is not None:
        structure = report["jira_structure"]
        print("Jira project structure: " + structure["coverage"])
        for item in structure["projects"]:
            print("  {}: {} ({} issue types, {} components){}".format(
                item["project"], item["status"], len(item["issue_types"]),
                len(item["components"]),
                "; " + item["detail"] if item.get("detail") else ""))
    if getattr(args, "export", False):
        target = output.place(cfg, "discovery.md", getattr(args, "out", None))
        with open(target, "w", encoding="utf-8") as stream:
            stream.write(discovery.markdown(report))
            if report.get("inventory") is not None:
                from core import discovery_inventory
                stream.write("\n" + discovery_inventory.markdown(report))
            if report.get("profile_discovery") is not None:
                inventory = report["profile_discovery"]
                stream.write("\n## Unconfirmed offline product and workstream candidates\n\n")
                stream.write("- Project: {}\n- Total candidates: {} ({} reported; {} "
                             "not included due to limit)\n".format(
                    inventory["project"], inventory["total_candidates"],
                    len(inventory["candidates"]), inventory["unreviewed_candidates"]))
                stream.write("- No configuration or confirmed ownership was changed.\n")
                for item in inventory["candidates"]:
                    stream.write("\n### {} (candidate)\n\n".format(item["name"]))
                    stream.write("- Observed labels: {}\n".format(
                        ", ".join(item["observed_labels"]) or "unknown"))
                    stream.write("- Found via: {}\n".format(", ".join(item["found_via"])))
                    stream.write("- Independent sources: {} ({} published Confluence, "
                                 "{} Jira issues)\n".format(
                        item["source_count"], item["published_documents"],
                        item["jira_issues"]))
                    stream.write("- Reconciliation: {} (configured kind: {})\n".format(
                        item["reconciliation"]["status"],
                        item["reconciliation"]["configured_kind"] or "none"))
                    for evidence in item["evidence"]:
                        stream.write("- Evidence {} [{}]: {}\n".format(
                            evidence["citation"], evidence["kind"],
                            evidence["excerpt"].replace("\n", " ")))
                model_review = inventory.get("model_review")
                if model_review is not None:
                    stream.write("\n## Unconfirmed local-model profile claims\n\n")
                    stream.write("- Reviewed: {} of {} candidates\n".format(
                        model_review["reviewed"], model_review["total_candidates"]))
                    for entry in model_review["results"]:
                        result = entry["result"]
                        stream.write("\n### {} [{}]\n".format(
                            entry["name"], result["status"]))
                        if result.get("error"):
                            stream.write("- Validation error: {}\n".format(result["error"]))
                        for claim in result["claims"]:
                            stream.write("- {}: {} [{}]\n".format(
                                claim["field"], claim["value"],
                                ", ".join(claim["citations"])))
            if report.get("profile_leads") is not None:
                leads = report["profile_leads"]
                stream.write("\n## Indexed evidence for product and workstream definitions\n\n")
                stream.write("- Indexed evidence records scanned: {}\n".format(
                    leads["indexed_documents_scanned"]))
                stream.write("- Source records: {}\n".format(", ".join(
                    "{}: {}".format(k, v) for k, v in
                    leads["indexed_source_counts"].items()) or "none"))
                kinds = leads.get("indexed_kind_counts") or {}
                stream.write("- Jira breakdown: {} issues, {} comments, {} changelog records.\n".format(
                    kinds.get("jira:issue", 0), kinds.get("jira:comment", 0),
                    kinds.get("jira:change", 0)))
                stream.write("- Jira comments and changelog records are supporting evidence, "
                             "not additional Jira issues.\n")
                stream.write("- These are navigation leads, not verified ownership or purpose claims.\n")
                for entry in leads["entities"]:
                    stream.write("\n### {} ({}, {})\n\n".format(
                        entry["name"], entry["kind"], entry["abbrev"]))
                    stream.write("- Independent parent sources mentioning full name: {} "
                                 "({} matching evidence records)\n".format(
                        entry["documents_matched"],
                        entry.get("evidence_records_matched", entry["documents_matched"])))
                    for lead in entry["leads"]:
                        stream.write("- {} [{}]: {}\n".format(
                            lead["citation"], lead["source"],
                            lead["excerpt"].replace("\n", " ")))
                    if not entry["leads"]:
                        stream.write("- No descriptive passage found in the indexed evidence.\n")
                stream.write("\n")
            if report.get("concept_graph") is not None:
                graph = report["concept_graph"]
                stream.write("\n## Unconfirmed typed concept graph\n\n")
                stream.write("- Concept identities: {} (showing {})\n".format(
                    graph["identity_total"], len(graph["identities"])))
                stream.write("- Typed relationships: {} (showing {})\n".format(
                    graph["relationship_total"], len(graph["relationships"])))
                for item in graph["identities"]:
                    stream.write("- Concept {} [{}] aliases: {} | citations: {}\n".format(
                        item["canonical"], item["status"], ", ".join(item["aliases"]),
                        ", ".join(item["citations"])))
                for edge in graph["relationships"]:
                    stream.write("- {} --{}--> {} [{}; candidate]\n".format(
                        edge["from"], edge["type"], edge["to"], edge["project"]))
                    for evidence in edge["evidence"]:
                        stream.write("  - {}: {}\n".format(
                            evidence["citation"], evidence["excerpt"]))
            if report.get("thinking_comparison") is not None:
                stream.write("\n## Thinking on/off comparison (unconfirmed)\n\n")
                stream.write("```json\n" + json.dumps(report["thinking_comparison"], indent=2) + "\n```\n")
            if report.get("contextual_candidates") is not None:
                queue = report["contextual_candidates"]
                stream.write("\n## Contextual candidate queue (all, unconfirmed)\n\n")
                stream.write("- {} canonical candidate pairs found; not all are reviewed by the model.\n".format(len(queue)))
                for edge in queue:
                    stream.write("- {} <> {} [{}; {} strong, {} signal, {} source(s)]\n".format(
                        edge["from"], edge["to"], edge["project"],
                        edge["strong_sources"], edge["signal_sources"],
                        edge["independent_sources"]))
                    for hint in edge["relationship_hints"][:5]:
                        stream.write("  - Candidate {}: {} -> {} ({})\n".format(
                            hint["type"], hint["from"], hint["to"], hint["citation"]))
            if report.get("model_graph_review") is not None:
                item = report["model_graph_review"]
                stream.write("\n## Local model review (unconfirmed)\n\n")
                stream.write("- Contextual candidates generated: {}\n".format(
                    len(report.get("contextual_candidates", []))))
                stream.write("- Model: {}. Reviewed {} of {} edges.\n".format(
                    item["model_name"], item["reviewed"], item["total_edges"]))
                stream.write("- Unreviewed candidate edges: {}\n".format(item["unreviewed"]))
                for edge in item["results"]:
                    finding = edge["model"]
                    stream.write("- {} -> {}: {} [{}]. References: {}\n".format(
                        edge["from"], edge["to"], finding["type"], finding["status"],
                        ", ".join(finding.get("citations", []))))
                    if finding.get("rationale"):
                        stream.write("  - Rationale (model interpretation): {}\n".format(
                            finding["rationale"]))
                    if finding.get("error"):
                        stream.write("  - Error: {}\n".format(finding["error"]))
            if report.get("term_evaluations") is not None:
                stream.write("\n## Unconfirmed terminology evidence evaluations\n\n")
                for item in report["term_evaluations"]["evaluations"]:
                    stream.write("- {} <> {}: {} [{}]\n".format(
                        item["a"], item["b"], item["assessment"], item["project"]))
                    for evidence in item["evidence"]:
                        stream.write("  - {} [{}]: {}\n".format(
                            evidence["citation"], evidence["signal"], evidence["excerpt"]))
            if report.get("term_relationships") is not None:
                stream.write("\n## Unconfirmed terminology relationships\n\n")
                for relation in report["term_relationships"]["relationships"]:
                    stream.write("- {}: {} -> {} [{}; {} source(s)]\n".format(
                        relation["relationship"], relation["from"], relation["to"],
                        relation["project"], relation["evidence_count"]))
                    for ev in relation["evidence"]:
                        stream.write("  - {}: {}\n".format(ev["citation"], ev["excerpt"]))
            if report.get("concept_clusters") is not None:
                stream.write("\n## Candidate terminology clusters\n\n")
                for item in report["concept_clusters"]:
                    stream.write("- {}: {} | variants: {} | aliases: {} | citations: {} | ambiguous: {}\n".format(
                        item["project"], item["canonical"],
                        ", ".join(item["variants"]),
                        ", ".join(item["aliases"]),
                        ", ".join(item["citations"]),
                        ", ".join(item["ambiguous_aliases"]) or "none"))
            if report.get("alias_candidates") is not None:
                stream.write("\n## Unconfirmed alias candidates\n\n")
                for entry in report["alias_candidates"]:
                    stream.write("- {}: {} ({}) [{}]\n".format(
                        entry["project"], entry["canonical"], entry["alias"],
                        ", ".join(entry["citations"])))
            if report.get("jira_index") is not None:
                item = report["jira_index"]
                stream.write("\n## Offline Jira evidence index\n\n- Documents: {}\n- Changed: {}\n".format(
                    item["documents_total"], item["documents_updated"]))
            if report.get("evidence_matches") is not None:
                stream.write("\n## Offline evidence search\n\n")
                for item in report["evidence_matches"]:
                    stream.write("- {} [{}] {}: {}\n".format(
                        item["citation"], item["kind"], item["title"], item["excerpt"]))
            if report.get("jira_inventory") is not None:
                inv = report["jira_inventory"]
                stream.write("\n## Jira project inventory\n\n- Coverage: {}\n".format(inv["coverage"]))
                for scope in inv["projects"]:
                    stream.write("- {}: {} ({} stored issues; {} pages fetched this run){}\n".format(
                        scope["project"], scope["status"], scope["stored"],
                        scope["fetched_pages"],
                        "; " + scope["detail"] if scope.get("detail") else ""))
            if report.get("jira_refresh") is not None:
                refresh = report["jira_refresh"]
                stream.write("\n## Jira incremental refresh\n\n- Coverage: {}\n".format(
                    refresh["coverage"]))
                for project in refresh["projects"]:
                    stream.write("- {}: {} ({} changed issues){}\n".format(
                        project["project"], project["status"], project["updated"],
                        "; " + project["detail"] if project.get("detail") else ""))
            if report.get("jira_history") is not None:
                history = report["jira_history"]
                stream.write("\n## Jira historical classification changes\n\n")
                stream.write("- Coverage: {}\n- Issues completed this run: {}\n- Issues remaining: {}\n".format(
                    history["coverage"], history["completed"], history["remaining"]))
                for error in history.get("errors") or []:
                    stream.write("- {}: {}\n".format(error["issue"], error["detail"]))
            if report.get("jira_comments") is not None:
                comments = report["jira_comments"]
                stream.write("\n## Jira comment collection\n\n")
                stream.write("- Coverage: {}\n- Issues completed this run: {}\n- Issues remaining: {}\n".format(
                    comments["coverage"], comments["completed"], comments["remaining"]))
                for error in comments.get("errors") or []:
                    stream.write("- {}: {}\n".format(error["issue"], error["detail"]))
            if report.get("jira_reconcile") is not None:
                reconcile = report["jira_reconcile"]
                stream.write("\n## Jira inventory reconciliation\n\n- Coverage: {}\n".format(
                    reconcile["coverage"]))
                for scope in reconcile["projects"]:
                    stream.write("- {}: {} ({} absent candidates){}\n".format(
                        scope["project"], scope["status"], scope["missing_candidates"],
                        "; " + scope["detail"] if scope.get("detail") else ""))
            if report.get("jira_structure") is not None:
                structure = report["jira_structure"]
                stream.write("\n## Jira project structure\n\n- Coverage: {}\n".format(
                    structure["coverage"]))
                for item in structure["projects"]:
                    stream.write("- {}: {}\n".format(item["project"], item["status"]))
                    for issue_type in item["issue_types"]:
                        stream.write("  - {} (ID {}, hierarchy level {})\n".format(
                            issue_type["name"], issue_type["id"],
                            issue_type["hierarchy_level"]))
                    stream.write("  - Field catalogue: {} ({} fields)\n".format(
                        item.get("fields_coverage", "unavailable"), len(item.get("fields") or [])))
                    if item.get("detail"):
                        stream.write("  - Note: {}\n".format(item["detail"]))
        print("Discovery report: " + target)
