"""Audience file names, state paths, and redaction."""

import datetime as dt
import unittest

from core import audience


class AudienceTests(unittest.TestCase):
    def test_pm_names_stay_and_leadership_gets_its_own(self):
        cfg = {"output": {"file": "weekly_report_{date}.md",
                          "state_file": "report_state.json", "directory": "."}}
        day = "2026-09-25"
        self.assertEqual(audience.output_name(cfg, "pm", day),
                         "weekly_report_2026-09-25.md")
        self.assertEqual(audience.output_name(cfg, "leadership", day),
                         "weekly_report_leadership_2026-09-25.md")
        self.assertTrue(audience.state_path(cfg, "pm", None).endswith("report_state.json"))
        self.assertTrue(audience.state_path(cfg, "leadership", None).endswith(
            "report_state_leadership.json"))

    def test_bad_default_is_rejected(self):
        from core import config
        with self.assertRaises(SystemExit) as caught:
            config._validate_audiences({"audiences": {"default": "boss"}})
        self.assertIn("audiences.default", str(caught.exception))

    def test_redact_drops_a_person_and_a_hidden_key(self):
        text, removed = audience.redact(
            "Hello A. Lee\nVisible [APS-1]\nHidden APS-10",
            ["A. Lee"], {"APS-1"}, drop_all_keys=False)
        self.assertNotIn("A. Lee", text)
        self.assertNotIn("APS-10", text)
        self.assertIn("APS-1", text)
        self.assertEqual(removed, 2)


if __name__ == "__main__":
    unittest.main()
