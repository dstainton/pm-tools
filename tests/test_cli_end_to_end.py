"""End-to-end runs of the real CLI against a stand-in Jira.

Every test here shells out to `pm` exactly as a user would, with a config that
points at the fake Jira from `tests.fake_jira`. That makes these the tests that
prove the whole chain: config -> membership resolution -> generated JQL ->
paged fetch -> report on disk.

The backlog below is shaped like the one the tool is built for: Epics carry the
Component, most children carry nothing, and a few children carry a Component of
their own.
"""

import datetime as dt
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.fake_jira import FakeJira


PM = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "pm.py")

NOW = dt.datetime.now(dt.timezone.utc)


def stamp(days_ago, hour=9):
    when = (NOW - dt.timedelta(days=days_ago)).replace(hour=hour, minute=12)
    return when.strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def date(days_from_now):
    return (NOW.date() + dt.timedelta(days=days_from_now)).isoformat()


AC = "Acceptance criteria: the endpoint returns the current status."


def backlog():
    return [
        # --- Epics: these carry the Component that names the workstream -----
        {"key": "APS-1", "project": "APS", "issuetype": "Epic",
         "summary": "Secure exchange platform", "components": ["Secure Data Exchange"],
         "status_name": "In Progress", "status_category": "In Progress",
         "updated": stamp(2), "sprint": None},
        {"key": "APS-2", "project": "APS", "issuetype": "Epic",
         "summary": "Public API foundations", "components": ["API Platform"],
         "status_name": "In Progress", "status_category": "In Progress",
         "updated": stamp(3), "sprint": None},
        {"key": "APS-3", "project": "APS", "issuetype": "Epic",
         "summary": "Housekeeping and compliance", "components": [],
         "status_name": "To Do", "status_category": "To Do",
         "updated": stamp(9), "sprint": None},

        # --- Children with no Component: membership is inherited ------------
        {"key": "APS-10", "project": "APS", "issuetype": "Story",
         "summary": "Publish exchange status endpoint", "components": [],
         "parent": "APS-1", "status_name": "In Review",
         "status_category": "In Progress", "sprint": "open",
         "assignee": "A. Lee", "story_points": 3, "description": AC,
         "updated": stamp(0), "changelog": [
             {"created": stamp(0), "author": {"displayName": "A. Lee"},
              "items": [{"field": "status", "fromString": "To Do",
                         "toString": "In Review"}]}]},
        {"key": "APS-11", "project": "APS", "issuetype": "Task",
         "summary": "Fix stuff", "components": [], "parent": "APS-1",
         "status_name": "In Progress", "status_category": "In Progress",
         "sprint": "open", "assignee": "B. Ray", "updated": stamp(1)},
        # A sub-task two levels below the Epic.
        {"key": "APS-12", "project": "APS", "issuetype": "Sub-task",
         "summary": "Wire retry handling into the client SDK", "components": [],
         "parent": "APS-10", "status_name": "To Do", "status_category": "To Do",
         "sprint": "open", "updated": stamp(1)},
        {"key": "APS-20", "project": "APS", "issuetype": "Story",
         "summary": "Rate limiting for public endpoints", "components": [],
         "parent": "APS-2", "status_name": "To Do", "status_category": "To Do",
         "sprint": "open", "updated": stamp(40), "changelog": [
             {"created": stamp(40), "author": {"displayName": "C. Diaz"},
              "items": [{"field": "status", "fromString": "Backlog",
                         "toString": "To Do"}]}]},

        # --- Children that carry a Component themselves ---------------------
        # Its Epic belongs to nobody, so only its own Component finds it.
        {"key": "APS-30", "project": "APS", "issuetype": "Story",
         "summary": "Rotate exchange signing certificates",
         "components": ["Secure Data Exchange"], "parent": "APS-3",
         "status_name": "To Do", "status_category": "To Do", "sprint": "open",
         "story_points": 5, "description": AC, "duedate": date(-4),
         "updated": stamp(1)},
        # Inherits from the tagged Story above, not from any Epic.
        {"key": "APS-31", "project": "APS", "issuetype": "Sub-task",
         "summary": "Document the certificate rotation runbook",
         "components": [], "parent": "APS-30", "status_name": "To Do",
         "status_category": "To Do", "sprint": "open", "updated": stamp(1)},
        # No parent at all, and no Epic carries the ITK Component.
        {"key": "APS-40", "project": "APS", "issuetype": "Story",
         "summary": "Publish the connector template gallery",
         "components": ["Integration Toolkit"], "status_name": "To Do",
         "status_category": "To Do", "sprint": "open", "story_points": 2,
         "description": AC, "updated": stamp(5)},
        # Sits under the SDX Epic but names API Platform itself.
        {"key": "APS-50", "project": "APS", "issuetype": "Story",
         "summary": "Expose exchange metrics on the API gateway",
         "components": ["API Platform"], "parent": "APS-1",
         "status_name": "To Do", "status_category": "To Do", "sprint": "open",
         "story_points": 3, "description": AC, "updated": stamp(2)},

        # --- Finished work, outside every open scope -------------------------
        {"key": "APS-60", "project": "APS", "issuetype": "Story",
         "summary": "Retire the legacy handshake", "components": [],
         "parent": "APS-2", "status_name": "Done", "status_category": "Done",
         "sprint": None, "story_points": 1, "description": AC,
         "updated": stamp(30)},
    ]


PROJECT_COMPONENTS = {"APS": ["Secure Data Exchange", "API Platform",
                              "Integration Toolkit", "Documentation"]}


def pages():
    return [
        {"id": "1001", "space": "SDX", "labels": ["decision"],
         "title": "Decision: certificate rotation cadence",
         "body": "Rotate every 90 days, automated from October.",
         "when": stamp(1)},
        {"id": "1002", "space": "SDX", "labels": ["risk"],
         "title": "Risk: HSM capacity during rotation",
         "body": "Capacity headroom is thin during the switchover window.",
         "when": stamp(2)},
        {"id": "2001", "space": "APS", "labels": ["decision"],
         "title": "Decision: rate limit defaults",
         "body": "1000 requests a minute per tenant.", "when": stamp(3)},
    ]

CONFIG = """\
# Test config for the end-to-end run. Comments here double as a check that
# `pm workstreams add` and `remove` leave them alone.
model:
  endpoint: "{url}/v1/chat/completions"
  name: "fake-local"
  temperature: 0.2
  max_tokens: 500
  timeout: 30

jira:
  base_url: "{url}"
  email: "pm@example.com"
  api_token: "token"
  project: "APS"
  fields: "summary,status,assignee,updated,duedate,priority,issuetype,labels"
  max_results: 500
  page_size: 2          # small on purpose: every fetch has to page
  story_points_field: "customfield_10016"
  start_date_field: "customfield_10015"
  acceptance_criteria_field: ""
  epic_link_field: "parent"

confluence:
  base_url: "{url}/wiki"
  email: "pm@example.com"
  api_token: "token"
  lookback_days: 7
  max_results: 10

sharepoint:
  enabled: false

lint:
  stale_days: 14
  required_fields: [epic]
  min_title_words: 3
  vague_title_terms: [fix, stuff, misc, tbd, wip]
  story_types: [story, bug]
  require_acceptance_criteria: true
  acceptance_criteria_markers: ["acceptance criteria", "given ", "when ", "then "]
  require_estimate: true

review:
  batch_size: 5

ready:
  blocking_criteria:
    - clear-title
    - has-acceptance-criteria
    - has-estimate
    - sane-dates

standup:
  lookback_days: 1

membership:
{membership}

# ----------------------------------------------------------------------------
#  Workstreams — the section `pm workstreams` edits
# ----------------------------------------------------------------------------
workstreams:

  - name: "Secure Data Exchange"
    abbrev: "SDX"
    components: [{sdx_component}]
    confluence_space: "SDX"
    confluence_labels: [decision, risk]

  - name: "API Platform"
    abbrev: "APS"
    components: ["API Platform"]

  - name: "Integration Toolkit"
    abbrev: "ITK"
    components: ["Integration Toolkit"]

# ----------------------------------------------------------------------------
#  Output
# ----------------------------------------------------------------------------
output:
  file: "weekly_report_{{date}}.md"
  audience: "directors"
  state_file: "report_state.json"
"""


class CliTestCase(unittest.TestCase):
    """Shared plumbing: one fake Jira for the class, a temp home per test."""

    @classmethod
    def setUpClass(cls):
        cls.jira = FakeJira(backlog(), PROJECT_COMPONENTS, pages())
        cls.jira.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.jira.__exit__(None, None, None)

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="pm-e2e-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.write_config("config.yaml")

    def write_config(self, name, membership="  inherit_from_parent: true",
                     sdx_component='"Secure Data Exchange"'):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(CONFIG.format(url=self.jira.url, membership=membership,
                                   sdx_component=sdx_component))
        return path

    def run_pm(self, *args, config="config.yaml", expect=0):
        proc = subprocess.run(
            [sys.executable, PM, *args, "--config",
             os.path.join(self.dir, config)],
            cwd=self.dir, capture_output=True, text=True, timeout=120)
        output = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, expect,
                         f"`pm {' '.join(args)}` exited "
                         f"{proc.returncode}:\n{output}")
        return output

    def read_output(self, pattern):
        matches = [f for f in os.listdir(self.dir) if re.match(pattern, f)]
        self.assertEqual(len(matches), 1,
                         f"expected one {pattern} file, found {matches}")
        with open(os.path.join(self.dir, matches[0]), "r",
                  encoding="utf-8") as fh:
            return fh.read()

    def keys_in_scope(self, abbrev, config="config.yaml"):
        """Every issue `pm ready` sees for one workstream."""
        self.run_pm("ready", "-w", abbrev, config=config)
        report = self.read_output(r"ready_report_.*\.md")
        os.remove(os.path.join(self.dir, [f for f in os.listdir(self.dir)
                                          if f.startswith("ready_report_")][0]))
        return set(re.findall(r"APS-\d+", report))


class MembershipScopeTests(CliTestCase):
    def test_inherited_and_directly_tagged_work_is_in_scope(self):
        self.assertEqual(
            self.keys_in_scope("SDX"),
            {
                "APS-10",   # no component, under the SDX epic
                "APS-11",   # ditto
                "APS-12",   # sub-task two levels under the SDX epic
                "APS-30",   # its own SDX component, under an untagged epic
                "APS-31",   # sub-task of that directly tagged story
                "APS-50",   # under the SDX epic, names API Platform itself
            })

    def test_a_workstream_with_no_tagged_epic_still_finds_its_work(self):
        # Nothing in the backlog is an ITK epic — only APS-40 carries the
        # component. Before component membership existed this came back empty.
        self.assertEqual(self.keys_in_scope("ITK"), {"APS-40"})

    def test_other_workstreams_do_not_leak_in(self):
        keys = self.keys_in_scope("APS")
        self.assertEqual(keys, {"APS-20", "APS-50"})
        self.assertNotIn("APS-60", keys)     # done, and out of the sprint

    def test_child_component_wins_reassigns_shared_work(self):
        self.write_config("strict.yaml",
                          membership="  child_component_wins: true")
        self.assertNotIn("APS-50", self.keys_in_scope("SDX", config="strict.yaml"))
        self.assertIn("APS-50", self.keys_in_scope("APS", config="strict.yaml"))


class WorkstreamsCommandTests(CliTestCase):
    def test_list_shows_every_workstream_and_its_components(self):
        out = self.run_pm("workstreams")
        for expected in ("SDX", "Secure Data Exchange", "API Platform",
                         "Integration Toolkit", "APS"):
            self.assertIn(expected, out)

    def test_check_resolves_membership_against_jira(self):
        out = self.run_pm("workstreams", "check", "--show-jql", "-w", "SDX")
        self.assertIn("connected to", out)
        self.assertIn("epics carrying the component: 1", out)
        self.assertIn("issues tagged directly: 1", out)
        self.assertIn("Setup looks good", out)
        # --show-jql exposes the generated query for a sceptical reader.
        self.assertIn('component IN ("Secure Data Exchange")', out)
        self.assertIn("parentEpic IN (APS-1)", out)

    def test_check_counts_issues_per_scope(self):
        out = self.run_pm("workstreams", "check", "-w", "ITK")
        self.assertIn("~1 issue(s)", out)

    def test_check_catches_a_mistyped_component(self):
        self.write_config("typo.yaml", sdx_component='"Secure Data Exchang"')
        out = self.run_pm("workstreams", "check", "-w", "SDX",
                          config="typo.yaml", expect=1)
        self.assertIn("does not exist in the project", out)
        self.assertIn("Did you mean: Secure Data Exchange", out)

    def test_add_then_remove_a_workstream_without_touching_comments(self):
        path = os.path.join(self.dir, "config.yaml")
        with open(path, encoding="utf-8") as fh:
            before = fh.read()

        out = self.run_pm("workstreams", "add", "--name", "Billing Platform",
                          "--abbrev", "BIL", "--components", "Billing Platform",
                          "--confluence-space", "BIL")
        self.assertIn("Added BIL", out)

        with open(path, encoding="utf-8") as fh:
            after = fh.read()
        self.assertIn("#  Workstreams — the section `pm workstreams` edits",
                      after)
        self.assertIn('audience: "directors"', after)
        self.assertIn("BIL", self.run_pm("workstreams"))

        self.run_pm("workstreams", "remove", "BIL")
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), before)

    def test_add_refuses_a_duplicate(self):
        out = self.run_pm("workstreams", "add", "--name", "Another",
                          "--abbrev", "SDX", "--components", "X", expect=1)
        self.assertIn("already exists", out)


class LintTests(CliTestCase):
    def _findings(self):
        self.run_pm("lint", "--json")
        import json
        with open(os.path.join(self.dir, [f for f in os.listdir(self.dir)
                                          if f.startswith("lint_report_")][0]),
                  encoding="utf-8") as fh:
            return json.load(fh)

    def test_findings_land_on_the_right_issues_and_workstreams(self):
        findings = self._findings()
        by_key = {}
        for f in findings:
            by_key.setdefault(f["key"], set()).add(f["rule"])

        self.assertIn("vague-title", by_key.get("APS-11", set()))
        self.assertIn("bad-dates", by_key.get("APS-30", set()))
        self.assertIn("no-estimate", by_key.get("APS-20", set()))
        self.assertIn("missing-acceptance-criteria", by_key.get("APS-20", set()))
        self.assertEqual(
            {f["workstream"] for f in findings if f["key"] == "APS-20"}, {"APS"})

    def test_inherited_components_are_never_nagged_about(self):
        rules = {f["rule"] for f in self._findings()}
        self.assertNotIn("missing-component", rules)

    def test_epics_are_linted_but_not_asked_for_a_parent(self):
        keys = {f["key"] for f in self._findings()}
        self.assertNotIn("APS-1", keys)
        missing_epic = {f["key"] for f in self._findings()
                        if f["rule"] == "missing-epic"}
        self.assertEqual(missing_epic, {"APS-40"})   # the only orphan


class StandupTests(CliTestCase):
    def test_movement_and_work_in_progress(self):
        self.run_pm("standup", "-w", "SDX")
        report = self.read_output(r"standup_.*\.md")
        self.assertIn("APS-10", report)
        self.assertIn("To Do → In Review", report)
        self.assertIn("A. Lee", report)
        self.assertIn("APS-11", report)              # in progress now
        self.assertNotIn("APS-20", report)           # moved 40 days ago

    def test_widening_the_window_picks_up_older_moves(self):
        self.run_pm("standup", "--days", "60", "-w", "APS")
        report = self.read_output(r"standup_.*\.md")
        self.assertIn("APS-20", report)
        self.assertIn("Backlog → To Do", report)


class ReportTests(CliTestCase):
    def test_weekly_report_is_written_with_real_links(self):
        out = self.run_pm("report", "-w", "SDX")
        self.assertIn("Done. Report written to", out)

        report = self.read_output(r"weekly_report_.*\.md")
        self.assertIn("Fake model reply for the end-to-end test", report)
        self.assertIn("## References", report)
        self.assertIn(f"{self.jira.url}/browse/APS-10", report)
        # The roadmap half of the gather is the workstream's epic.
        self.assertIn("APS-1:", report)
        self.assertTrue(os.path.exists(os.path.join(self.dir,
                                                    "report_state.json")))

    def test_confluence_decisions_are_gathered_from_space_and_labels(self):
        self.run_pm("report", "-w", "SDX")
        report = self.read_output(r"weekly_report_.*\.md")
        self.assertIn("Decision: certificate rotation cadence", report)
        self.assertIn("Risk: HSM capacity during rotation", report)
        # The other workstream's space stays out of it.
        self.assertNotIn("Decision: rate limit defaults", report)

    def test_second_run_reports_what_changed(self):
        self.run_pm("report", "-w", "SDX")
        out = self.run_pm("report", "-w", "SDX")
        self.assertIn("changes: 0 new", out)


class ReadyTests(CliTestCase):
    def test_gate_names_the_blocking_gaps(self):
        self.run_pm("ready", "-w", "SDX")
        report = self.read_output(r"ready_report_.*\.md")
        self.assertIn("🔴 Not ready", report)
        self.assertIn("APS-11", report)              # vague title
        self.assertIn("sane-dates", report)          # APS-30's past due date
        self.assertIn("🟢 Ready", report)
        self.assertIn("APS-10", report)


class ReviewTests(CliTestCase):
    def test_review_runs_against_the_local_model(self):
        out = self.run_pm("review", "titles", "-w", "SDX")
        self.assertIn("issues reviewed", out)
        report = self.read_output(r"review_titles_.*\.md")
        self.assertIn("Nothing flagged", report)     # the fake model returns []


if __name__ == "__main__":
    unittest.main()
