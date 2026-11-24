import unittest
from argparse import Namespace

from commands import daily


class LookbackTests(unittest.TestCase):
    def test_days_flag_wins(self):
        cfg = {"daily": {"lookback_days": 3}}
        self.assertEqual(daily.lookback(cfg, Namespace(days=5)), 5)

    def test_config_used_without_flag(self):
        cfg = {"daily": {"lookback_days": 3}}
        self.assertEqual(daily.lookback(cfg, Namespace(days=None)), 3)

    def test_default_is_one_day(self):
        self.assertEqual(daily.lookback({}, Namespace(days=None)), 1)
        self.assertEqual(daily.lookback({"daily": {}}, Namespace()), 1)

    def test_zero_or_negative_is_refused(self):
        with self.assertRaises(SystemExit):
            daily.lookback({}, Namespace(days=0))
        with self.assertRaises(SystemExit):
            daily.lookback({"daily": {"lookback_days": -2}}, Namespace(days=None))

    def test_parser_leaves_days_unset(self):
        import pm
        args = pm.build_parser().parse_args(["daily"])
        self.assertIsNone(args.days)


if __name__ == "__main__":
    unittest.main()
