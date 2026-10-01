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
            confluence_team_page="API Program Services",
            confluence_pages=[
                ("product", "IP", "Integration Platform"),
                ("workstream", "SDX", "Secure Data Exchange"),
            ])
        text, notes = setup.apply_confluence_settings(TEXT, args)
        self.assertIn('space: "TEAM"', text)
        self.assertIn('team_page: "API Program Services"', text)
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
        args = Namespace(confluence_space=None, confluence_team_page=None)
        with patch("commands.setup._ask", lambda _prompt: next(answers)), \
                patch("commands.setup._matched_folders", return_value={}):
            setup._ask_confluence(TEXT, args)
        self.assertEqual(args.confluence_space, "TEAM")
        self.assertEqual(args.confluence_team_page, "API Program Services")
        self.assertEqual(args.confluence_pages, [
            ("product", "IP", "Integration Platform"),
            ("workstream", "SDX", "Secure Data Exchange"),
        ])

    def test_a_blank_space_skips_the_folders(self):
        args = Namespace(confluence_space=None, confluence_team_page=None)
        with patch("commands.setup._ask", return_value=""), \
                patch("commands.setup._matched_folders", return_value={}):
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


class FolderFixTests(unittest.TestCase):
    def test_a_matching_folder_only_drops_the_whole_space_key(self):
        row = {"abbrev": "SDX", "confluence_space": "POSM"}
        actions = setup.plan_folder(
            row, {"space": "POSM"},
            {"ancestor_id": "12", "title": "Secure Data Exchange (SDX)"},
            space_is_team=True)
        self.assertEqual(actions, ["delete-space"])

    def test_a_missing_team_folder_sets_the_page_and_drops_the_space(self):
        row = {"abbrev": "SDX", "confluence_space": "POSM",
               "confluence_page": "Missing"}
        actions = setup.plan_folder(
            row, {"missing": True, "space": "POSM"}, {}, space_is_team=True)
        self.assertEqual(actions, ["set-page", "delete-space"])

    def test_a_private_space_keeps_its_key(self):
        row = {"abbrev": "ITK", "confluence_space": "ITK"}
        actions = setup.plan_folder(
            row, {"space": "ITK"}, {}, space_is_team=False)
        self.assertEqual(actions, ["set-page"])

    def test_yes_writes_the_folder_title(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "config.yaml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(TEXT)
            args = Namespace(
                workstream="SDX", product=None, confluence_page="Secure Data Exchange",
                yes=True)
            with redirect_stdout(io.StringIO()), \
                    patch("commands.setup._tty", return_value=False), \
                    patch("commands.setup._locate_quiet", return_value={}):
                setup._run_folder(args, path, TEXT)
            with open(path, encoding="utf-8") as fh:
                written = fh.read()
        self.assertIn('confluence_page: "Secure Data Exchange"', written)
        self.assertIn('confluence_space: "APS"', written)

    def test_a_pipe_does_not_write_without_yes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "config.yaml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(TEXT)
            args = Namespace(
                workstream="SDX", product=None, confluence_page="Secure Data Exchange",
                yes=False)
            out = io.StringIO()
            with redirect_stdout(out), \
                    patch("commands.setup._tty", return_value=False), \
                    patch("commands.setup._locate_quiet", return_value={}):
                setup._run_folder(args, path, TEXT)
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), TEXT)
        self.assertIn("--yes", out.getvalue())

    def test_a_matched_folder_removes_confluence_space(self):
        text = TEXT.replace(
            '    abbrev: "SDX"\n    product: "IP"\n',
            '    abbrev: "SDX"\n    product: "IP"\n    confluence_space: "TEAM"\n')
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "config.yaml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            args = Namespace(workstream="SDX", product=None, confluence_page=None, yes=True)

            def locate(_loaded, _kind, row):
                if row.get("confluence_space"):
                    return {"space": "TEAM"}
                return {"ancestor_id": "12", "title": "Secure Data Exchange (SDX)"}

            with redirect_stdout(io.StringIO()), \
                    patch("commands.setup._tty", return_value=False), \
                    patch("commands.setup._locate_quiet", side_effect=locate):
                setup._run_folder(args, path, text)
            with open(path, encoding="utf-8") as fh:
                written = fh.read()
        self.assertNotIn('confluence_space: "TEAM"', written)
        self.assertIn('confluence_space: "APS"', written)


class ContentTypeTests(unittest.TestCase):
    def test_a_rejected_type_is_dropped_from_the_list(self):
        text = TEXT.replace(
            "confluence:\n",
            "confluence:\n  content_types: [page, blogpost]\n  title_only_types: [database, embed]\n")
        updated, status = config_edit.drop_flow_item(
            text, "confluence", "content_types", "blogpost")
        self.assertEqual(status, "removed")
        self.assertIn("content_types: [page]", updated)
        self.assertNotIn("blogpost", updated)
        again, status = config_edit.drop_flow_item(
            updated, "confluence", "content_types", "page")
        self.assertEqual(status, "refused")
        self.assertIn("content_types: [page]", again)


class RegisterSetupTests(unittest.TestCase):
    def test_a_register_is_added_and_then_its_page_is_updated(self):
        entry = {
            "type": "adr", "name": "ADRs", "title": "", "under": "",
            "page_id": "234567", "product": "", "workstream": "SDX",
        }
        text, notes, preview = setup.apply_register(TEXT, entry)
        self.assertIn("registers ADRs added", notes)
        self.assertIn('name: "ADRs"', text)
        self.assertIn('page_id: "234567"', text)
        self.assertIn("workstream: SDX", text)
        self.assertTrue(any("ADRs" in line for line in preview))

        changed = dict(entry, page_id="999")
        text, notes, _preview = setup.apply_register(text, changed)
        self.assertIn("page_id written", " ".join(notes))
        self.assertIn('page_id: "999"', text)
        self.assertEqual(text.count('name: "ADRs"'), 1)

    def test_a_noninteractive_registers_section_names_the_flags(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "config.yaml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(TEXT)
            out = io.StringIO()
            with redirect_stdout(out), patch("commands.setup._tty", return_value=False):
                setup.run(Namespace(
                    path=path, section="registers", yes=False,
                    site=None, email=None, token=None, token_env=None,
                    project=None, model_endpoint=None, model_name=None,
                    model_api_key=None, model_api_key_env=None,
                    confluence_space=None, confluence_team_page=None,
                    open_browser=False, workstream=None, product=None,
                    register_type=None, register_name=None, register_title=None,
                    under=None, page_id=None, drop_content_type=None,
                    confluence_page=None))
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), TEXT)
        self.assertIn("--register-name", out.getvalue())
        self.assertIn("optional", out.getvalue().lower())

    def test_yes_writes_a_register_and_drops_a_content_type(self):
        text = TEXT.replace(
            "confluence:\n",
            "confluence:\n  content_types: [page, blogpost]\n")
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "config.yaml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            out = io.StringIO()
            with redirect_stdout(out), patch("commands.setup._tty", return_value=False):
                setup.run(Namespace(
                    path=path, section="registers", yes=True,
                    site=None, email=None, token=None, token_env=None,
                    project=None, model_endpoint=None, model_name=None,
                    model_api_key=None, model_api_key_env=None,
                    confluence_space=None, confluence_team_page=None,
                    open_browser=False, workstream="SDX", product=None,
                    register_type="adr", register_name="ADRs", register_title=None,
                    under=None, page_id="234567", drop_content_type=None,
                    confluence_page=None))
            with open(path, encoding="utf-8") as fh:
                written = fh.read()
            self.assertIn('name: "ADRs"', written)
            self.assertIn("Updated", out.getvalue())

            out = io.StringIO()
            with redirect_stdout(out), patch("commands.setup._tty", return_value=False):
                setup.run(Namespace(
                    path=path, section="confluence", yes=True,
                    site=None, email=None, token=None, token_env=None,
                    project=None, model_endpoint=None, model_name=None,
                    model_api_key=None, model_api_key_env=None,
                    confluence_space=None, confluence_team_page=None,
                    open_browser=False, workstream=None, product=None,
                    register_type=None, register_name=None, register_title=None,
                    under=None, page_id=None, drop_content_type="blogpost",
                    confluence_page=None))
            with open(path, encoding="utf-8") as fh:
                written = fh.read()
        self.assertIn("content_types: [page]", written)
        self.assertNotIn("blogpost", written)
        self.assertIn('name: "ADRs"', written)


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
        self.assertIn("--workstream", setup_help)
        self.assertIn("--drop-content-type", setup_help)
        self.assertIn("--register-name", setup_help)
        self.assertIn("registers", setup_help)
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
                    confluence_space=None, confluence_team_page=None,
                    open_browser=False))
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), TEXT)
        self.assertIn("--confluence-space", out.getvalue())
        self.assertIn("Registers", out.getvalue())


if __name__ == "__main__":
    unittest.main()
