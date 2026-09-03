import unittest

from core import filters


class CompileScopeTests(unittest.TestCase):
    def test_empty_scope_filters_nothing(self):
        self.assertEqual(filters.compile_scope({}), "")
        self.assertEqual(filters.compile_scope(None), "")

    def test_status_and_sprint_are_translated(self):
        jql = filters.compile_scope({"status": "open", "sprint": "open"})
        self.assertIn("statusCategory != Done", jql)
        self.assertIn("sprint in openSprints()", jql)
        self.assertIn(" AND ", jql)

    def test_any_means_no_clause(self):
        self.assertEqual(filters.compile_scope({"status": "any"}), "")

    def test_lists_accept_yaml_lists_and_strings(self):
        self.assertEqual(filters.compile_scope({"types": ["Story", "Bug"]}),
                         'issuetype IN ("Story", "Bug")')
        self.assertEqual(filters.compile_scope({"types": "Story, Bug"}),
                         'issuetype IN ("Story", "Bug")')

    def test_labels_none_keeps_unlabelled_issues(self):
        jql = filters.compile_scope({"labels_none": ["wontfix"]})
        self.assertEqual(jql,
                         '(labels IS EMPTY OR labels NOT IN ("wontfix"))')

    def test_day_windows(self):
        self.assertEqual(filters.compile_scope({"updated_within_days": 3}),
                         "updated >= -3d")
        self.assertEqual(filters.compile_scope({"created_within_days": "7"}),
                         "created >= -7d")

    def test_extra_jql_is_passed_through(self):
        self.assertEqual(filters.compile_scope({"extra_jql": "fixVersion = 2.1"}),
                         "fixVersion = 2.1")

    def test_quotes_in_names_are_escaped(self):
        self.assertEqual(filters.compile_scope({"types": ['Sub "task"']}),
                         'issuetype IN ("Sub \\"task\\"")')

    def test_unknown_option_fails_loudly(self):
        with self.assertRaises(SystemExit) as caught:
            filters.compile_scope({"stattus": "open"})
        self.assertIn("unknown scope option", str(caught.exception))

    def test_unknown_value_lists_the_valid_ones(self):
        with self.assertRaises(SystemExit) as caught:
            filters.compile_scope({"status": "finished"})
        self.assertIn("in-progress", str(caught.exception))

    def test_negative_day_window_is_rejected(self):
        with self.assertRaises(SystemExit):
            filters.compile_scope({"updated_within_days": -2})


class ScopeOptionTests(unittest.TestCase):
    def test_defaults_apply_when_nothing_is_configured(self):
        options = filters.scope_options({}, {}, "standup_wip")
        self.assertEqual(options, {"status": "in-progress"})

    def test_layers_override_in_order(self):
        cfg = {"scopes": {"lint": {"status": "any"}}}
        ws = {"scopes": {"lint": {"status": "done", "types": ["Story"]}}}
        options = filters.scope_options(cfg, ws, "lint")
        self.assertEqual(options, {"status": "done", "types": ["Story"]})

        options = filters.scope_options(cfg, ws, "lint",
                                        overrides={"status": "open"})
        self.assertEqual(options["status"], "open")

    def test_unknown_scope_name_fails(self):
        with self.assertRaises(SystemExit):
            filters.scope_options({}, {}, "sprintreview")


class ValidateTests(unittest.TestCase):
    def test_bad_scope_in_workstream_is_caught_at_load(self):
        cfg = {"workstreams": [{"abbrev": "SDX",
                                "scopes": {"lint": {"status": "nope"}}}]}
        with self.assertRaises(SystemExit):
            filters.validate_config_scopes(cfg)

    def test_valid_config_passes(self):
        cfg = {"scopes": {"report": {"sprint": "open"}},
               "workstreams": [{"abbrev": "SDX",
                                "scopes": {"lint": {"status": "any"}}}]}
        filters.validate_config_scopes(cfg)


class ConfluenceCqlTests(unittest.TestCase):
    def test_space_and_labels_are_combined(self):
        cql = filters.build_cql({"confluence_space": "SDX",
                                 "confluence_labels": ["decision", "risk"]})
        self.assertEqual(cql,
                         'space = "SDX" AND label IN ("decision", "risk")')

    def test_space_only(self):
        self.assertEqual(filters.build_cql({"confluence_space": "SDX"}),
                         'space = "SDX"')

    def test_hand_written_cql_still_wins(self):
        self.assertEqual(
            filters.build_cql({"confluence_space": "SDX",
                               "confluence_cql": "space = OLD"}),
            "space = OLD")

    def test_nothing_configured(self):
        self.assertIsNone(filters.build_cql({}))


if __name__ == "__main__":
    unittest.main()
