"""Tranche 3: status categories, blocked names, honest lint, model cache."""

import datetime as dt
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from commands import lint, schedule, triage, today
from core import blocked, metrics, migrations, model, model_cache, statuses


def _when(days_ago, today=None):
    today = today or dt.date(2026, 9, 3)
    return dt.datetime.combine(today - dt.timedelta(days=days_ago),
                               dt.time(9, 0), tzinfo=dt.timezone.utc)


class CategoryTests(unittest.TestCase):
    def test_complete_and_shipped_are_done_when_jira_says_so(self):
        issue = {
            "key": "A",
            "status": "Complete",
            "status_category": "done",
            "issuetype": "Story",
            "updated": "2026-09-01T09:00:00.000+0000",
            "transitions": [
                {"field": "status", "from": "To Do", "to": "Building",
                 "to_category": "indeterminate", "when": _when(10)},
                {"field": "status", "from": "Building", "to": "Complete",
                 "to_category": "done", "when": _when(4)},
            ],
        }
        self.assertEqual(metrics.cycle_days(issue), 6)
        self.assertEqual(metrics.done_on(issue), dt.date(2026, 8, 30))

    def test_english_names_still_work_without_a_category(self):
        issue = {
            "key": "B",
            "status": "Done",
            "status_category": "done",
            "transitions": [
                {"field": "status", "to": "In Progress", "when": _when(8)},
                {"field": "status", "to": "Done", "when": _when(3)},
            ],
        }
        self.assertEqual(metrics.cycle_days(issue), 5)

    def test_annotate_stamps_category_from_the_status_id(self):
        index = statuses.index_statuses([
            {"id": "9", "name": "Complete", "category": "done"},
            {"id": "3", "name": "Building", "category": "indeterminate"},
        ])
        issue = {"status": "", "status_category": "", "transitions": [
            {"field": "status", "to": "Complete", "to_id": "9"},
        ]}
        statuses.annotate([issue], index)
        self.assertEqual(issue["transitions"][0]["to_category"], "done")
        self.assertEqual(metrics.transition_category(issue["transitions"][0]), "done")


class SprintIdTests(unittest.TestCase):
    def test_sprint_42_does_not_match_sprint_421(self):
        sprint = {"name": "Sprint 42", "start": "2026-08-27"}
        issues = [{
            "key": "Z",
            "transitions": [{
                "field": "sprint",
                "from": "",
                "to": "Sprint 421",
                "when": _when(2),
            }],
        }]
        change = metrics.sprint_scope_change(issues, sprint)
        self.assertEqual(change["added"], 0)

    def test_sprint_id_matches_exactly(self):
        sprint = {"id": 42, "name": "Sprint 42", "start": "2026-08-27"}
        issues = [
            {"key": "KEEP", "transitions": [{
                "field": "sprint", "from": "", "to": "Sprint 421",
                "from_id": "", "to_id": "421", "when": _when(2)}]},
            {"key": "ADD", "transitions": [{
                "field": "sprint", "from": "", "to": "Sprint 42",
                "from_id": "", "to_id": "42", "when": _when(1)}]},
        ]
        change = metrics.sprint_scope_change(issues, sprint)
        self.assertEqual(change["keys"], ["ADD"])


class BlockedTests(unittest.TestCase):
    def _issue(self, **overrides):
        issue = {
            "key": "APS-1", "status": "To Do", "status_category": "new",
            "issuetype": "Story", "assignee": "A. Lee", "labels": [],
            "due_date": None, "updated": "2026-09-01T09:00:00.000+0000",
        }
        issue.update(overrides)
        return issue

    def test_unblocked_is_not_blocked(self):
        issue = self._issue(status="Unblocked")
        self.assertFalse(blocked.is_blocked(issue, {}))
        self.assertNotEqual(today.classify_need(issue, 3), "blocked")

    def test_configured_status_counts(self):
        cfg = {"blocked": {"statuses": ["Impediment"], "labels": []}}
        issue = self._issue(status="Impediment")
        self.assertEqual(today.classify_need(issue, 3, cfg=cfg), "blocked")

    def test_default_label_still_counts(self):
        issue = self._issue(labels=["blocked"])
        self.assertEqual(today.classify_need(issue, 3), "blocked")


class MentionAndLinkTests(unittest.TestCase):
    def test_sam_does_not_match_sample(self):
        self.assertFalse(triage._name_mentioned("see the sample", "Sam"))
        self.assertTrue(triage._name_mentioned("ask Sam tomorrow", "Sam"))

    def test_mention_node_matches_account_id(self):
        comment = {"body": {"type": "doc", "content": [
            {"type": "mention", "attrs": {"id": "abc-1"}},
        ]}}
        self.assertEqual(triage._mention_ids(comment), ["abc-1"])

    def test_blocks_is_not_blocked_by(self):
        self.assertFalse(triage._is_blocked_by(
            {"relation": "blocks", "direction": "outward"}))
        self.assertTrue(triage._is_blocked_by(
            {"relation": "is blocked by", "direction": "inward"}))


class LintJudgementTests(unittest.TestCase):
    def _issue(self, **overrides):
        issue = {
            "key": "APS-1", "url": "http://example/APS-1",
            "summary": "Publish the status endpoint",
            "issuetype": "Story", "status_category": "new",
            "components": ["API"], "epic": "APS-3",
            "acceptance_criteria": "", "description": "",
            "story_points": 3, "start_date": None, "due_date": None,
            "updated": "2026-09-01T00:00:00.000+0000",
            "status_changed": None,
        }
        issue.update(overrides)
        return issue

    CFG = {
        "min_title_words": 3,
        "vague_title_terms": ["fix"],
        "vague_title_alone": ["test"],
        "required_fields": [],
        "require_acceptance_criteria": True,
        "acceptance_criteria_markers": ["when ", "then "],
        "require_estimate": False,
        "story_types": ["story"],
    }

    def test_a_clear_title_containing_fix_is_not_vague(self):
        findings = lint.check_issue(self._issue(
            summary="Fix the retry backoff in the exchange client"), self.CFG)
        self.assertFalse(any(f["rule"] == "vague-title" for f in findings))

    def test_a_short_title_points_at_review(self):
        findings = lint.check_issue(self._issue(summary="Fix stuff"), self.CFG)
        vague = [f for f in findings if f["rule"] == "vague-title"]
        self.assertEqual(len(vague), 1)
        self.assertIn("pm refine", vague[0]["message"])

    def test_the_word_when_is_not_acceptance_criteria(self):
        findings = lint.check_issue(self._issue(
            description="when the user clicks save"), self.CFG)
        self.assertTrue(any(f["rule"] == "missing-acceptance-criteria"
                            for f in findings))

    def test_a_given_when_then_scenario_counts(self):
        findings = lint.check_issue(self._issue(
            description="Given an admin, when they export, then a file is saved."),
            self.CFG)
        self.assertFalse(any(f["rule"] == "missing-acceptance-criteria"
                             for f in findings))


class ModelCacheTests(unittest.TestCase):
    def _cfg(self, folder):
        return {
            "endpoint": "http://127.0.0.1:9/v1/chat/completions",
            "name": "qwen-local",
            "temperature": 0.4,
            "json_temperature": 0.2,
            "top_p": 0.8,
            "top_k": 20,
            "presence_penalty": 1.5,
            "max_tokens": 32,
            "timeout": 5,
            "enable_thinking": False,
            "_model_cache_enabled": True,
            "_model_cache_path": folder,
            "_model_ttl": 604800,
            "_cache_mode": "default",
            "_calls": 0,
            "_cache_hits": 0,
        }

    def test_the_second_identical_call_does_not_hit_the_model(self):
        folder = tempfile.mkdtemp(prefix="pm-model-cache-")
        cfg = self._cfg(folder)
        reply = {"choices": [{"message": {"content": "hello"}}]}

        class Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return reply

        with patch("core.model.requests.post", return_value=Resp()) as post:
            first = model.call_model(cfg, "sys", "user")
            second = model.call_model(cfg, "sys", "user")
        self.assertEqual(first, "hello")
        self.assertEqual(second, "hello")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(cfg["_cache_hits"], 1)
        path, count, state = model_cache.status_line(cfg)
        self.assertEqual(count, 1)
        self.assertEqual(state, "warm")
        self.assertTrue(path)

    def test_refresh_asks_again(self):
        folder = tempfile.mkdtemp(prefix="pm-model-cache-")
        cfg = self._cfg(folder)
        reply = {"choices": [{"message": {"content": "hello"}}]}

        class Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return reply

        with patch("core.model.requests.post", return_value=Resp()) as post:
            model.call_model(cfg, "sys", "user")
            cfg["_cache_mode"] = "refresh"
            model.call_model(cfg, "sys", "user")
        self.assertEqual(post.call_count, 2)

    def test_a_spent_budget_does_not_call(self):
        cfg = self._cfg(tempfile.mkdtemp(prefix="pm-budget-"))
        cfg["_deadline"] = time.monotonic() - 1
        with patch("core.model.requests.post") as post:
            text = model.call_model(cfg, "sys", "user")
        self.assertTrue(text.startswith("_The model budget"))
        self.assertEqual(post.call_count, 0)


class MigrationTests(unittest.TestCase):
    def test_version_3_inserts_blocked_and_the_budget(self):
        text = "config_version: 2\nmodel:\n  timeout: 600\ncache:\n  ttl_seconds: 300\n"
        updated = migrations.to_version_3(text)
        self.assertEqual(migrations.read_version(updated), 3)
        self.assertIn("total_timeout: 3600", updated)
        self.assertIn("statuses: [Blocked]", updated)
        self.assertIn("model_ttl_seconds: 604800", updated)
        self.assertIn("timeout: 600", updated)
        again = migrations.to_version_3(updated)
        self.assertEqual(again.count("total_timeout:"), 1)
        self.assertEqual(again.count("statuses:"), 1)

    def test_an_existing_budget_is_not_replaced(self):
        text = "config_version: 2\nmodel:\n  total_timeout: 90\nblocked:\n  statuses: [Parked]\n"
        updated = migrations.to_version_3(text)
        self.assertIn("total_timeout: 90", updated)
        self.assertNotIn("total_timeout: 3600", updated)
        self.assertIn("statuses: [Parked]", updated)
        self.assertNotIn("statuses: [Blocked]", updated)


class ScheduleWarmTests(unittest.TestCase):
    def test_warm_can_be_scheduled(self):
        folder = tempfile.mkdtemp(prefix="pm-warm-sched-")
        cfg = {"state": {"local_path": folder, "shared_path": folder}}
        from argparse import Namespace
        schedule._add(cfg, Namespace(
            target="warm", at="07:00", weekly=None,
            for_audience=None, product=None, workstream=None,
            fail_on=None, fail_under=None))
        store = schedule._store(cfg)
        self.assertEqual(store["jobs"][0]["command"], "warm")
        self.assertTrue(os.path.exists(os.path.join(folder, "schedule.cron")))
