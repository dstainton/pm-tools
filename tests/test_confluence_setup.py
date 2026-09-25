"""Guided setup, help, and doctor wording for one Confluence space."""

import io
import os
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from unittest.mock import patch

from commands import doctor, setup
from core import config_edit


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TEXT = """\
jira:
  base_url: "https://example.atlassian.net"
  email: "a@example.com"
  api_token: "t"
confluence:
  base_url: "https://<YOUR_ORG>.atlassian.net/wiki"
  email: "<YOUR_LOGIN_EMAIL>"
  api_token: "<YOUR_CONFLUENCE_API_TOKEN>"
products:
  - name: "Integration Platform"
    abbrev: "IP"
workstreams:
  - name: "Secure Data Exchange"
    abbrev: "SDX"
    product: "IP"
    components: ["Secure Data Exchange"]
  - name: "API Platform"
    abbrev: "APS"
    components: ["API Platform"]
    confluence_space: "APS"
"""


class ApplyTests(unittest.TestCase):
    def test_a_shared_space_and_folder_are_written_when_blank(self):
        args = Namespace(
            site=None, email=None, token=None, token_env=None,
            confluence_space="TEAM",
            confluence_root="API Program Services",
            confluence_pages=[
                ("product", "IP", "Integration Platform"),
                ("workstream", "SDX", "Secure Data Exchange"),
            ])
        text, notes = setup.apply_confluence_settings(TEXT, args)
        self.assertIn('space: "TEAM"', text)
        self.assertIn('root_title: "API Program Services"', text)
        self.assertIn('base_url: "https://example.atlassian.net/wiki"', text)
        self.assertIn('confluence_page: "Integration Platform"', text)
        self.assertIn('confluence_page: "Secure Data Exchange"', text)
        self.assertIn('confluence_space: "APS"', text)
        self.assertIn("confluence.space written", notes)

        again, notes = setup.apply_confluence_settings(text, args)
        self.assertEqual(again, text)
        self.assertIn("confluence.space kept", notes)
        self.assertIn("products IP confluence_page kept", notes)

    def test_questions_skip_a_workstream_that_already_has_a_space(self):
        answers = iter(["TEAM", "API Program Services", "Integration Platform",
                        "Secure Data Exchange"])
        args = Namespace(confluence_space=None, confluence_root=None)
        with patch("commands.setup._ask", lambda _prompt: next(answers)):
            setup._ask_confluence(TEXT, args)
        self.assertEqual(args.confluence_space, "TEAM")
        self.assertEqual(args.confluence_root, "API Program Services")
        self.assertEqual(args.confluence_pages, [
            ("product", "IP", "Integration Platform"),
            ("workstream", "SDX", "Secure Data Exchange"),
        ])

    def test_a_blank_space_skips_the_folders(self):
        args = Namespace(confluence_space=None, confluence_root=None)
        with patch("commands.setup._ask", return_value=""):
            setup._ask_confluence(TEXT, args)
        self.assertIsNone(args.confluence_space)
        self.assertFalse(hasattr(args, "confluence_pages"))


class EntryTests(unittest.TestCase):
    def test_a_folder_title_is_inserted_and_an_existing_one_is_kept(self):
        text, status = config_edit.set_entry_scalar(
            TEXT, "workstreams", "SDX", "confluence_page", "Secure Data Exchange")
        self.assertEqual(status, "written")
        self.assertIn('confluence_page: "Secure Data Exchange"', text)
        again, status = config_edit.set_entry_scalar(
            text, "workstreams", "SDX", "confluence_page", "Other")
        self.assertEqual(status, "kept")
        self.assertIn('confluence_page: "Secure Data Exchange"', again)
        self.assertNotIn("Other", again)


class DoctorWordingTests(unittest.TestCase):
    def test_a_workstream_with_neither_space_nor_page_is_named(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            doctor._check_confluence({"workstreams": [{"abbrev": "SDX"}]})
        self.assertIn("no confluence_space or confluence_page", buf.getvalue())


class HelpTests(unittest.TestCase):
    def _help(self, *args):
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "pm.py"), *args, "--help"],
            capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def test_help_names_the_shared_space_and_the_folder(self):
        setup_help = self._help("setup")
        self.assertIn("--confluence-space", setup_help)
        self.assertIn("--confluence-root", setup_help)
        self.assertIn("shared space", setup_help)
        self.assertIn("--confluence-page", self._help("workstreams"))
        self.assertIn("--confluence-page", self._help("products"))

    def test_a_noninteractive_confluence_section_prints_the_flags(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "config.yaml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(TEXT)
            out = io.StringIO()
            with redirect_stdout(out), patch("commands.setup._tty", return_value=False):
                setup.run(Namespace(
                    path=path, section="confluence", yes=True,
                    site=None, email=None, token=None, token_env=None,
                    project=None, model_endpoint=None, model_name=None,
                    model_api_key=None, model_api_key_env=None,
                    confluence_space=None, confluence_root=None,
                    open_browser=False))
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), TEXT)
        self.assertIn("--confluence-space", out.getvalue())
        self.assertIn("Registers", out.getvalue())


if __name__ == "__main__":
    unittest.main()
