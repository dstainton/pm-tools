"""Decision, risk and ADR registers."""

import datetime as dt
import unittest

from core import config, registers
from tests.fake_jira import FakeJira


def _storage(status, extra=""):
    return (
        "<table><tr><th>Status</th><td>"
        f'<ac:structured-macro ac:name="status">'
        f'<ac:parameter ac:name="title">{status}</ac:parameter>'
        "</ac:structured-macro></td></tr>"
        "<tr><th>Owner</th><td>Dana</td></tr>"
        f"{extra}</table>"
    )


def _pages():
    day = lambda n: (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=n)).strftime(
        "%Y-%m-%dT%H:%M:%S.000+0000")
    child = lambda pid, title, when, created, status, body: {
        "id": pid, "space": "APS", "title": title, "type": "page",
        "when": when, "created": created, "body": body, "by": "Dana",
        "storage": _storage(status),
        "ancestors": [{"id": "5000", "title": "Decision log"}],
    }
    return [
        {"id": "5000", "space": "APS", "title": "Decision log", "type": "page",
         "when": day(1), "by": "Dana", "body": "summary"},
        child("5001", "DEC-014 Rotate certificates every 90 days", day(1), day(1),
              "ACCEPTED", "Certificates rotate every 90 days. See APS-1."),
        child("5002", "DEC-013 Rate limit defaults", day(40), day(40), "Accepted", "old"),
        child("5003", "DEC-011 Tenant rate limits", day(2), day(40), "ACCEPTED", "1000 a minute"),
        {"id": "6000", "space": "APS", "title": "Risk register", "type": "page",
         "when": day(2), "body": "risks"},
        {"id": "6001", "space": "APS", "title": "RISK-007 HSM capacity during rotation",
         "type": "page", "when": day(2), "created": day(2), "by": "Sam",
         "body": "Capacity headroom is thin.",
         "storage": _storage("Open", "<tr><th>Rating</th><td>High</td></tr>"),
         "ancestors": [{"id": "6000", "title": "Risk register"}]},
    ]


class RegisterTests(unittest.TestCase):
    def setUp(self):
        self.jira = FakeJira([], pages=_pages())
        self.jira.__enter__()
        self.addCleanup(lambda: self.jira.__exit__(None, None, None))
        self.cfg = {
            "jira": {"base_url": self.jira.url, "email": "a", "api_token": "t",
                     "project": "APS"},
            "confluence": {"base_url": self.jira.url + "/wiki", "email": "a",
                           "api_token": "t", "max_results": 50},
            "products": [{"abbrev": "IP"}],
            "workstreams": [{"abbrev": "SDX"}],
            "_products": [{"abbrev": "IP"}],
            "_workstreams": [{"abbrev": "SDX"}],
            "registers": [
                {"type": "decision", "name": "Decision log", "space": "APS",
                 "title": "Decision log", "product": "IP", "fields": ["Owner"]},
                {"type": "risk", "name": "Risk register", "space": "APS",
                 "title": "Risk register", "product": "IP",
                 "fields": ["Owner", "Rating"],
                 "highlight": {"field": "Rating", "values": ["High", "Critical"]}},
            ],
        }
        self.window = {"start": dt.date.today() - dt.timedelta(days=7)}

    def test_new_changed_and_removed(self):
        previous = {"_registers": {"decision:5000": {
            "5003": {"title": "DEC-011 Tenant rate limits", "version": 1, "status": "Proposed"},
            "5009": {"title": "DEC-009 Legacy key escrow", "version": 1, "status": "Accepted"},
            "5002": {"title": "DEC-013 Rate limit defaults", "version": 1, "status": "Accepted"},
        }}}
        found, skip = registers.gather(self.cfg, self.window, previous)
        decision = next(row for row in found if row["type"] == "decision")
        by_title = {row["title"]: row for row in decision["entries"]}
        self.assertEqual(by_title["DEC-014 Rotate certificates every 90 days"]["change"], "new")
        self.assertEqual(by_title["DEC-011 Tenant rate limits"]["change"], "changed")
        self.assertEqual(by_title["DEC-011 Tenant rate limits"]["status_was"], "Proposed")
        self.assertNotIn("DEC-013 Rate limit defaults", by_title)
        self.assertEqual(decision["removed"][0]["page_id"], "5009")
        self.assertIn("5000", skip)
        self.assertIn("5001", skip)
        risk = next(row for row in found if row["type"] == "risk")
        self.assertTrue(risk["entries"][0]["high"])
        self.assertEqual(risk["entries"][0]["change"], "new")

    def test_properties_reads_a_status_macro(self):
        html = _storage("ACCEPTED")
        self.assertEqual(registers.properties(html, ["Status", "Owner"])["Status"], "Accepted")
        self.assertEqual(registers.properties(html, ["Status", "Owner"])["Owner"], "Dana")
        self.assertEqual(registers.properties(html, ["Missing"]), {})

    def test_missing_summary_page_returns_none(self):
        reg = {"type": "adr", "name": "Architecture decisions", "space": "APS",
               "title": "Missing", "page_id": ""}
        self.assertIsNone(registers.gather_one(self.cfg, reg, self.window, {}))

    def test_explicit_window_snapshot_is_callers_job(self):
        found, _skip = registers.gather(self.cfg, self.window, {})
        snap = registers.snapshot(found)
        self.assertIn("5001", snap["decision:5000"])
        self.assertIn("5002", snap["decision:5000"])

    def test_risk_cannot_be_partner_visible(self):
        cfg = {"products": [{"abbrev": "IP", "name": "IP"}],
               "workstreams": [{"name": "S", "abbrev": "SDX", "components": ["A"]}],
               "registers": [{"type": "risk", "name": "Risk register",
                              "space": "APS", "title": "Risk register",
                              "partner_visible": True}]}
        with self.assertRaises(SystemExit) as caught:
            config._validate_registers(cfg)
        self.assertIn("cannot be partner_visible", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
