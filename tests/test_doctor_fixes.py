"""A warn or FAIL line names the command that addresses it."""

import io
import unittest
from contextlib import redirect_stdout

from commands import doctor


class FixLineTests(unittest.TestCase):
    def setUp(self):
        doctor.reset_fixes()

    def _shown(self, fn):
        buf = io.StringIO()
        with redirect_stdout(buf):
            fn()
        return buf.getvalue()

    def test_each_warning_names_one_command(self):
        shown = self._shown(lambda: doctor._check_model({"model": {}}))
        self.assertIn("no model.endpoint configured", shown)
        self.assertIn("Run: pm setup --section model", shown)

        doctor.reset_fixes()
        shown = self._shown(lambda: doctor._check_custom_fields({"jira": {}}, []))
        self.assertIn("story points (not configured)", shown)
        self.assertIn("Run: pm doctor --discover-fields", shown)
        self.assertEqual(shown.count("Run: pm doctor --discover-fields"), 3)

        doctor.reset_fixes()
        shown = self._shown(lambda: doctor._check_confluence(
            {"workstreams": [{"abbrev": "SDX"}]}))
        self.assertIn("no confluence_space or confluence_page", shown)
        self.assertIn("Run: pm setup --section confluence", shown)
        self.assertNotIn("--workstream", shown)

        doctor.reset_fixes()
        shown = self._shown(lambda: doctor._check_registers({}))
        self.assertIn("none configured", shown)
        self.assertIn("leave them off", shown)
        self.assertIn("Run: pm setup --section registers", shown)

    def test_a_disabled_cache_is_not_a_write(self):
        shown = self._shown(lambda: doctor._check_cache({"cache": {"enabled": False}}))
        self.assertIn("cache.enabled: true", shown)
        self.assertIn("does not write it", shown)
        self.assertNotIn("Run:", shown)
        self.assertEqual(doctor._fixes, [])

    def test_the_summary_lists_each_command_once(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            doctor._warn("model", "no model.endpoint configured",
                         fix="pm setup --section model")
            doctor._warn("model", "again", fix="pm setup --section model")
            doctor._warn("cache", "off",
                         note="Set cache.enabled: true to turn it back on. "
                              "This check does not write it.")
            doctor._print_fixes()
        shown = buf.getvalue()
        self.assertEqual(shown.count("pm setup --section model"), 3)
        self.assertIn("To address these:", shown)
        self.assertNotIn("cache.enabled", shown.split("To address these:", 1)[1])

    def test_an_ok_line_has_no_command(self):
        shown = self._shown(lambda: doctor._ok("config version", "7"))
        self.assertIn("ok", shown)
        self.assertNotIn("Run:", shown)


if __name__ == "__main__":
    unittest.main()
