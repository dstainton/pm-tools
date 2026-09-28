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

    def test_command_help_is_short_until_advanced(self):
        short = _run("report", "-h")
        self.assertEqual(short.returncode, 0, short.stderr)
        self.assertIn("--sprint", short.stdout)
        self.assertNotIn("--json", short.stdout)
        full = _run("report", "-h", "--advanced")
        self.assertEqual(full.returncode, 0, full.stderr)
        self.assertIn("--json", full.stdout)
        do = _run("do", "-h")
        self.assertEqual(do.returncode, 0, do.stderr)
        self.assertIn("pm do 2", do.stdout)

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
