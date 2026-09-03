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
  temperature: 0.4
  json_temperature: 0.2
  top_p: 0.8
  top_k: 20
  presence_penalty: 1.5
  max_tokens: 500
  timeout: 30
  enable_thinking: false

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
  batch_size: 8

ready:
  blocking_criteria:
    - clear-title
    - has-acceptance-criteria
    - has-estimate
    - sane-dates

standup:
  lookback_days: 1

cache:
  enabled: true
  path: "cache"
  ttl_seconds: 300

today:
  state_file: "today.json"
  max_needs_you: 5
  max_moved: 8
  max_aging: 3
  untouched_days: 3

state:
  shared_path: "."
  local_path: "."

triage:
  unassigned_in_sprint: true
  blocked: true
  mentions_me_within_days: 3
  new_bugs_within_days: 1
  in_sprint_untouched_days: 3
  overdue: true

membership:
{membership}

# ----------------------------------------------------------------------------
#  Products — the section `pm products` edits
# ----------------------------------------------------------------------------
products:

  - name: "Integration Platform"
    abbrev: "IP"
    project: "APS"

# ----------------------------------------------------------------------------
#  Workstreams — the section `pm workstreams` edits
# ----------------------------------------------------------------------------
workstreams:

  - name: "Secure Data Exchange"
    abbrev: "SDX"
    product: "IP"
    components: [{sdx_component}]
    confluence_space: "SDX"
    confluence_labels: [decision, risk]

  - name: "API Platform"
    abbrev: "APS"
    product: "IP"
    components: ["API Platform"]

  - name: "Integration Toolkit"
    abbrev: "ITK"
    product: "IP"
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


class ProductTests(CliTestCase):
    def test_list_shows_the_product_and_its_workstreams(self):
        out = self.run_pm("products")
        self.assertIn("IP", out)
        self.assertIn("Integration Platform", out)
        self.assertIn("SDX", out)
        self.assertIn("APS", out)
        self.assertIn("ITK", out)

    def test_product_filter_keeps_only_that_product(self):
        out = self.run_pm("lint", "--json", "--product", "IP")
        self.assertIn("(scope: product IP)", out)
        import json
        with open(os.path.join(self.dir, [f for f in os.listdir(self.dir)
                                          if f.startswith("lint_report_")][0]),
                  encoding="utf-8") as fh:
            findings = json.load(fh)
        self.assertTrue(findings)
        self.assertTrue(all(f["workstream"] in {"SDX", "APS", "ITK"}
                            for f in findings))

    def test_unknown_product_fails_loudly(self):
        out = self.run_pm("lint", "--product", "NOPE", expect=1)
        self.assertIn("Unknown product", out)
        self.assertIn("IP", out)

    def test_product_and_workstream_compose(self):
        out = self.run_pm("ready", "--product", "IP", "-w", "ITK")
        self.assertIn("product IP", out)
        report = self.read_output(r"ready_report_.*\.md")
        self.assertIn("APS-40", report)
        self.assertNotIn("APS-10", report)

    def test_unassigned_workstream_is_isolated_by_product_filter(self):
        self.run_pm("workstreams", "add", "--name", "Orphan Docs",
                    "--abbrev", "DOC", "--components", "Documentation")
        out = self.run_pm("workstreams", "--product", "UNASSIGNED")
        self.assertIn("DOC", out)
        self.assertNotIn("SDX", out.split("Abbrev", 1)[-1]
                         if "Abbrev" in out else out)

        isolated = self.run_pm("ready", "--product", "UNASSIGNED")
        self.assertIn("DOC", isolated)
        report = self.read_output(r"ready_report_.*\.md")
        self.assertNotIn("APS-10", report)

    def test_add_then_remove_a_product_without_touching_comments(self):
        path = os.path.join(self.dir, "config.yaml")
        with open(path, encoding="utf-8") as fh:
            before = fh.read()
        out = self.run_pm("products", "add", "--name", "Billing Platform",
                          "--abbrev", "BILL", "--project", "BILL")
        self.assertIn("Added BILL", out)
        with open(path, encoding="utf-8") as fh:
            after = fh.read()
        self.assertIn("#  Products — the section `pm products` edits", after)
        self.assertIn("BILL", self.run_pm("products"))
        self.run_pm("products", "remove", "BILL")
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), before)

    def test_cannot_remove_a_product_workstreams_still_name(self):
        out = self.run_pm("products", "remove", "IP", expect=1)
        self.assertIn("still name it", out)

    def test_workstreams_add_tags_a_product(self):
        self.run_pm("products", "add", "--name", "Billing Platform",
                    "--abbrev", "BILL", "--project", "BILL")
        self.run_pm("workstreams", "add", "--name", "Invoicing",
                    "--abbrev", "INV", "--components", "Billing Platform",
                    "--product", "BILL")
        listed = self.run_pm("workstreams", "--product", "BILL")
        self.assertIn("INV", listed)
        self.assertNotIn("SDX", listed)

    def test_weekly_report_has_a_portfolio_section(self):
        self.run_pm("report", "--product", "IP")
        report = self.read_output(r"weekly_report_.*\.md")
        self.assertIn("## Portfolio", report)
        self.assertIn("Integration Platform (IP)", report)


class DoctorTests(CliTestCase):
    def test_doctor_reports_each_check(self):
        out = self.run_pm("doctor")
        for label in ("config", "jira", "projects", "custom fields",
                      "membership", "model", "cache"):
            self.assertIn(label, out)
        self.assertIn("Setup looks good", out)
        self.assertIn("Test PM", out)
        self.assertIn("unclaimed", out)

    def test_discover_fields_prints_a_snippet(self):
        out = self.run_pm("doctor", "--discover-fields")
        self.assertIn("customfield_10016", out)
        self.assertIn("Story Points", out)
        self.assertIn("Suggested snippet", out)


class CacheTests(CliTestCase):
    def test_second_lint_reuses_the_cache(self):
        self.run_pm("lint", "--json", "-w", "ITK")
        searches = [c for c in self.jira.calls
                    if c[0] == "POST" and "search/jql" in c[1]]
        first = len(searches)
        self.assertGreater(first, 0)
        self.run_pm("lint", "--json", "-w", "ITK")
        searches = [c for c in self.jira.calls
                    if c[0] == "POST" and "search/jql" in c[1]]
        self.assertEqual(len(searches), first)

    def test_refresh_hits_jira_again(self):
        self.run_pm("lint", "--json", "-w", "ITK")
        searches = [c for c in self.jira.calls
                    if c[0] == "POST" and "search/jql" in c[1]]
        first = len(searches)
        self.run_pm("lint", "--json", "-w", "ITK", "--refresh")
        searches = [c for c in self.jira.calls
                    if c[0] == "POST" and "search/jql" in c[1]]
        self.assertGreater(len(searches), first)


class TodayTests(CliTestCase):
    def test_today_numbers_actions_and_do_previews(self):
        out = self.run_pm("today")
        self.assertIn("NEEDS YOU", out)
        self.assertIn("MOVED SINCE YESTERDAY", out)
        self.assertIn("AGING", out)
        self.assertIn("REFINEMENT GAPS", out)
        self.assertIn("SPRINT GOAL", out)
        self.assertIn("Ship certificate rotation", out)
        self.assertIn("APS-30", out)                 # overdue
        self.assertIn("pm do", out)
        self.assertTrue(os.path.exists(os.path.join(self.dir, "today.json")))

        before = len([c for c in self.jira.calls if c[0] == "PUT"])
        preview = self.run_pm("do", "1", "--dry-run")
        self.assertIn("Would PUT", preview)
        self.assertIn("--dry-run: nothing was sent.", preview)
        self.assertIn("/rest/api/3/issue/", preview)
        puts = [c for c in self.jira.calls if c[0] == "PUT"]
        self.assertEqual(len(puts), before)

    def test_do_without_confirm_refuses_to_write(self):
        self.run_pm("today")
        out = self.run_pm("do", "1", expect=1)
        self.assertIn("Refusing to write", out)

    def test_do_without_today_explains_itself(self):
        out = self.run_pm("do", "1", expect=1)
        self.assertIn("pm today", out)

    def test_today_respects_product_filter(self):
        out = self.run_pm("today", "--product", "IP", "-w", "SDX")
        self.assertIn("APS-30", out)
        self.assertNotIn("APS-20", out)              # APS workstream


class TodayWriteTests(CliTestCase):
    def test_do_yes_writes_the_due_date(self):
        self.run_pm("today")
        out = self.run_pm("do", "1", "--yes")
        self.assertIn("Sent.", out)
        puts = [c for c in self.jira.calls if c[0] == "PUT"]
        self.assertTrue(puts)
        self.assertIn("duedate", (puts[-1][2].get("fields") or {}))
        log = os.path.join(self.dir, "write-log.jsonl")
        self.assertTrue(os.path.exists(log))
        with open(log, encoding="utf-8") as fh:
            self.assertIn("APS-30", fh.read())


class LintDecisionTests(CliTestCase):
    def _findings(self, *extra):
        self.run_pm("lint", "--json", *extra)
        import json
        files = [f for f in os.listdir(self.dir)
                 if f.startswith("lint_report_") and f.endswith(".json")]
        with open(os.path.join(self.dir, files[0]), encoding="utf-8") as fh:
            return json.load(fh)

    def test_snooze_hides_a_finding_until_all(self):
        before = {f["key"] for f in self._findings() if f["rule"] == "vague-title"}
        self.assertIn("APS-11", before)
        out = self.run_pm("lint", "--snooze", "APS-11", "--until", "14d",
                          "--why", "cosmetic, agreed with A. Lee")
        self.assertIn("Remembered: snooze APS-11", out)
        self.assertIn("hidden", out)
        after = {f["key"] for f in self._findings()}
        self.assertNotIn("APS-11", after)
        shown = {f["key"] for f in self._findings("--all")}
        self.assertIn("APS-11", shown)

    def test_assign_hides_and_writes_assignee(self):
        out = self.run_pm("lint", "--assign", "APS-20", "--to", "dana",
                          "--why", "Dana will refine the AC", "--yes")
        self.assertIn("Remembered: assign APS-20", out)
        self.assertIn("Sent.", out)
        puts = [c for c in self.jira.calls if c[0] == "PUT"
                and "APS-20" in c[1]]
        self.assertTrue(puts)
        self.assertEqual(
            (puts[-1][2].get("fields") or {}).get("assignee"),
            {"accountId": "dana"})
        keys = {f["key"] for f in self._findings()}
        self.assertNotIn("APS-20", keys)


class TriageTests(CliTestCase):
    def test_triage_lists_and_apply_dry_run_sends_nothing(self):
        out = self.run_pm("triage")
        self.assertIn("TRIAGE", out)
        self.assertIn("APS-30", out)
        self.assertIn("pm triage --apply", out)
        self.assertTrue(os.path.exists(os.path.join(self.dir, "triage.json")))
        before = len([c for c in self.jira.calls if c[0] == "PUT"])
        preview = self.run_pm("triage", "--apply", "1", "--dry-run")
        self.assertIn("Would PUT", preview)
        self.assertIn("nothing was sent", preview)
        puts = [c for c in self.jira.calls if c[0] == "PUT"]
        self.assertEqual(len(puts), before)

    def test_triage_apply_yes_writes(self):
        self.run_pm("triage")
        out = self.run_pm("triage", "--apply", "1", "--yes")
        self.assertIn("Sent.", out)
        puts = [c for c in self.jira.calls if c[0] == "PUT"]
        self.assertTrue(puts)


class RefineTests(CliTestCase):
    def test_refine_writes_a_worksheet_with_drafts(self):
        out = self.run_pm("refine", "-w", "SDX")
        self.assertIn("Drafts in refine_SDX_", out)
        text = self.read_output(r"refine_SDX_.*\.md")
        self.assertIn("## APS-11", text)
        self.assertIn("title: Fix retry handling in the exchange client", text)

    def test_refine_apply_writes_kept_fields(self):
        self.run_pm("refine", "-w", "SDX")
        out = self.run_pm("refine", "--apply", "-w", "SDX", "--yes")
        self.assertIn("Sent.", out)
        puts = [c for c in self.jira.calls if c[0] == "PUT"
                and "APS-11" in c[1]]
        self.assertTrue(puts)
        self.assertEqual(
            (puts[-1][2].get("fields") or {}).get("summary"),
            "Fix retry handling in the exchange client")

    def test_review_alias_prints_a_deprecation_note(self):
        out = self.run_pm("review", "titles", "-w", "SDX")
        self.assertIn("deprecated alias", out)


class InboxTests(CliTestCase):
    def test_note_then_inbox_create(self):
        out = self.run_pm("note", "customer wants an SSO audit export")
        self.assertIn("Captured #1", out)
        listed = self.run_pm("inbox")
        self.assertIn("#1", listed)
        self.assertIn("Export the SSO audit log", listed)
        created = self.run_pm("inbox", "create", "1", "--yes")
        self.assertIn("Created APS-", created)
        posts = [c for c in self.jira.calls if c[0] == "POST"
                 and c[1].rstrip("/") == "/rest/api/3/issue"]
        self.assertTrue(posts)
        empty = self.run_pm("inbox")
        self.assertIn("Inbox is empty", empty)

    def test_inbox_drop(self):
        self.run_pm("note", "scratch this later")
        out = self.run_pm("inbox", "drop", "1")
        self.assertIn("Dropped #1", out)
        self.assertIn("Inbox is empty", self.run_pm("inbox"))

    def test_inbox_create_dry_run_sends_nothing(self):
        self.run_pm("note", "do not create this")
        before = [c for c in self.jira.calls if c[0] == "POST"
                  and c[1].rstrip("/") == "/rest/api/3/issue"]
        out = self.run_pm("inbox", "create", "1", "--dry-run")
        self.assertIn("nothing was sent", out)
        posts = [c for c in self.jira.calls if c[0] == "POST"
                 and c[1].rstrip("/") == "/rest/api/3/issue"]
        self.assertEqual(len(posts), len(before))


class ProductCheckTests(CliTestCase):
    def test_products_check_uses_the_team_project(self):
        out = self.run_pm("products", "check")
        self.assertIn("Team project: APS", out)
        self.assertIn("components name products and workstreams", out)
        self.assertIn("Setup looks good", out)


if __name__ == "__main__":
    unittest.main()
