"""Doctor prompt listing, and the generated customising doc stays current."""

import io
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout

from commands import doctor
from core import prompts, queries
from core.registry_docs import render


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class RegistryDocTests(unittest.TestCase):
    def test_generated_doc_matches_the_file_and_the_template_lists_ids(self):
        path = os.path.join(ROOT, "docs", "CUSTOMISING.md")
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), render(),
                             "regenerate with: python3 -c 'from core.registry_docs import main; main()' > docs/CUSTOMISING.md")
        with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as fh:
            template = fh.read()
        for prompt_id in prompts.PROMPTS:
            self.assertIn(prompt_id, template)
        for query_id in queries.QUERIES:
            self.assertIn(query_id, template, query_id)

    def test_doctor_prompts_lists_ids_and_prints_one(self):
        cfg = {}
        prompts.validate_config(cfg)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(doctor._prompt_report(cfg), 0)
        self.assertIn("refine.titles", out.getvalue())
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(doctor._prompt_report(cfg, "refine.titles"), 0)
        snap = os.path.join(ROOT, "tests", "snapshots", "prompts", "refine.titles.txt")
        with open(snap, encoding="utf-8") as fh:
            expected = fh.read()
        self.assertEqual(out.getvalue(), expected)

    def test_stale_based_on_is_marked(self):
        cfg = {"prompts": {"refine.titles": {"text": prompts.get(None, "refine.titles"), "based_on": 0}}}
        prompts.validate_config(cfg)
        out = io.StringIO()
        with redirect_stdout(out):
            doctor._prompt_report(cfg)
        self.assertIn("based_on 0", out.getvalue())


if __name__ == "__main__":
    unittest.main()
