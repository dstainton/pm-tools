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
    if getattr(args, "enrich", False):
        from core import discovery_evidence
        progress.start("Gathering bounded discovery evidence")
        report = discovery_evidence.enrich(cfg, report)
        progress.finish()
    if getattr(args, "questions", False):
        from core import discovery_questions
        report = discovery_questions.attach(report)
    print(discovery.summary(report), end="")
    if getattr(args, "export", False):
        target = output.place(cfg, "discovery.md", getattr(args, "out", None))
        with open(target, "w", encoding="utf-8") as stream:
            stream.write(discovery.markdown(report))
        print("Discovery report: " + target)
