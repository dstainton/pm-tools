"""Several teams in one Confluence space, each under its own team page."""

import datetime as dt
import io
import unittest
from argparse import Namespace
from contextlib import redirect_stdout

from commands import doctor, report as report_cmd, setup
from core import config, confluence_tree, filters, pages, registers, report_render
from tests.fake_jira import FakeJira


def _when(days_ago):
    moment = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.000+0000")


OLD = "2020-01-01T00:00:00.000+0000"
APS = ("100", "API Program Services (APS) Team")
DES = ("900", "Data Equity Services (TM_DES)")
SDX = ("120", "Secure Data Exchange (SDX)")
CORE = ("123", "Core services (CORE)")


def _page(page_id, title, parents, kind="page", when=None):
    return {"id": page_id, "space": "POSM", "title": title, "type": kind,
            "when": when or _when(0),
            "ancestors": [{"id": pid, "title": name} for pid, name in parents]}


PM = ("160", "APS PM Artifacts")
LIFE = ("170", "Life Events")
CST = ("20", "Connected Services Teams")


def _space():
    return [
        _page("20", CST[1], [], "folder", OLD),
        _page("21", "Decision log", [CST], when=OLD),
        _page("30", "DSS Teams and the Matrix", []),
        _page("31", "BCDS Pulse Checks", []),
        _page("100", APS[1], [], when=OLD),
        _page("160", PM[1], [APS], "folder", OLD),
        _page("161", "PM checklist", [APS, PM]),
        _page("110", "APS API Portal", [APS], "folder", OLD),
        _page("130", "Integration Toolkit (ITK)", [APS], "folder", OLD),
        _page("120", SDX[1], [APS], "folder", OLD),
        _page("180", "Other APS Artifacts", [APS], "folder", OLD),
        _page("190", "SM WIP", [APS], "folder", OLD),
        _page("191", "SM draft", [APS, ("190", "SM WIP")]),
        _page("140", "Master To-Do List", [APS]),
        _page("141", "Vacation Support - Drew - 2025-12-19", [APS]),
        _page("170", LIFE[1], [APS], "folder", OLD),
        _page("171", "Life event note", [APS, LIFE]),
        _page("142", "Wildcard SSL renewal: production downtime", [APS]),
        _page("143", "APS F27Q2 Branch Update", [APS]),
        _page("150", "Risks", [APS], when=OLD),
        _page("121", "SDX design notes", [APS, SDX]),
        _page("122", "Risks", [APS, SDX], when=OLD),
        _page("123", CORE[1], [APS, SDX], "folder", OLD),
        _page("124", "Core runbook", [APS, SDX, CORE]),
        _page("111", "Portal launch plan", [APS, ("110", "APS API Portal")]),
        _page("900", DES[1], [], when=OLD),
        _page("901", "DES plan", [DES]),
        _page("902", "Risks", [DES], when=OLD),
        _page("910", "Integration Toolkit (ITK)", [DES], "folder", OLD),
        _page("911", "DES toolkit notes", [DES, ("910", "Integration Toolkit (ITK)")]),
    ]


def _spaces():
    rows = [{"key": f"S{n}", "name": f"Space {n}"} for n in range(130)]
    rows.append({"key": "POSM", "name": "POSM Chapter"})
    return rows


TEAM_LEVEL = [
    "PM checklist", "SM draft", "Master To-Do List",
    "Vacation Support - Drew - 2025-12-19", "Life event note",
    "Wildcard SSL renewal: production downtime", "APS F27Q2 Branch Update",
]


class TeamPageTests(unittest.TestCase):
    def setUp(self):
        self.jira = FakeJira([], pages=_space(), spaces=_spaces())
        self.jira.__enter__()
        self.addCleanup(lambda: self.jira.__exit__(None, None, None))
        self.cfg = {
            "jira": {"base_url": self.jira.url, "email": "a", "api_token": "t",
                     "project": "APS"},
            "confluence": {
                "base_url": self.jira.url + "/wiki", "email": "a", "api_token": "t",
                "max_results": 50, "space": "POSM Chapter",
                "team_page": "API Program Services (APS) Team",
            },
            "pages": {"summaries": False, "follow_jira_links": False,
                      "match_epics_with_model": False},
            "products": [
                {"abbrev": "PORTAL", "name": "API Portal"},
                {"abbrev": "SDX", "name": "Secure Data Exchange"},
                {"abbrev": "ITK", "name": "Integration Toolkit"},
            ],
            "workstreams": [
                {"abbrev": "CORE", "name": "Core services", "product": "SDX"},
                {"abbrev": "EDGE", "name": "Edge gateway", "product": "SDX"},
                {"abbrev": "TKR", "name": "Toolkit releases", "product": "ITK"},
            ],
        }
        self.window = {"start": dt.date.today() - dt.timedelta(days=7)}

    def _quiet(self, fn, *args, **kwargs):
        with redirect_stdout(io.StringIO()):
            return fn(*args, **kwargs)

    def test_a_space_name_is_turned_into_its_key(self):
        self.assertEqual(confluence_tree.team_space(self.cfg), "POSM")
        self.assertEqual(confluence_tree.team_root_id(self.cfg), "100")

    def test_product_folders_are_matched_under_our_team_page_only(self):
        found = {p["abbrev"]: confluence_tree.locate_product(self.cfg, p)
                 for p in self.cfg["products"]}
        self.assertEqual(found["PORTAL"]["ancestor_id"], "110")
        self.assertEqual(found["SDX"]["ancestor_id"], "120")
        self.assertEqual(found["ITK"]["ancestor_id"], "130")
        self.assertEqual(found["SDX"]["how"], "matched")

    def test_a_workstream_folder_is_matched_inside_its_product(self):
        cql = filters.build_cql(self.cfg["workstreams"][0], self.cfg, scope="space")
        self.assertIn('space = "POSM"', cql)
        self.assertIn("ancestor = 123", cql)
        self.assertIsNone(filters.build_cql(self.cfg["workstreams"][1], self.cfg))

    def test_matching_can_be_turned_off(self):
        self.cfg["products"][1]["confluence_page"] = False
        self.assertEqual(confluence_tree.locate_product(self.cfg, self.cfg["products"][1])
                         ["ancestor_id"], "")

    def test_a_space_on_its_own_still_reads_the_whole_space(self):
        ws = {"abbrev": "OLD", "name": "Old", "confluence_space": "POSM"}
        self.assertEqual(filters.build_cql(ws, self.cfg, scope="space"), 'space = "POSM"')

    def test_ties_and_weak_titles_are_not_guessed(self):
        entry = {"name": "Secure Data Exchange", "abbrev": "SDX"}
        self.assertEqual(confluence_tree.match_rank("Secure Data Exchange", entry), 5)
        self.assertEqual(confluence_tree.match_rank("Secure Data Exchange (SDX)", entry), 4)
        self.assertEqual(confluence_tree.match_rank("SDX", entry), 3)
        self.assertEqual(confluence_tree.match_rank("SDX notes", entry), 2)
        self.assertEqual(confluence_tree.match_rank("sdxtra", entry), 0)
        rows = [{"id": "1", "title": "SDX one"}, {"id": "2", "title": "SDX two"}]
        self.assertIsNone(confluence_tree.best_match(rows, entry))
        rows.append({"id": "3", "title": "Secure Data Exchange"})
        self.assertEqual(confluence_tree.best_match(rows, entry)["id"], "3")

    def _prepared(self):
        prepared = []
        for ws in self.cfg["workstreams"]:
            got = pages.gather(self.cfg, ws, window=self.window)
            prepared.append((ws, {"items": list(got), "epics": [], "changed": []}))
        return prepared

    def test_team_product_and_workstream_pages_each_land_once(self):
        prepared = self._quiet(self._prepared)
        team = report_cmd.team_pages(self.cfg, prepared, self.window, set())
        groups = [(p, [ws for ws, _r in prepared if ws["product"] == p["abbrev"]])
                  for p in self.cfg["products"]]
        report_cmd._attach_product_pages(self.cfg, groups, prepared, self.window, set())
        self.assertEqual(sorted(page["title"] for page in team), sorted(TEAM_LEVEL))
        by = {ws["abbrev"]: row for ws, row in prepared}
        core = [item["title"] for item in by["CORE"]["items"]]
        self.assertEqual(core.count("Core runbook"), 1)
        self.assertIn("SDX design notes", core)
        sdx_product = [item["title"] for item in by["CORE"]["items"] if item.get("product_only")]
        self.assertEqual(sdx_product, ["SDX design notes"])
        every = [item["title"] for _ws, row in prepared for item in row["items"]]
        for title in ("DES plan", "DES toolkit notes", "Portal launch plan",
                      "Master To-Do List", "DSS Teams and the Matrix"):
            self.assertNotIn(title, every)

        sections = [(ws, "Body.") for ws, _r in prepared]
        text = report_render.render_pm(
            self.cfg, [g for g in groups if g[1]], prepared, sections, self.window, "",
            team_pages=team)
        self.assertEqual(text.count("Master To-Do List"), 1)
        self.assertEqual(text.count("SDX design notes"), 1)
        glance = text.index("## At a glance")
        product = text.index("## Secure Data Exchange (SDX)")
        workstream = text.index("### Core services (CORE)")
        self.assertLess(glance, text.index("Master To-Do List"))
        self.assertLess(text.index("Master To-Do List"), product)
        self.assertLess(product, text.index("SDX design notes"))
        self.assertLess(text.index("SDX design notes"), workstream)
        self.assertLess(workstream, text.index("Core runbook"))

    def test_skipped_folders_and_pages_are_never_read(self):
        self.cfg["confluence"]["skip"] = [
            "Life Events", "SM WIP", "Vacation Support - Drew - 2025-12-19"]
        prepared = self._quiet(self._prepared)
        team = report_cmd.team_pages(self.cfg, prepared, self.window, set())
        titles = sorted(page["title"] for page in team)
        self.assertEqual(titles, sorted(set(TEAM_LEVEL) - {
            "Life event note", "SM draft", "Vacation Support - Drew - 2025-12-19"}))

    def test_a_short_name_used_by_several_folders_is_not_guessed(self):
        aps = {"abbrev": "APS", "name": "API Platform"}
        sm = {"abbrev": "SM", "name": "Service management"}
        self.cfg["workstreams"] += [aps, sm]
        self.assertEqual(confluence_tree.locate_workstream(self.cfg, aps)["ancestor_id"], "")
        self.assertEqual(confluence_tree.locate_workstream(self.cfg, sm)["ancestor_id"], "190")
        self.cfg["confluence"]["skip"] = ["SM WIP"]
        self.cfg.pop("_confluence_located")
        self.cfg.pop("_confluence_children")
        self.assertEqual(confluence_tree.locate_workstream(self.cfg, sm)["ancestor_id"], "")

    def test_under_may_name_a_page_outside_the_team_page(self):
        missing = self._quiet(registers.resolve_root, self.cfg, {
            "type": "decision", "name": "Decisions", "title": "Decision log"})
        self.assertIsNone(missing)
        found = self._quiet(registers.resolve_root, self.cfg, {
            "type": "decision", "name": "Decisions", "title": "Decision log",
            "under": "Connected Services Teams"})
        self.assertEqual(found["page_id"], "21")

    def test_a_register_title_is_found_in_its_own_folder_first(self):
        product = self._quiet(registers.resolve_root, self.cfg, {
            "type": "risk", "name": "SDX risks", "title": "Risks", "product": "SDX"})
        team = self._quiet(registers.resolve_root, self.cfg, {
            "type": "risk", "name": "Team risks", "title": "Risks"})
        self.assertEqual(product["page_id"], "122")
        self.assertEqual(team["page_id"], "150")

    def test_doctor_names_the_team_page_and_how_folders_were_found(self):
        self.cfg["workstreams"].append(
            {"abbrev": "WIDE", "name": "Wide", "confluence_space": "POSM"})
        buf = io.StringIO()
        with redirect_stdout(buf):
            doctor._check_confluence(self.cfg)
        shown = buf.getvalue()
        self.assertIn('space "POSM Chapter" is POSM', shown)
        self.assertIn('team page "API Program Services (APS) Team"', shown)
        self.assertIn('product SDX folder "Secure Data Exchange (SDX)" (matched by name)', shown)
        self.assertIn('CORE folder "Core services (CORE)" (matched by name)', shown)
        self.assertIn("EDGE: no folder under the team page is named for it, so its pages "
                      "are listed under product SDX", shown)
        self.assertIn("WIDE reads all of POSM, including other teams", shown)


class TeamPageConfigTests(unittest.TestCase):
    def test_team_page_and_a_false_page_are_accepted(self):
        config._validate_confluence_tree({"confluence": {
            "space": "POSM Chapter", "team_page": "APS Team", "team_page_id": "100"}})
        config._validate_confluence_ref("Product SDX", {"confluence_page": False})
        config._validate_confluence_tree({"confluence": {"skip": ["Life Events", 170]}})
        with self.assertRaises(SystemExit):
            config._validate_confluence_tree({"confluence": {"skip": "Life Events"}})
        with self.assertRaises(SystemExit):
            config._validate_confluence_ref("Product SDX", {"confluence_page": 5})
        with self.assertRaises(SystemExit):
            config._validate_confluence_tree({"confluence": {"team_page_id": "abc"}})

    def test_setup_writes_team_page_and_keeps_an_older_root_title(self):
        text = ('jira:\n  base_url: "https://example.atlassian.net"\n'
                'confluence:\n  space: ""\n')
        args = Namespace(site=None, email=None, token=None, token_env=None,
                         confluence_space="POSM Chapter",
                         confluence_team_page="API Program Services (APS) Team")
        out, notes = setup.apply_confluence_settings(text, args)
        self.assertIn('space: "POSM Chapter"', out)
        self.assertIn('team_page: "API Program Services (APS) Team"', out)
        older = text.replace('  space: ""\n', '  space: ""\n  root_title: "APS"\n')
        out, notes = setup.apply_confluence_settings(older, args)
        self.assertNotIn("team_page:", out)
        self.assertIn("confluence.team_page kept (root_title is set)", notes)


if __name__ == "__main__":
    unittest.main()
