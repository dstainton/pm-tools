import os
import tempfile
import unittest

import yaml

from commands import workstreams as ws_cmd


CONFIG_TEXT = '''\
# ============================================================================
#  Product Manager Helper (pm) — Configuration
# ============================================================================

jira:
  base_url: "https://example.atlassian.net"
  project: "APS"

# ----------------------------------------------------------------------------
#  Workstreams
# ----------------------------------------------------------------------------
workstreams:

  - name: "Secure Data Exchange"
    abbrev: "SDX"
    components: ["Secure Data Exchange"]

  - name: "API Platform"
    abbrev: "APS"
    components: ["API Platform"]

# ----------------------------------------------------------------------------
#  Output
# ----------------------------------------------------------------------------
output:
  file: "weekly_report_{date}.md"
'''


class AddTests(unittest.TestCase):
    ENTRY = {"name": "Billing Platform", "abbrev": "BIL",
             "components": ["Billing Platform"]}

    def test_entry_is_appended_to_the_list(self):
        updated = ws_cmd.add_entry_to_text(CONFIG_TEXT, self.ENTRY)
        parsed = yaml.safe_load(updated)
        self.assertEqual([w["abbrev"] for w in parsed["workstreams"]],
                         ["SDX", "APS", "BIL"])
        self.assertEqual(parsed["workstreams"][2]["components"],
                         ["Billing Platform"])

    def test_comments_and_later_sections_survive(self):
        updated = ws_cmd.add_entry_to_text(CONFIG_TEXT, self.ENTRY)
        for comment in ("#  Product Manager Helper (pm) — Configuration",
                        "#  Workstreams", "#  Output"):
            self.assertIn(comment, updated)
        # The new entry lands inside the list, before the Output banner.
        self.assertLess(updated.index("Billing Platform"),
                        updated.index("#  Output"))
        self.assertIn('file: "weekly_report_{date}.md"', updated)

    def test_optional_details_are_written_when_given(self):
        entry = dict(self.ENTRY, project="BILL",
                     confluence_space="BIL",
                     confluence_labels=["decision", "risk"],
                     sharepoint_query="Billing")
        parsed = yaml.safe_load(ws_cmd.add_entry_to_text(CONFIG_TEXT, entry))
        added = parsed["workstreams"][-1]
        self.assertEqual(added["project"], "BILL")
        self.assertEqual(added["confluence_space"], "BIL")
        self.assertEqual(added["confluence_labels"], ["decision", "risk"])
        self.assertEqual(added["sharepoint_query"], "Billing")

    def test_duplicate_abbrev_is_refused(self):
        with self.assertRaises(ValueError):
            ws_cmd.add_entry_to_text(CONFIG_TEXT, dict(self.ENTRY, abbrev="sdx"))

    def test_missing_list_is_reported(self):
        with self.assertRaises(ValueError):
            ws_cmd.add_entry_to_text("jira:\n  project: APS\n", self.ENTRY)


class RemoveTests(unittest.TestCase):
    def test_named_entry_is_removed(self):
        updated = ws_cmd.remove_entry_from_text(CONFIG_TEXT, "SDX")
        parsed = yaml.safe_load(updated)
        self.assertEqual([w["abbrev"] for w in parsed["workstreams"]], ["APS"])
        self.assertIn("#  Output", updated)

    def test_last_entry_is_removed_without_eating_the_next_section(self):
        updated = ws_cmd.remove_entry_from_text(CONFIG_TEXT, "APS")
        parsed = yaml.safe_load(updated)
        self.assertEqual([w["abbrev"] for w in parsed["workstreams"]], ["SDX"])
        self.assertEqual(parsed["output"]["file"], "weekly_report_{date}.md")

    def test_case_insensitive(self):
        parsed = yaml.safe_load(ws_cmd.remove_entry_from_text(CONFIG_TEXT, "sdx"))
        self.assertEqual([w["abbrev"] for w in parsed["workstreams"]], ["APS"])

    def test_unknown_abbrev_is_reported(self):
        with self.assertRaises(ValueError):
            ws_cmd.remove_entry_from_text(CONFIG_TEXT, "NOPE")

    def test_add_then_remove_round_trips(self):
        entry = {"name": "Billing", "abbrev": "BIL", "components": ["Billing"]}
        added = ws_cmd.add_entry_to_text(CONFIG_TEXT, entry)
        self.assertEqual(ws_cmd.remove_entry_from_text(added, "BIL"),
                         CONFIG_TEXT)


class WriteGuardTests(unittest.TestCase):
    def test_removing_the_last_workstream_is_refused(self):
        text = ws_cmd.remove_entry_from_text(
            ws_cmd.remove_entry_from_text(CONFIG_TEXT, "SDX"), "APS")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.yaml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(CONFIG_TEXT)
            with self.assertRaises(SystemExit):
                ws_cmd._write_checked(path, text)
            with open(path, "r", encoding="utf-8") as fh:
                self.assertEqual(fh.read(), CONFIG_TEXT)

    def test_a_valid_edit_is_written(self):
        text = ws_cmd.add_entry_to_text(
            CONFIG_TEXT, {"name": "Billing", "abbrev": "BIL",
                          "components": ["Billing"]})
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.yaml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(CONFIG_TEXT)
            ws_cmd._write_checked(path, text)
            with open(path, "r", encoding="utf-8") as fh:
                self.assertIn("BIL", fh.read())


if __name__ == "__main__":
    unittest.main()
