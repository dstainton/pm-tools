"""Windowed Jira comments: the reader, the caps, and where each command shows them."""

import datetime as dt
import unittest
from unittest.mock import patch

from commands import daily, release_notes, triage
from core import comments, migrations, model, sources, state
from tests.fake_jira import FakeJira


NOW = dt.datetime(2026, 9, 23, 12, 0, tzinfo=dt.timezone.utc)
OPTS = {
    "enabled": True,
    "max_per_issue": 3,
    "max_issues": 25,
    "excerpt_chars": 240,
    "report_days": 7,
    "section_chars": 6000,
}


def _stamp(when):
    return when.strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def _comment(when, text, who="Dana"):
    return {
        "created": _stamp(when),
        "author": {"displayName": who},
        "body": text,
    }


class ReaderTests(unittest.TestCase):
    def _server(self, comments_on_issue):
        issue = {
            "key": "APS-1", "project": "APS", "issuetype": "Story",
            "summary": "Rotate the certificate", "comments": comments_on_issue,
        }
        return FakeJira([issue])

    def test_a_comment_inside_the_window_is_kept_and_an_older_one_is_not(self):
        thread = [
            _comment(NOW - dt.timedelta(days=30), "Old note from last quarter."),
            _comment(NOW - dt.timedelta(days=1), "Waiting on the certificate review."),
        ]
        with self._server(thread) as jira:
            cfg = {"base_url": jira.url, "email": "a@b.c", "api_token": "t"}
            kept = sources.fetch_comments(
                cfg, "APS-1", cutoff=NOW - dt.timedelta(days=7))
        texts = [comments.comment_text(c) for c in kept]
        self.assertEqual(texts, ["Waiting on the certificate review."])

    def test_paging_stops_at_the_cutoff(self):
        thread = [_comment(NOW - dt.timedelta(days=i), f"note {i}")
                  for i in range(60)]
        with self._server(thread) as jira:
            cfg = {"base_url": jira.url, "email": "a@b.c", "api_token": "t"}
            before = len(jira.calls)
            kept = sources.fetch_comments(
                cfg, "APS-1", cutoff=NOW - dt.timedelta(days=10))
            gets = [c for c in jira.calls[before:]
                    if c[0] == "GET" and "/comment" in c[1]]
        self.assertEqual(len(gets), 1)
        self.assertEqual(len(kept), 11)
        self.assertEqual(comments.comment_text(kept[0]), "note 10")
        self.assertEqual(comments.comment_text(kept[-1]), "note 0")

    def test_a_long_window_reads_the_next_page_and_then_stops(self):
        thread = [_comment(NOW - dt.timedelta(days=i), f"note {i}")
                  for i in range(60)]
        with self._server(thread) as jira:
            cfg = {"base_url": jira.url, "email": "a@b.c", "api_token": "t"}
            before = len(jira.calls)
            kept = sources.fetch_comments(
                cfg, "APS-1", cutoff=NOW - dt.timedelta(days=55))
            gets = [c for c in jira.calls[before:]
                    if c[0] == "GET" and "/comment" in c[1]]
        self.assertEqual(len(gets), 2)
        self.assertEqual(len(kept), 56)

    def test_limit_keeps_the_newest(self):
        thread = [_comment(NOW - dt.timedelta(days=i), f"note {i}")
                  for i in range(10)]
        with self._server(thread) as jira:
            cfg = {"base_url": jira.url, "email": "a@b.c", "api_token": "t"}
            kept = sources.fetch_comments(cfg, "APS-1", limit=3)
        self.assertEqual(
            [comments.comment_text(c) for c in kept],
            ["note 2", "note 1", "note 0"])

    def test_disabled_block_makes_no_request(self):
        opts = dict(OPTS, enabled=False)
        issues = [{"key": "APS-1", "updated": _stamp(NOW)}]
        with patch("core.sources.fetch_comments") as fetch:
            found = comments.load_for_issues({}, issues, NOW, opts)
        fetch.assert_not_called()
        self.assertEqual(found, {})

    def test_max_issues_caps_the_number_of_requests(self):
        issues = [{"key": f"APS-{i}", "updated": _stamp(NOW)} for i in range(30)]
        opts = dict(OPTS, max_issues=25)

        def _fetch(cfg, key, cutoff=None, limit=None):
            return [_comment(NOW, "hello")]

        with patch("core.sources.fetch_comments", side_effect=_fetch) as fetch:
            found = comments.load_for_issues({}, issues, NOW, opts)
        self.assertEqual(fetch.call_count, 25)
        self.assertEqual(len(found), 25)


class WindowTests(unittest.TestCase):
    def test_first_report_uses_report_days(self):
        cutoff = comments.report_cutoff({}, OPTS, now=NOW)
        self.assertEqual(cutoff, NOW - dt.timedelta(days=7))

    def test_the_next_report_uses_the_saved_timestamp(self):
        snapshot = {"_ran_at": "2026-09-20T15:00:00+00:00",
                    "APS-1": {"title": "A", "watch": "To Do", "ref": "SDX-J1"}}
        cutoff = comments.report_cutoff(snapshot, OPTS, now=NOW)
        self.assertEqual(
            cutoff, dt.datetime(2026, 9, 20, 15, tzinfo=dt.timezone.utc))

    def test_a_saved_timestamp_is_not_a_dropped_item(self):
        previous = {
            "_ran_at": "2026-09-20T15:00:00+00:00",
            "APS-1": {"title": "APS-1: One", "watch": "To Do", "ref": "SDX-J1"},
        }
        items = [{
            "uid": "APS-1", "title": "APS-1: One", "watch": "To Do",
            "ref": "SDX-J1",
        }]
        new, changed, dropped = state.compute_changes(previous, items)
        self.assertEqual((new, changed, dropped), ([], [], []))

    def test_first_brief_uses_report_days_and_a_date_is_midnight(self):
        self.assertEqual(
            comments.audience_cutoff(None, OPTS, now=NOW),
            NOW - dt.timedelta(days=7))
        self.assertEqual(
            comments.audience_cutoff("2026-09-20", OPTS, now=NOW),
            dt.datetime(2026, 9, 20, tzinfo=dt.timezone.utc))


class MaterialTests(unittest.TestCase):
    def test_an_old_ref_is_not_cited_when_an_item_drops_out(self):
        block = state.build_change_block(
            [], [], [("page-1", {"title": "Old page", "ref": "SDX-J1"})], False)
        self.assertNotIn("SDX-J1", block)
        keyed = state.build_change_block(
            [], [], [("APS-10", {"title": "Publish", "ref": "SDX-J1"})], False)
        self.assertIn("[APS-10]", keyed)
        self.assertNotIn("SDX-J1", keyed)
    def test_a_comment_is_not_cut_by_the_status_line_cap(self):
        comment = "2026-09-22 Dana: " + ("y" * 200)
        block = model.build_material([{
            "ref": "SDX-J1", "source": "Jira", "title": "APS-1: One",
            "detail": "Status: In Progress " + ("x" * 400),
            "comments": [comment],
        }])
        self.assertIn("...", block)
        self.assertIn("y" * 200, block)

    def test_the_section_budget_omits_a_later_issue(self):
        items = [
            {"ref": "SDX-J1", "source": "Jira", "title": "A", "detail": "",
             "comments": ["1234567890"]},
            {"ref": "SDX-J2", "source": "Jira", "title": "B", "detail": "",
             "comments": ["abcdefghij"]},
        ]
        block = model.build_material(items, comment_budget=10)
        self.assertIn("1234567890", block)
        self.assertNotIn("abcdefghij", block)
        self.assertIn("+1 commented issues omitted to keep the prompt short.",
                      block)

    def test_the_prompt_may_use_a_comment_and_not_as_a_status_change(self):
        self.assertIn("A comment is not a status change.",
                      model.REPORT_SYSTEM_PROMPT)
        self.assertIn("[APS-10]", model.REPORT_SYSTEM_PROMPT)
        self.assertNotIn("SDX-J", model.REPORT_SYSTEM_PROMPT)

    def test_release_notes_put_the_excerpt_on_the_bullet(self):
        rows = [{
            "product_name": "Integration Platform",
            "product_abbrev": "IP",
            "workstream_name": "Secure Data Exchange",
            "workstream_abbrev": "SDX",
            "key": "APS-61",
            "summary": "Ship the exchange retry budget",
            "comments": ["2026-09-18 A. Lee: Shipped the retry budget."],
        }]
        text = "\n".join(release_notes.bullet_lines(rows))
        self.assertIn("- APS-61: Ship the exchange retry budget", text)
        self.assertIn("  - 2026-09-18 A. Lee: Shipped the retry budget.", text)

    def test_daily_prints_the_comment_under_the_card(self):
        moved = [{
            "key": "APS-10", "url": "http://example/APS-10",
            "summary": "Publish exchange status endpoint",
            "transitions": [{
                "from": "To Do", "to": "In Review", "who": "A. Lee",
                "when": NOW,
            }],
            "comments": ["2026-09-23 A. Lee: Waiting on the certificate review."],
        }]
        ws = {"name": "Secure Data Exchange", "abbrev": "SDX"}
        text = daily.build_markdown({"products": []}, [(ws, moved, [])], 1,
                                    "assignee")
        self.assertIn("Waiting on the certificate review.", text)
        self.assertIn("APS-10", text)


class TriageQuoteTests(unittest.TestCase):
    def test_the_reply_line_quotes_the_mention(self):
        issue = {"key": "APS-1", "updated": _stamp(NOW)}
        me = {"accountId": "abc-1", "displayName": "Dana"}
        comment = {
            "created": _stamp(NOW),
            "author": {"displayName": "Sam"},
            "body": {"type": "doc", "content": [{
                "type": "paragraph",
                "content": [
                    {"type": "mention", "attrs": {"id": "abc-1"}},
                    {"type": "text", "text": " can you review the cert?"},
                ],
            }]},
        }
        with patch("core.sources.fetch_comments", return_value=[comment]):
            named = triage._mentioned(issue, me, 3, {})
        self.assertTrue(named)
        self.assertIn("can you review the cert?", issue["mention_comment"])
        self.assertIn(issue["mention_comment"],
                      triage.describe("mention", issue))


class MigrationTests(unittest.TestCase):
    def test_version_4_inserts_the_comments_block(self):
        text = "config_version: 3\nconfluence:\n  lookback_days: 7\n"
        updated = migrations.to_version_4(text)
        self.assertEqual(migrations.read_version(updated), 4)
        self.assertIn("max_per_issue: 3", updated)
        self.assertIn("section_chars: 6000", updated)
        self.assertLess(updated.index("comments:"), updated.index("confluence:"))
        again = migrations.to_version_4(updated)
        self.assertEqual(again.count("max_per_issue:"), 1)

    def test_an_existing_switch_is_not_replaced(self):
        text = "config_version: 3\ncomments:\n  enabled: false\n"
        updated = migrations.to_version_4(text)
        self.assertIn("enabled: false", updated)
        self.assertNotIn("enabled: true", updated)
        self.assertIn("report_days: 7", updated)
        self.assertEqual(updated.count("enabled:"), 1)
