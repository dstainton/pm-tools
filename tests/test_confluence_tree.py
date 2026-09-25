"""One Confluence space: team page, product folder, labelled registers."""

import datetime as dt
import unittest
from unittest.mock import patch

from commands import report as report_cmd
from core import config, filters, pages, registers, sources
from tests.fake_jira import FakeJira


def _when(days_ago):
    moment = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def _ancestors(*pairs):
    return [{"id": page_id, "title": title} for page_id, title in pairs]


def _tree():
    now = _when(0)
    old = "2020-01-01T00:00:00.000+0000"
    team = ("100", "API Program Services")
    product = ("200", "Integration Platform")
    stream = ("210", "Secure Data Exchange")
    shared = ("7000", "Risks")
    return [
        {"id": "100", "space": "APS", "title": "API Program Services", "type": "page",
         "when": now},
        {"id": "200", "space": "APS", "title": "Integration Platform", "type": "folder",
         "when": old, "ancestors": _ancestors(team)},
        {"id": "210", "space": "APS", "title": "Secure Data Exchange", "type": "page",
         "when": now, "ancestors": _ancestors(team, product)},
        {"id": "211", "space": "APS", "title": "SDX runbook", "type": "page",
         "when": now, "ancestors": _ancestors(team, product, stream)},
        {"id": "220", "space": "APS", "title": "Product overview", "type": "page",
         "when": now, "ancestors": _ancestors(team, product)},
        {"id": "300", "space": "APS", "title": "Elsewhere", "type": "page",
         "when": now, "ancestors": _ancestors(team)},
        {"id": "7000", "space": "APS", "title": "Risks", "type": "page",
         "when": old, "ancestors": _ancestors(team)},
        {"id": "8000", "space": "APS", "title": "Risks", "type": "folder",
         "when": old, "ancestors": _ancestors(team, product)},
        {"id": "8001", "space": "APS", "title": "RISK-1 Certificate rotation", "type": "page",
         "when": now, "created": now, "labels": ["SDX"],
         "ancestors": _ancestors(team, shared, product, ("8000", "Risks"))},
        {"id": "8002", "space": "APS", "title": "RISK-2 Unassigned", "type": "page",
         "when": now, "created": now,
         "ancestors": _ancestors(team, shared)},
        {"id": "8003", "space": "APS", "title": "RISK-3 Platform", "type": "page",
         "when": now, "created": now, "labels": ["IP"],
         "ancestors": _ancestors(team, shared)},
    ]


class TreeTests(unittest.TestCase):
    def setUp(self):
        self.jira = FakeJira([], pages=_tree())
        self.jira.__enter__()
        self.addCleanup(lambda: self.jira.__exit__(None, None, None))
        self.cfg = {
            "jira": {"base_url": self.jira.url, "email": "a", "api_token": "t",
                     "project": "APS"},
            "confluence": {
                "base_url": self.jira.url + "/wiki", "email": "a", "api_token": "t",
                "max_results": 50, "space": "APS", "root_title": "API Program Services",
            },
            "pages": {"summaries": False, "follow_jira_links": False,
                      "match_epics_with_model": False},
            "products": [{
                "abbrev": "IP", "name": "Integration Platform",
                "confluence_page": "Integration Platform",
            }],
            "workstreams": [
                {"abbrev": "SDX", "name": "Secure Data Exchange", "product": "IP",
                 "confluence_page": "Secure Data Exchange"},
                {"abbrev": "ITK", "name": "Integration Toolkit", "product": "IP"},
            ],
        }
        self.window = {"start": dt.date.today() - dt.timedelta(days=7)}

    def test_workstream_page_is_the_ancestor(self):
        cql = filters.build_cql(self.cfg["workstreams"][0], self.cfg, scope="space")
        self.assertIn('space = "APS"', cql)
        self.assertIn("ancestor = 210", cql)
        self.assertNotIn("ancestor = 100", cql)
        found = pages.gather(
            self.cfg, self.cfg["workstreams"][0], window=self.window)
        self.assertEqual([page["title"] for page in found], ["SDX runbook"])

    def test_missing_page_does_not_read_the_space(self):
        cql = filters.build_cql(
            {"abbrev": "SDX", "confluence_page": "Missing"}, self.cfg, scope="space")
        self.assertIsNone(cql)

    def test_old_folder_is_found_outside_the_lookback(self):
        original = pages.cache_fetch

        def skip_title(cfg, kind, key_parts, fetch):
            if kind == "confluence-title":
                return None
            return original(cfg, kind, key_parts, fetch)

        with patch("core.pages.cache_fetch", skip_title):
            root = registers.resolve_root(self.cfg, {
                "type": "risk", "name": "Risks", "title": "Risks", "under_id": "200",
            })
        self.assertEqual(root["page_id"], "8000")

    def test_under_picks_the_folder_and_labels_split(self):
        self.cfg["registers"] = [
            {"type": "risk", "name": "IP risks", "title": "Risks",
             "under": "Integration Platform", "product": "IP"},
            {"type": "risk", "name": "All risks", "title": "Risks",
             "under": "API Program Services", "split": "label"},
        ]
        found, skip = registers.gather(self.cfg, self.window, {})
        # 8001 is labelled SDX, so the shared register's workstream slice
        # keeps it and the product register is not listed as well.
        self.assertNotIn("IP risks", [row["name"] for row in found])
        scopes = {}
        for row in found:
            if row["name"] != "All risks":
                continue
            scope = row["scope"]
            key = scope.get("workstream") or scope.get("product") or ""
            scopes[key] = [item["page_id"] for item in row["catalog"]]
        self.assertEqual(scopes["SDX"], ["8001"])
        self.assertEqual(scopes["IP"], ["8003"])
        self.assertEqual(scopes[""], ["8002"])
        memory = self.cfg["_register_memory"]
        self.assertIn("8001", memory["risk:8000"])
        self.assertEqual(sorted(memory["risk:7000"]), ["8001", "8002", "8003"])
        self.assertIn("8001", skip)
        self.assertIn("7000", skip)

    def test_product_folder_pages_attach_once(self):
        ws = self.cfg["workstreams"][0]
        gathered = pages.gather(self.cfg, ws, window=self.window)
        row = {"items": list(gathered), "epics": []}
        prepared = [(ws, row)]
        groups = [(self.cfg["products"][0], [ws])]
        report_cmd._attach_product_pages(self.cfg, groups, prepared, self.window, set())
        titles = [item["title"] for item in row["items"]]
        self.assertEqual(titles.count("SDX runbook"), 1)
        self.assertIn("Product overview", titles)
        self.assertNotIn("Elsewhere", titles)
        product_titles = [item["title"] for item in row.get("product_pages") or []]
        self.assertIn("Product overview", product_titles)
        self.assertNotIn("SDX runbook", product_titles)


class DedupeTests(unittest.TestCase):
    def test_a_product_register_keeps_an_unlabelled_shared_page(self):
        page = {"page_id": "2", "title": "R"}
        product = {
            "type": "risk", "name": "IP risks", "root": {"page_id": "8"},
            "scope": {"product": "IP"}, "reg": {"product": "IP"},
            "entries": [dict(page)], "catalog": [dict(page)], "removed": [],
            "snapshot_catalog": [dict(page)],
        }
        shared = {
            "type": "risk", "name": "All risks", "root": {"page_id": "7"},
            "scope": {}, "reg": {"split": "label"},
            "entries": [dict(page)], "catalog": [dict(page)], "removed": [],
            "snapshot_catalog": [dict(page)],
        }
        kept = registers.dedupe_entries([product, shared])
        self.assertEqual([row["name"] for row in kept], ["IP risks"])


class SplitScopeTests(unittest.TestCase):
    def test_a_workstream_label_beats_a_product_label(self):
        cfg = {
            "products": [{"abbrev": "IP"}, {"abbrev": "ZZ"}],
            "workstreams": [
                {"abbrev": "SDX", "product": "IP"},
                {"abbrev": "ITK", "product": "IP"},
                {"abbrev": "OTHER", "product": "ZZ"},
            ],
        }
        owned = {"product": "IP", "split": "label"}
        self.assertEqual(registers._scope_from_labels(cfg, owned, ["SDX"]),
                         {"workstream": "SDX"})
        self.assertEqual(registers._scope_from_labels(cfg, owned, ["sdx"]),
                         {"workstream": "SDX"})
        self.assertEqual(registers._scope_from_labels(cfg, owned, ["IP"]),
                         {"product": "IP"})
        self.assertEqual(registers._scope_from_labels(cfg, owned, []),
                         {"product": "IP"})
        self.assertEqual(registers._scope_from_labels(cfg, owned, ["SDX", "ITK"]),
                         {"product": "IP"})
        self.assertEqual(registers._scope_from_labels(cfg, owned, ["OTHER"]),
                         {"product": "IP"})
        shared = {"split": "label"}
        self.assertEqual(registers._scope_from_labels(cfg, shared, ["SDX", "IP"]),
                         {"workstream": "SDX"})
        self.assertEqual(registers._scope_from_labels(cfg, shared, []), {})
        self.assertEqual(registers._scope_from_labels(cfg, shared, ["nope"]), {})


class RegisterConfigTests(unittest.TestCase):
    def _cfg(self, registers, confluence=None):
        cfg = {
            "products": [{"abbrev": "IP", "name": "IP"}],
            "workstreams": [{"name": "S", "abbrev": "SDX", "components": ["A"]}],
            "registers": registers,
        }
        if confluence is not None:
            cfg["confluence"] = confluence
        return cfg

    def test_space_may_be_omitted_when_the_team_space_is_set(self):
        config._validate_registers(self._cfg(
            [{"type": "risk", "name": "Risks", "title": "Risks", "product": "IP"}],
            {"space": "APS"}))

    def test_title_without_a_space_is_rejected(self):
        with self.assertRaises(SystemExit) as caught:
            config._validate_registers(self._cfg(
                [{"type": "risk", "name": "Risks", "title": "Risks"}]))
        self.assertIn("space", str(caught.exception))

    def test_split_must_be_label_and_not_a_fixed_workstream(self):
        with self.assertRaises(SystemExit) as caught:
            config._validate_registers(self._cfg(
                [{"type": "risk", "name": "Risks", "page_id": "1", "split": "folder"}]))
        self.assertIn("split must be label", str(caught.exception))
        with self.assertRaises(SystemExit) as caught:
            config._validate_registers(self._cfg(
                [{"type": "risk", "name": "Risks", "page_id": "1",
                  "workstream": "SDX", "split": "label"}]))
        self.assertIn("fixed workstream", str(caught.exception))


class TitleSearchTests(unittest.TestCase):
    def test_a_rejected_folder_type_is_retried_as_a_page(self):
        calls = []

        def fake(cfg, cql, since=None, limit=None):
            calls.append((cql, since))
            if "folder" in cql:
                raise RuntimeError("400 Client Error: Bad Request")
            return [{"id": "9", "title": "Risks"}]

        cfg = {"confluence": {"base_url": "https://example.test/wiki",
                              "email": "a", "api_token": "t"}}
        with patch("core.sources.fetch_confluence_results", fake):
            hits = sources.search_confluence_by_title(cfg, "APS", "Risks")
        self.assertEqual(hits[0]["id"], "9")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][1], "1970-01-01")
        self.assertNotIn("folder", calls[1][0])


if __name__ == "__main__":
    unittest.main()
