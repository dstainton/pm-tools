import io
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from unittest import mock

from core import writes


class AdfTests(unittest.TestCase):
    def test_adf_doc_wraps_plain_text(self):
        doc = writes.adf_doc("hello")
        self.assertEqual(doc["type"], "doc")
        self.assertEqual(doc["content"][0]["content"][0]["text"], "hello")


class ActionBuilderTests(unittest.TestCase):
    def test_update_issue(self):
        action = writes.action_update_issue(
            "APS-30", {"duedate": "2026-09-17"}, kind="overdue",
            summary="Rotate certs")
        self.assertEqual(action["method"], "PUT")
        self.assertEqual(action["path"], "/rest/api/3/issue/APS-30")
        self.assertEqual(action["body"]["fields"]["duedate"], "2026-09-17")

    def test_comment_uses_adf(self):
        action = writes.action_comment("APS-11", "Checking in")
        self.assertEqual(action["method"], "POST")
        self.assertEqual(action["body"]["body"]["type"], "doc")


class ConfirmTests(unittest.TestCase):
    def test_dry_run_does_not_write(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertFalse(writes.should_write(Namespace(dry_run=True,
                                                           yes=False)))
        self.assertIn("nothing was sent", buf.getvalue())

    def test_yes_writes(self):
        self.assertTrue(writes.should_write(Namespace(dry_run=False, yes=True)))

    def test_non_interactive_without_yes_exits(self):
        with mock.patch("sys.stdin") as stdin:
            stdin.isatty.return_value = False
            with self.assertRaises(SystemExit) as err:
                writes.should_write(Namespace(dry_run=False, yes=False))
        self.assertIn("Refusing to write", str(err.exception))
