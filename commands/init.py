"""`pm init` — create a starter config in the standard location.

On first run there's usually no config yet. This copies the bundled template
(the config.yaml shipped next to the code) to ~/.pm/config.yaml — the tidy home
a globally-installed `pm` looks in — so you can fill it in and immediately run
`pm lint` from anywhere.

  pm init                 Create ~/.pm/config.yaml (won't overwrite).
  pm init --force         Overwrite an existing ~/.pm/config.yaml.
  pm init --path FILE     Write to a specific location instead.

This command deliberately does NOT load or validate config, so it works even
when nothing is set up yet. pm.py routes to it before config discovery.
"""

import os
import shutil
import sys


def bundled_template_path():
    """The config.yaml that ships alongside the code, used as the template."""
    here = os.path.dirname(os.path.abspath(__file__))     # .../commands
    root = os.path.dirname(here)                           # package root
    return os.path.join(root, "config.yaml")


def run(args):
    """Entry point called by pm.py. Note: takes only args (no cfg)."""
    template = bundled_template_path()
    if not os.path.exists(template):
        sys.exit(f"Could not find the bundled template at {template}. "
                 "Reinstall or copy config.yaml manually.")

    # Decide where to write.
    if getattr(args, "path", None):
        dest = os.path.expanduser(args.path)
    else:
        dest = os.path.expanduser("~/.pm/config.yaml")

    # Don't clobber an existing config unless asked.
    if os.path.exists(dest) and not getattr(args, "force", False):
        print(f"A config already exists at:\n  {dest}\n\n"
              f"Leaving it untouched. To replace it, run:\n"
              f"  pm init --force")
        return

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copyfile(template, dest)

    print(f"Created a starter config at:\n  {dest}\n")
    print("Next steps:")
    print("  1. Open that file and fill in the <PLACEHOLDERS> "
          "(Jira URL, email, API token, project).")
    print("  2. Name your workstreams and their Jira Component(s) — either in "
          "that file or with:  pm workstreams add")
    print("  3. Confirm Jira agrees with it:  pm workstreams check")
    print("  4. Start the local llama.cpp/Qwen server (for report/review).")
    print("  5. Run a command from anywhere, e.g.:  pm lint --workstream SDX")
    print("\nTip: pm finds this file automatically — no --config needed.")
