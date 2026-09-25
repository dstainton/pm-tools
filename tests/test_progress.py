"""Progress lines for commands that take a while."""

import io
import time
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from core import model, progress


class Tty(io.StringIO):
    def isatty(self):
        return True


def _reply(text="pong"):
    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": text}}]}

    return Response()


def _model():
    return {
        "endpoint": "http://127.0.0.1:9/v1/chat/completions",
        "name": "qwen", "temperature": 0.4, "json_temperature": 0.2,
        "top_p": 0.8, "top_k": 20, "presence_penalty": 1.5,
        "max_tokens": 32, "timeout": 5, "enable_thinking": False,
    }


class ProgressTests(unittest.TestCase):
    def setUp(self):
        progress.finish()
        progress._state["raw"] = None
        progress._state["wrapper"] = None
        progress._state["out"] = None

    def tearDown(self):
        self.setUp()

    def test_a_step_is_one_plain_line_when_output_is_captured(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            progress.start(progress.numbered(1, 3, "Secure Data Exchange — reading Jira"))
            progress.note("200 issues")
            progress.finish()
        self.assertEqual(buf.getvalue(),
                         "[1/3] Secure Data Exchange — reading Jira\n")
        self.assertFalse(progress.busy())

    def test_a_long_step_says_it_is_still_going(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            progress.start("Reading Jira")
            progress._state["t0"] = time.monotonic() - 20
            progress._beat_once()
        self.assertIn("Reading Jira\n", buf.getvalue())
        self.assertIn("... still Reading Jira (20s)", buf.getvalue())

    def test_a_terminal_rewrites_one_line_and_then_keeps_it(self):
        buf = Tty()
        with redirect_stdout(buf):
            progress.start("Reading Jira")
            progress._state["t0"] = time.monotonic() - 5
            progress._beat_once()
            progress.note("200 issues")
            progress.finish()
            shown = buf.getvalue()
        self.assertIn("\r", shown)
        self.assertIn("Reading Jira — 200 issues", shown)
        self.assertIn("(5s)", shown)
        self.assertTrue(shown.endswith("\n"))

    def test_one_step_has_no_counter(self):
        self.assertEqual(progress.numbered(1, 1, "Reading Jira"), "Reading Jira")

    def test_a_fast_model_call_stays_quiet_until_it_takes_a_second(self):
        buf = io.StringIO()
        with redirect_stdout(buf), patch("core.model.requests.post",
                                         return_value=_reply()) as post:
            model.call_model(_model(), "sys", "pong", use_cache=False)
            self.assertEqual(post.call_count, 1)
            self.assertEqual(buf.getvalue(), "")
            progress.start("Asking the model", hold=True)
            progress._state["t0"] = time.monotonic() - 2
            progress._beat_once()
            progress.start("Writing the SDX section")
            model.call_model(_model(), "sys", "pong", use_cache=False)
            progress.finish()
        text = buf.getvalue()
        self.assertEqual(text.count("Asking the model"), 1)
        self.assertIn("Writing the SDX section", text)

    def test_ticks_count_every_call_including_the_first(self):
        buf = io.StringIO()
        settings = {"_progress_total": 1, "_progress_done": 0}
        with redirect_stdout(buf):
            model.tick(settings, "SDX — writing the section")
            settings["_progress_total"] = 2
            model.tick(settings, "APS — writing the section")
            progress.finish()
        text = buf.getvalue()
        self.assertIn("SDX — writing the section", text)
        self.assertNotIn("[1/1]", text)
        self.assertIn("[2/2] APS — writing the section", text)


if __name__ == "__main__":
    unittest.main()
