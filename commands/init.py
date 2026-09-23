"""`pm init` — create a starter config in the standard location.

On first run there's usually no config yet. This copies the bundled template
(the config.yaml shipped next to the code) to ~/.pm-tools/config.yaml — the tidy home
a globally-installed `pm` looks in — so you can fill it in and immediately run
`pm lint` from anywhere.

  pm init                 Create ~/.pm-tools/config.yaml (won't overwrite).
  pm init --force         Overwrite an existing ~/.pm-tools/config.yaml.
  pm init --path FILE     Write to a specific location instead.

This command deliberately does NOT load or validate config, so it works even
when nothing is set up yet. pm.py routes to it before config discovery.
"""

import os
import shutil
import sys

from core.migrations import bundled_template_path
from core.paths import config_file


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
        dest = os.path.expanduser(config_file())

    # Don't clobber an existing config unless asked.
    if os.path.exists(dest) and not getattr(args, "force", False):
        print(f"A config already exists at:\n  {dest}\n\n"
              f"Leaving it untouched. To add new settings, run:\n"
              f"  pm update\n\n"
              f"`pm init --force` is the only command that replaces this file.")
        return

    if os.path.exists(dest):
        print("Replacing the existing config. "
              "`pm init --force` is the only command that does this.\n")

    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    shutil.copyfile(template, dest)

    print(f"Created a starter config at:\n  {dest}\n")
    print("Next steps:")
    print("  1. Open that file and fill in the <PLACEHOLDERS> "
          "(Jira URL, email, API token, project).")
    print("  2. Name your products and workstreams — either in that file or "
          "with:  pm products add   /   pm workstreams add")
    print("  3. Confirm Jira agrees with it:  pm doctor")
    print("  4. Start the local llama.cpp/Qwen server (for report/review).")
    print("  5. The habit command:  pm today")
    print("\nTip: pm finds this file automatically — no --config needed.")
