import os
import tempfile
import unittest
from unittest.mock import patch

from core import config


def write(text):
    handle = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False,
                                        encoding="utf-8")
    handle.write(text)
    handle.close()
    return handle.name


BASE = """\
jira:
  base_url: "https://example.atlassian.net"
  project: "APS"
workstreams:
  - name: "Secure Data Exchange"
    abbrev: "SDX"
    components: ["Secure Data Exchange"]
"""


class LoadTests(unittest.TestCase):
    def _load(self, text):
        path = write(text)
        self.addCleanup(os.remove, path)
        return config.load_config(path)

    def test_a_minimal_workstream_loads(self):
        cfg = self._load(BASE)
        self.assertEqual(cfg["workstreams"][0]["abbrev"], "SDX")

    def test_env_placeholders_are_expanded(self):
        text = BASE.replace('"https://example.atlassian.net"',
                            '"${ENV:PM_TEST_URL}"')
        with patch.dict(os.environ, {"PM_TEST_URL": "https://real.example"}):
            cfg = self._load(text)
        self.assertEqual(cfg["jira"]["base_url"], "https://real.example")

    def test_missing_env_placeholder_fails(self):
        text = BASE.replace('"APS"', '"${ENV:PM_TEST_MISSING}"')
        with self.assertRaises(SystemExit):
            self._load(text)

    def test_components_without_a_project_fails(self):
        text = BASE.replace('  project: "APS"\n', "")
        with self.assertRaises(SystemExit) as caught:
            self._load(text)
        self.assertIn("no project", str(caught.exception))

    def test_workstream_without_components_or_jql_fails(self):
        with self.assertRaises(SystemExit) as caught:
            self._load(BASE.replace('    components: ["Secure Data Exchange"]\n',
                                    ""))
        self.assertIn("cannot tell which issues", str(caught.exception))

    def test_duplicate_abbrev_fails(self):
        text = BASE + """\
  - name: "Another"
    abbrev: "sdx"
    components: ["Another"]
"""
        with self.assertRaises(SystemExit) as caught:
            self._load(text)
        self.assertIn("unique", str(caught.exception))

    def test_missing_abbrev_fails(self):
        with self.assertRaises(SystemExit):
            self._load(BASE.replace('    abbrev: "SDX"\n', ""))

    def test_no_workstreams_at_all_points_at_the_add_command(self):
        with self.assertRaises(SystemExit) as caught:
            self._load('jira:\n  project: "APS"\nworkstreams: []\n')
        self.assertIn("pm workstreams add", str(caught.exception))

    def test_unknown_membership_setting_fails(self):
        with self.assertRaises(SystemExit) as caught:
            self._load(BASE + "membership:\n  inherit_from_epic: true\n")
        self.assertIn("Unknown membership setting", str(caught.exception))

    def test_unknown_scope_option_fails(self):
        with self.assertRaises(SystemExit):
            self._load(BASE + "scopes:\n  lint:\n    statuz: open\n")

    def test_legacy_jql_workstream_still_loads(self):
        cfg = self._load("""\
jira:
  base_url: "https://example.atlassian.net"
workstreams:
  - name: "Old Stream"
    abbrev: "OLD"
    jira_jql: 'project = OLD AND sprint in openSprints()'
""")
        self.assertEqual(cfg["workstreams"][0]["abbrev"], "OLD")


class FilterWorkstreamTests(unittest.TestCase):
    CFG = {"workstreams": [{"abbrev": "SDX"}, {"abbrev": "APS"},
                           {"abbrev": "ITK"}]}

    def test_no_selector_returns_everything(self):
        self.assertEqual(len(config.filter_workstreams(self.CFG, None)), 3)

    def test_selection_is_case_insensitive_and_ordered(self):
        picked = config.filter_workstreams(self.CFG, "itk,sdx")
        self.assertEqual([w["abbrev"] for w in picked], ["ITK", "SDX"])

    def test_a_typo_lists_the_valid_names(self):
        with self.assertRaises(SystemExit) as caught:
            config.filter_workstreams(self.CFG, "sdz")
        self.assertIn("Available: SDX, APS, ITK", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
