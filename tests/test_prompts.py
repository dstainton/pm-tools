"""Prompt registry: defaults match the old strings, overrides fail closed."""

import os
import tempfile
import unittest
from unittest.mock import patch

from core import config, model, prompts


SNAP = os.path.join(os.path.dirname(__file__), "snapshots", "prompts")


def _cfg(**prompts_block):
    cfg = {"prompts": prompts_block, "_config_path": os.path.join(tempfile.gettempdir(), "pm.yaml")}
    prompts.validate_config(cfg)
    return cfg


class SnapshotTests(unittest.TestCase):
    def test_rendered_defaults_match_the_snapshots(self):
        for prompt_id in prompts.PROMPTS:
            path = os.path.join(SNAP, prompt_id + ".txt")
            with open(path, encoding="utf-8") as fh:
                expected = fh.read()
            got = prompts.get(None, prompt_id, audience="stakeholders", product="Product")
            self.assertEqual(
                got, expected,
                f"{prompt_id}: the default changed: bump `version` and update the snapshot")


class RenderTests(unittest.TestCase):
    def test_json_braces_stay_and_known_names_are_filled(self):
        text = prompts.render('{"text": string} {name} {{x}}', {"name": "Ada"})
        self.assertEqual(text, '{"text": string} Ada {x}')


class OverrideTests(unittest.TestCase):
    def test_append_goes_before_the_example(self):
        cfg = _cfg(**{"report.section": {"append": "8. Say hello."}})
        text = prompts.get(cfg, "report.section", audience="stakeholders")
        self.assertLess(text.find("8. Say hello."), text.find("Example of one filled section:"))
        self.assertIn("\n\n8. Say hello.\n\nExample of one filled section:", text)

    def test_text_replaces_and_file_is_read_beside_the_config(self):
        cfg = _cfg(**{"refine.tail": {"text": "Send the array.\n"}})
        self.assertEqual(prompts.get(cfg, "refine.tail"), "Send the array.\n")

        folder = tempfile.mkdtemp()
        path = os.path.join(folder, "titles.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(prompts.get(None, "refine.titles"))
        cfg = {"prompts": {"refine.titles": {"file": "titles.txt", "based_on": 1}},
               "_config_path": os.path.join(folder, "pm.yaml")}
        prompts.validate_config(cfg)
        self.assertEqual(prompts.source(cfg, "refine.titles"), "file titles.txt")
        self.assertEqual(prompts.get(cfg, "refine.titles"), prompts.get(None, "refine.titles"))

    def test_heading_values_change_the_rendered_prompt(self):
        cfg = _cfg(**{"report.section": {"values": {"headings": {"risks": "Risks and issues"}}}})
        self.assertIn("### Risks and issues", prompts.get(cfg, "report.section", audience="a"))
        self.assertEqual(prompts.headings(cfg)[-1], "Risks and issues")

    def _exits(self, block, snippet):
        with self.assertRaises(SystemExit) as caught:
            _cfg(**block)
        self.assertIn(snippet, str(caught.exception))

    def test_load_errors_name_the_fix(self):
        self._exits({"nope": {"text": "x"}}, "unknown id")
        self._exits({"refine.titles": {"nope": "x"}}, "unknown key")
        self._exits({"refine.titles": {"text": "Return a list."}}, "JSON array")
        self._exits({"report.section": {"text": "Hello {audience}."}}, "must keep {headings}")
        self._exits({"report.section": {"text": "Hello {nope} {headings} {empty_section} {first_run_line}"}},
                    "unknown placeholder")
        self._exits({"report.section": {"values": {"headings": {"nope": "X"}}}}, "unknown heading")
        folder = tempfile.mkdtemp()
        cfg = {"prompts": {"refine.titles": {"file": "missing.txt"}},
               "_config_path": os.path.join(folder, "pm.yaml")}
        with self.assertRaises(SystemExit) as caught:
            prompts.validate_config(cfg)
        self.assertIn("cannot read", str(caught.exception))


class ReportCallTests(unittest.TestCase):
    def test_append_reaches_the_model_and_the_second_call_is_cached(self):
        cfg = _cfg(**{"report.section": {"append": "8. Say hello."}})
        seen = []

        def fake_call(model_cfg, system, user, **kwargs):
            seen.append(system)
            return "ok"

        with patch("core.model.call_model", side_effect=fake_call):
            model.infer_report_section(
                {}, "stakeholders",
                {"name": "Secure Data Exchange", "abbrev": "SDX"},
                [], "First run.", cfg=cfg)
            model.infer_report_section(
                {"_cache_hit": True}, "stakeholders",
                {"name": "Secure Data Exchange", "abbrev": "SDX"},
                [], "First run.", cfg=cfg)
        self.assertIn("8. Say hello.", seen[0])
        self.assertEqual(seen[0], seen[1])

    def test_load_config_records_the_path_and_accepts_no_prompts_block(self):
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, "pm.yaml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("config_version: 5\nproducts: []\nworkstreams:\n"
                     "  - name: Stream\n    abbrev: ST\n    jira_jql: project = APS\n")
        loaded = config.load_config(path)
        self.assertEqual(loaded["_config_path"], os.path.abspath(path))
        self.assertEqual(prompts.source(loaded, "report.section"), "built-in")


if __name__ == "__main__":
    unittest.main()
