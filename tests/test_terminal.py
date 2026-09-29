"""Markdown on the screen: PowerShell, CMD, bash, and a pipe."""

import io
import os
import unittest
from argparse import Namespace
from unittest.mock import patch

from core import render, terminal


REPORT = """\
# Weekly State-of-Product Report
_Audience: Product manager · Window: since 15 Sep_

## Needs attention

- [APS-1](https://x.test/browse/APS-1) Secure exchange (SDX): 1 blocked
- Decision needed: [Rotation cadence](https://x.test/wiki/pages/1001)

| Product | Workstream | Active Epics | At risk |
|---------|------------|-------------:|--------:|
| IP | SDX | 2 | 1 |
| | **Total** | **12** | **1** |

### 🔴 Not ready

**[APS-1 Secure exchange](https://x.test/browse/APS-1)** — In progress
- In this Sprint: [APS-10](https://x.test/browse/APS-10) Rotate, [APS-11](https://x.test/browse/APS-11) Export
  - Waiting on `pm report --sources full` and a \\| pipe
"""


class _Tty(io.StringIO):
    def isatty(self):
        return True


class PipeTests(unittest.TestCase):
    """A pipe or a file: plain text, and every link keeps its address."""

    def setUp(self):
        self.text = terminal.to_terminal(REPORT, terminal.Caps(emoji=False))

    def test_no_markdown_syntax_is_left(self):
        for mark in ("# ", "**", "](", "|---", "`", "\\|"):
            self.assertNotIn(mark, self.text)
        self.assertNotIn("\033", self.text)

    def test_headings_are_underlined(self):
        lines = self.text.splitlines()
        at = lines.index("Weekly State-of-Product Report")
        self.assertEqual(lines[at + 1], "=" * len(lines[at]))
        at = lines.index("Needs attention")
        self.assertEqual(lines[at + 1], "-" * len("Needs attention"))

    def test_every_reference_keeps_its_address(self):
        self.assertIn("APS-1 <https://x.test/browse/APS-1> Secure exchange", self.text)
        self.assertIn("Rotation cadence <https://x.test/wiki/pages/1001>", self.text)
        self.assertIn("APS-10 <https://x.test/browse/APS-10> Rotate,", self.text)

    def test_tables_line_up_and_honour_right_alignment(self):
        lines = self.text.splitlines()
        header = next(line for line in lines if "Workstream" in line)
        ip = next(line for line in lines if line.strip().startswith("IP"))
        total = next(line for line in lines if "Total" in line)
        self.assertEqual(header.index("Workstream"), ip.index("SDX"))
        self.assertEqual(len(ip), len(total))
        self.assertTrue(ip.endswith("2        1"))
        self.assertTrue(total.endswith("12        1"))

    def test_glyphs_go_when_the_console_cannot_draw_them(self):
        self.assertIn("Not ready", self.text)
        self.assertNotIn("🔴", self.text)

    def test_bullets_nest(self):
        self.assertIn("  - Decision needed:", self.text)
        self.assertIn("    - Waiting on pm report --sources full and a | pipe", self.text)


class TerminalTests(unittest.TestCase):
    def test_osc8_links_hide_the_address(self):
        caps = terminal.Caps(styles=True, links=True, width=200)
        text = terminal.to_terminal(REPORT, caps)
        self.assertIn(render.hyperlink("APS-10", "https://x.test/browse/APS-10"), text)
        self.assertNotIn("<https://", text)
        self.assertIn("\033[1m", text)
        self.assertIn("•", text)

    def test_wrapping_hangs_under_the_text_and_never_splits_a_link(self):
        caps = terminal.Caps(width=40)
        text = terminal.to_terminal(
            "- [Certificate rotation cadence](https://x.test/p/1) is waiting "
            "on the security review board to meet next week", caps)
        lines = text.splitlines()
        self.assertTrue(all(len(line) <= 40 for line in lines
                            if "<https://" not in line))
        self.assertTrue(lines[0].startswith("  - Certificate rotation cadence"))
        self.assertTrue(all(line.startswith("    ") for line in lines[1:]))

    def test_a_wide_table_becomes_labelled_lines(self):
        caps = terminal.Caps(width=30)
        text = terminal.to_terminal(REPORT, caps)
        self.assertIn("  IP\n    Workstream: SDX\n    Active Epics: 2", text)

    def test_plain_asks_for_one_fact_per_line(self):
        text = terminal.to_terminal(REPORT, terminal.Caps(records=True))
        self.assertIn("    At risk: 1", text)
        self.assertNotIn("-------  ----------", text)

    def test_preview_does_not_stop_inside_a_table(self):
        shown, rest = terminal.preview(REPORT, limit=10)
        self.assertTrue(shown.rstrip().endswith("| | **Total** | **12** | **1** |"))
        self.assertEqual(rest, len(REPORT.splitlines()) - len(shown.splitlines()))


class DetectionTests(unittest.TestCase):
    def _env(self, **values):
        clean = {k: v for k, v in os.environ.items()
                 if k not in ("WT_SESSION", "TERM_PROGRAM", "ConEmuANSI",
                              "FORCE_HYPERLINK", "NO_COLOR", "TERM")}
        clean.update(values)
        return patch.dict(os.environ, clean, clear=True)

    def test_a_pipe_gets_no_escape_sequences(self):
        with self._env():
            caps = terminal.capabilities(None, io.StringIO())
        self.assertFalse(caps.styles or caps.links)
        self.assertIsNone(caps.width)

    def test_bash_in_a_terminal_gets_links_and_styles(self):
        with self._env(TERM="xterm-256color"), patch("sys.platform", "linux"):
            caps = terminal.capabilities(None, _Tty())
        self.assertTrue(caps.styles and caps.links and caps.emoji)

    def test_windows_terminal_gets_links(self):
        with self._env(WT_SESSION="abc"), patch("sys.platform", "win32"):
            caps = terminal.capabilities(None, _Tty())
        self.assertTrue(caps.styles and caps.links and caps.emoji)

    def test_classic_console_gets_addresses_not_osc8(self):
        render._VT_ENABLED.clear()
        with self._env(), patch("sys.platform", "win32"), \
                patch.object(render, "_enable_windows_vt", return_value=True):
            caps = terminal.capabilities(None, _Tty())
        self.assertTrue(caps.styles)
        self.assertFalse(caps.links)
        self.assertFalse(caps.emoji)

    def test_an_old_console_without_vt_gets_plain_text(self):
        with self._env(), patch("sys.platform", "win32"), \
                patch.object(render, "_enable_windows_vt", return_value=False):
            caps = terminal.capabilities(None, _Tty())
        self.assertFalse(caps.styles or caps.links)

    def test_dumb_terminal_and_plain_and_no_color(self):
        with self._env(TERM="dumb"):
            self.assertFalse(terminal.capabilities(None, _Tty()).styles)
        with self._env(TERM="xterm"), patch("sys.platform", "linux"):
            caps = terminal.capabilities(Namespace(plain=True), _Tty())
            self.assertFalse(caps.styles or caps.links)
            self.assertTrue(caps.records)
        with self._env(TERM="xterm", NO_COLOR="1"), patch("sys.platform", "linux"):
            self.assertFalse(terminal.capabilities(None, _Tty()).links)

    def test_force_hyperlink_overrides_the_guess(self):
        with self._env(FORCE_HYPERLINK="1"):
            self.assertTrue(render.terminal_links(io.StringIO()))
        with self._env(FORCE_HYPERLINK="0", TERM="xterm"), patch("sys.platform", "linux"):
            self.assertFalse(render.terminal_links(_Tty()))

    def test_show_writes_screen_text(self):
        out = io.StringIO()
        with self._env():
            terminal.show("## Done\n\n- [APS-1](https://x.test/browse/APS-1)", stream=out)
        self.assertEqual(out.getvalue(),
                         "Done\n----\n\n  - APS-1 <https://x.test/browse/APS-1>\n")


if __name__ == "__main__":
    unittest.main()
