"""Regular help, advanced help, and both --config orders."""

import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PM = os.path.join(ROOT, "pm.py")


def _run(*args):
    return subprocess.run(
        [sys.executable, PM, *args],
        capture_output=True, text=True, encoding="utf-8", timeout=30)


class HelpTests(unittest.TestCase):
    def test_the_catalogue_covers_every_command(self):
        import pm
        from core import helptext
        parser = pm.build_parser()
        missing = sorted(set(parser._pm_subs) - set(helptext.known_commands()))
        self.assertEqual(missing, [])
    def test_no_arguments_and_help_are_the_everyday_page(self):
        for args in ([], ["help"], ["-h"], ["--help"]):
            proc = _run(*args)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("pm today", proc.stdout)
            self.assertIn("pm report --sprint", proc.stdout)
            self.assertNotIn("pm mcp", proc.stdout)
            self.assertNotIn("--fail-on", proc.stdout)

    def test_the_product_manager_page_keeps_those_examples(self):
        path = os.path.join(ROOT, "docs", "roles", "product-manager.md")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("pm today", text)
        self.assertIn("pm report --sprint", text)
        proc = _run("help")
        self.assertIn("pm today", proc.stdout)
        self.assertIn("pm report --sprint", proc.stdout)

    def test_advanced_lists_coverage_and_mcp(self):
        proc = _run("help", "--advanced")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("pm coverage", proc.stdout)
        self.assertIn("pm mcp", proc.stdout)

    def test_command_help_shows_syntax_without_advanced(self):
        short = _run("report", "-h")
        self.assertEqual(short.returncode, 0, short.stderr)
        self.assertIn("--since YYYY-MM-DD", short.stdout)
        self.assertIn("--sprint", short.stdout)
        self.assertIn("--audience", short.stdout)
        self.assertIn("--product", short.stdout)
        self.assertIn("--workstream", short.stdout)
        self.assertIn("--publish", short.stdout)
        self.assertIn("--json", short.stdout)
        self.assertIn("--sources", short.stdout)
        full = _run("report", "-h", "--advanced")
        self.assertEqual(full.returncode, 0, full.stderr)
        self.assertIn("--json", full.stdout)
        self.assertIn("--since YYYY-MM-DD", full.stdout)
        do = _run("do", "-h")
        self.assertEqual(do.returncode, 0, do.stderr)
        self.assertIn("number (required)", do.stdout)
        self.assertIn("pm do 2", do.stdout)

    def test_help_all_and_help_report_match_the_command_page(self):
        every = _run("help", "all")
        self.assertEqual(every.returncode, 0, every.stderr)
        self.assertIn("pm coverage", every.stdout)
        self.assertIn("pm mcp", every.stdout)
        self.assertNotIn("docs/roles/", every.stdout)
        report = _run("report", "-h")
        via_help = _run("help", "report")
        self.assertEqual(report.stdout, via_help.stdout)
        inbox = _run("inbox", "-h")
        for word in ("list", "edit", "create", "drop"):
            self.assertIn(word, inbox.stdout)
        schedule = _run("schedule", "-h")
        for word in ("list", "add", "remove", "--at HH:MM"):
            self.assertIn(word, schedule.stdout)

    def test_discovery_is_role_aware_and_survives_a_missing_config(self):
        missing = _run("--config", os.path.join(tempfile.gettempdir(), "no-such-pm.yaml"))
        self.assertEqual(missing.returncode, 0, missing.stderr)
        self.assertIn("pm today", missing.stdout)
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "dev.yaml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("role: developer\njira:\n  project: APS\n")
            dev = _run("--config", path)
            design_path = os.path.join(folder, "design.yaml")
            with open(design_path, "w", encoding="utf-8") as fh:
                fh.write("role: service-designer\njira:\n  project: APS\n")
            design = _run("--config", design_path)
        self.assertEqual(dev.returncode, 0, dev.stderr)
        self.assertIn("pm daily", dev.stdout)
        self.assertIn("pm release-notes", dev.stdout)
        self.assertNotIn("pm do", dev.stdout)
        self.assertEqual(design.returncode, 0, design.stderr)
        self.assertLess(design.stdout.index("pm report"), design.stdout.index("pm brief"))
        self.assertLess(design.stdout.index("pm brief"), design.stdout.index("pm show"))
        self.assertIn("pm release-notes", design.stdout)
        self.assertIn("pm me", design.stdout)
        self.assertNotIn("pm do", design.stdout)
        roles = _run("help", "roles")
        self.assertEqual(roles.returncode, 0, roles.stderr)
        self.assertIn("service-designer", roles.stdout)
        self.assertIn("github.com/dstainton/pm-tools", roles.stdout)
        self.assertNotIn("docs/roles/", roles.stdout)

    def test_advanced_without_help_does_not_run_the_command(self):
        proc = _run("report", "--advanced")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("-h --advanced", proc.stderr)

    def test_config_before_or_after_the_command_opens_the_same_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "aps.yaml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(
                    "jira:\n"
                    "  project: APS\n"
                    "products:\n"
                    "  - name: Integration Platform\n"
                    "    abbrev: IP\n"
                    "workstreams:\n"
                    "  - name: Secure Data Exchange\n"
                    "    abbrev: SDX\n"
                    "    product: IP\n"
                    "    components: [Secure Data Exchange]\n"
                )
            after = _run("products", "--config", path)
            before = _run("--config", path, "products")
        self.assertEqual(after.returncode, 0, after.stderr)
        self.assertEqual(before.returncode, 0, before.stderr)
        self.assertIn(path, after.stdout)
        self.assertIn(path, before.stdout)
        self.assertIn("Integration Platform", after.stdout)
        self.assertIn("Integration Platform", before.stdout)

    def test_two_different_config_flags_are_refused(self):
        proc = _run("--config", "/tmp/one.yaml", "products", "--config", "/tmp/two.yaml")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("Pass --config once.", proc.stderr)


if __name__ == "__main__":
    unittest.main()
