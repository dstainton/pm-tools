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
        report["jira_inventory"] = discovery_jira_checkpoint.crawl(
            cfg, projects, db_file)
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
        print("Discovery report: " + target)
