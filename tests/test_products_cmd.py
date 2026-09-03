import os
import tempfile
import unittest

import yaml

from commands import products as prod_cmd


CONFIG_TEXT = '''\
# ============================================================================
#  Product Manager Helper (pm) — Configuration
# ============================================================================

jira:
  base_url: "https://example.atlassian.net"
  project: "APS"

# ----------------------------------------------------------------------------
#  Products
# ----------------------------------------------------------------------------
products:

  - name: "Integration Platform"
    abbrev: "IP"
    project: "APS"

# ----------------------------------------------------------------------------
#  Workstreams
# ----------------------------------------------------------------------------
workstreams:

  - name: "Secure Data Exchange"
    abbrev: "SDX"
    product: "IP"
    components: ["Secure Data Exchange"]

# ----------------------------------------------------------------------------
#  Output
# ----------------------------------------------------------------------------
output:
  file: "weekly_report_{date}.md"
'''


class AddTests(unittest.TestCase):
    ENTRY = {"name": "Billing Platform", "abbrev": "BILL", "project": "BILL"}

    def test_entry_is_appended_to_the_list(self):
        updated = prod_cmd.add_entry_to_text(CONFIG_TEXT, self.ENTRY)
        parsed = yaml.safe_load(updated)
        self.assertEqual([p["abbrev"] for p in parsed["products"]],
                         ["IP", "BILL"])
        self.assertEqual(parsed["products"][1]["project"], "BILL")

    def test_comments_and_later_sections_survive(self):
        updated = prod_cmd.add_entry_to_text(CONFIG_TEXT, self.ENTRY)
        for comment in ("#  Product Manager Helper (pm) — Configuration",
                        "#  Products", "#  Workstreams", "#  Output"):
            self.assertIn(comment, updated)
        self.assertLess(updated.index("Billing Platform"),
                        updated.index("#  Workstreams"))

    def test_creates_the_block_when_missing(self):
        text = '''\
jira:
  project: "APS"
workstreams:
  - name: "Secure Data Exchange"
    abbrev: "SDX"
    components: ["Secure Data Exchange"]
'''
        updated = prod_cmd.add_entry_to_text(text, self.ENTRY)
        parsed = yaml.safe_load(updated)
        self.assertEqual(parsed["products"][0]["abbrev"], "BILL")
        self.assertEqual(parsed["workstreams"][0]["abbrev"], "SDX")

    def test_duplicate_abbrev_is_refused(self):
        with self.assertRaises(ValueError):
            prod_cmd.add_entry_to_text(CONFIG_TEXT, dict(self.ENTRY, abbrev="ip"))


class RemoveTests(unittest.TestCase):
    def test_named_entry_is_removed(self):
        # Add a second product first so we are not editing around workstreams.
        added = prod_cmd.add_entry_to_text(
            CONFIG_TEXT, {"name": "Billing", "abbrev": "BILL", "project": "BILL"})
        updated = prod_cmd.remove_entry_from_text(added, "BILL")
        parsed = yaml.safe_load(updated)
        self.assertEqual([p["abbrev"] for p in parsed["products"]], ["IP"])
        self.assertEqual(parsed["workstreams"][0]["abbrev"], "SDX")


class WriteGuardTests(unittest.TestCase):
    def test_a_valid_edit_is_written(self):
        text = prod_cmd.add_entry_to_text(
            CONFIG_TEXT, {"name": "Billing", "abbrev": "BILL", "project": "BILL"})
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.yaml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(CONFIG_TEXT)
            prod_cmd._write_checked(path, text)
            with open(path, "r", encoding="utf-8") as fh:
                self.assertIn("BILL", fh.read())


if __name__ == "__main__":
    unittest.main()
