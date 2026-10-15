"""Read-only discovery of configured products and workstreams."""
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
                # A failed item must not be retried indefinitely in this invocation.
                if previous_remaining is not None and remaining >= previous_remaining:
                    break
                previous_remaining = remaining
            report[name] = {"coverage": "complete" if remaining == 0 else "partial",
                            "attempted": total_attempted, "completed": total_completed,
                            "remaining": remaining, "errors": errors}
            if errors:
                report[name]["detail"] = "{} issues had collection errors".format(len(errors))
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
