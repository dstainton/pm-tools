"""Cached page summaries and the model Epic pick."""

import os
import tempfile
import unittest
from unittest.mock import patch

from core import page_summaries


def _page(version="1", text="Certificates rotate every 90 days."):
    return {"page_id": "1001", "version": version, "type": "page", "title": "Decision",
            "labels": [], "body_text": text, "updated": "2026-09-24", "title_only": False,
            "kind": ""}


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.cfg = {"cache": {"path": self.dir, "ttl_seconds": 300},
                    "model": {"name": "fake"}, "pages": {"max_summaries": 1}}

    def test_a_version_is_summarised_once(self):
        calls = {"n": 0}

        def fake_json(model_cfg, system, user):
            calls["n"] += 1
            return [{"summary": "Certificates rotate every 90 days.", "kind": "nope"}], None

        with patch("core.model.call_model_json", side_effect=fake_json):
            first = page_summaries.summarise(self.cfg, _page())
            second = page_summaries.summarise(self.cfg, _page())
        self.assertEqual(first["kind"], "other")
        self.assertEqual(calls["n"], 1)
        self.assertEqual(second["summary"], first["summary"])
        with patch("core.model.call_model_json", side_effect=fake_json):
            page_summaries.summarise(self.cfg, _page(version="2"))
            page_summaries.summarise(self.cfg, _page(), refresh=True)
        self.assertEqual(calls["n"], 3)

    def test_the_cap_lists_the_rest(self):
        def fake_json(model_cfg, system, user):
            return [{"summary": "One.", "kind": "decision"}], None

        pages = [_page(), {**_page(), "page_id": "1002", "updated": "2026-09-23"}]
        with patch("core.model.call_model_json", side_effect=fake_json):
            calls = page_summaries.fill(self.cfg, pages)
        self.assertEqual(calls, 1)
        pending = [page for page in pages if page.get("unsummarised")]
        self.assertEqual(len(pending), 1)

    def test_a_pick_outside_the_list_is_ignored(self):
        page = _page()
        page["summary"] = "A decision."

        def fake_json(model_cfg, system, user):
            return [{"epic": "NOPE-1"}], None

        with patch("core.model.call_model_json", side_effect=fake_json):
            chosen = page_summaries.pick_epic(
                self.cfg, page, [{"key": "APS-1", "summary": "Secure"}])
        self.assertEqual(chosen, "")
        self.assertTrue(os.path.isdir(self.dir))


if __name__ == "__main__":
    unittest.main()
