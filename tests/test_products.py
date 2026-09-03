import os
import tempfile
import unittest

from core import config, filters, products, workstreams


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
products:
  - name: "Integration Platform"
    abbrev: "IP"
    project: "APS"
  - name: "Billing Platform"
    abbrev: "BILL"
    project: "BILL"
    scopes:
      report: {sprint: any, status: open}
workstreams:
  - name: "Secure Data Exchange"
    abbrev: "SDX"
    product: "IP"
    components: ["Secure Data Exchange"]
  - name: "Invoicing"
    abbrev: "INV"
    product: "BILL"
    components: ["Invoicing"]
  - name: "Orphan"
    abbrev: "DOC"
    components: ["Documentation"]
"""


class ProductLookupTests(unittest.TestCase):
    def setUp(self):
        path = write(BASE)
        self.addCleanup(os.remove, path)
        self.cfg = config.load_config(path)

    def test_listed_products_keep_file_order(self):
        self.assertEqual([p["abbrev"] for p in products.listed_products(self.cfg)],
                         ["IP", "BILL"])

    def test_untagged_workstream_is_unassigned(self):
        doc = next(ws for ws in self.cfg["workstreams"] if ws["abbrev"] == "DOC")
        self.assertEqual(products.product_abbrev_of(doc), "UNASSIGNED")

    def test_group_puts_unassigned_last(self):
        groups = products.group_workstreams(self.cfg, self.cfg["workstreams"])
        self.assertEqual([p["abbrev"] for p, _ in groups],
                         ["IP", "BILL", "UNASSIGNED"])
        self.assertEqual([ws["abbrev"] for ws in groups[2][1]], ["DOC"])

    def test_filter_by_product_is_case_insensitive(self):
        picked = products.filter_by_product(self.cfg, self.cfg["workstreams"],
                                            "bill")
        self.assertEqual([ws["abbrev"] for ws in picked], ["INV"])

    def test_unknown_product_lists_the_valid_names(self):
        with self.assertRaises(SystemExit) as caught:
            products.filter_by_product(self.cfg, self.cfg["workstreams"], "NOPE")
        self.assertIn("Available: IP, BILL", str(caught.exception))

    def test_empty_product_filter_fails_loudly(self):
        with self.assertRaises(SystemExit) as caught:
            products.filter_by_product(self.cfg, self.cfg["workstreams"][:1],
                                       "BILL")
        self.assertIn("No workstreams belong", str(caught.exception))

    def test_config_without_products_still_loads(self):
        path = write("""\
jira:
  base_url: "https://example.atlassian.net"
  project: "APS"
workstreams:
  - name: "Secure Data Exchange"
    abbrev: "SDX"
    components: ["Secure Data Exchange"]
""")
        self.addCleanup(os.remove, path)
        cfg = config.load_config(path)
        self.assertEqual(products.product_abbrev_of(cfg["workstreams"][0]),
                         "UNASSIGNED")

    def test_unknown_product_on_a_workstream_fails_at_load(self):
        with self.assertRaises(SystemExit) as caught:
            path = write(BASE.replace('product: "IP"', 'product: "NOPE"'))
            self.addCleanup(os.remove, path)
            config.load_config(path)
        self.assertIn("unknown product NOPE", str(caught.exception))

    def test_duplicate_product_abbrev_fails(self):
        text = """\
jira:
  project: "APS"
  base_url: "https://example.atlassian.net"
products:
  - name: "A"
    abbrev: "IP"
  - name: "B"
    abbrev: "ip"
workstreams:
  - name: "S"
    abbrev: "S"
    components: ["S"]
"""
        path = write(text)
        self.addCleanup(os.remove, path)
        with self.assertRaises(SystemExit) as caught:
            config.load_config(path)
        self.assertIn("unique", str(caught.exception))

    def test_reserved_unassigned_abbrev_is_rejected(self):
        text = """\
jira:
  project: "APS"
  base_url: "https://example.atlassian.net"
products:
  - name: "None"
    abbrev: "UNASSIGNED"
workstreams:
  - name: "S"
    abbrev: "S"
    components: ["S"]
"""
        path = write(text)
        self.addCleanup(os.remove, path)
        with self.assertRaises(SystemExit) as caught:
            config.load_config(path)
        self.assertIn("reserved", str(caught.exception))


class ProductDefaultsTests(unittest.TestCase):
    def test_workstream_inherits_the_product_project(self):
        cfg = {
            "jira": {"project": "APS"},
            "products": [{"abbrev": "BILL", "project": "BILL"}],
        }
        ws = {"abbrev": "INV", "product": "BILL",
              "components": ["Invoicing"],
              "_resolved_epic_keys": ["BILL-1"],
              "_resolved_tagged_keys": []}
        self.assertEqual(workstreams.project_of(cfg, ws), "BILL")
        self.assertIn('project = "BILL"',
                      workstreams.scope_jql(cfg, ws, "report"))

    def test_workstream_project_wins_over_product(self):
        cfg = {
            "jira": {"project": "APS"},
            "products": [{"abbrev": "BILL", "project": "BILL"}],
        }
        ws = {"abbrev": "INV", "product": "BILL", "project": "INV"}
        self.assertEqual(workstreams.project_of(cfg, ws), "INV")

    def test_product_scopes_sit_between_global_and_workstream(self):
        cfg = {
            "scopes": {"report": {"sprint": "open"}},
            "products": [{"abbrev": "BILL",
                          "scopes": {"report": {"sprint": "any",
                                                "status": "open"}}}],
        }
        ws = {"abbrev": "INV", "product": "BILL"}
        options = filters.scope_options(cfg, ws, "report")
        self.assertEqual(options["sprint"], "any")
        self.assertEqual(options["status"], "open")

        ws["scopes"] = {"report": {"status": "done"}}
        options = filters.scope_options(cfg, ws, "report")
        self.assertEqual(options["status"], "done")
        self.assertEqual(options["sprint"], "any")


if __name__ == "__main__":
    unittest.main()
