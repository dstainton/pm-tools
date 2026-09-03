import unittest

from commands import refine


WORKSHEET = """\
# Refine SDX 2026-09-03

## APS-11
# was: Fix stuff
title: Fix retry handling in the exchange client
criteria: |
  Given a failed request
  When the client retries
  Then the exchange succeeds
estimate: 3

## APS-20
# was: Rate limiting
title: Rate limiting for public endpoints
"""


class ParseWorksheetTests(unittest.TestCase):
    def test_keeps_edited_fields(self):
        parsed = refine.parse_worksheet(WORKSHEET)
        self.assertEqual(parsed["APS-11"]["title"],
                         "Fix retry handling in the exchange client")
        self.assertIn("Given a failed request", parsed["APS-11"]["criteria"])
        self.assertEqual(parsed["APS-11"]["estimate"], 3)
        self.assertEqual(parsed["APS-20"]["title"],
                         "Rate limiting for public endpoints")
        self.assertNotIn("criteria", parsed["APS-20"])
        self.assertNotIn("estimate", parsed["APS-20"])

    def test_deleted_field_is_absent(self):
        text = "## APS-11\n# was: Fix stuff\n"
        self.assertEqual(refine.parse_worksheet(text), {})

    def test_blank_estimate_is_skipped(self):
        text = "## APS-20\nestimate: \n"
        self.assertEqual(refine.parse_worksheet(text), {})


class MedianTests(unittest.TestCase):
    def test_median_of_closed_points(self):
        self.assertEqual(refine._median_estimate([2, 3, 5, 8]), 4)
        self.assertIsNone(refine._median_estimate([]))
        self.assertIsNone(refine._median_estimate([0, None]))
