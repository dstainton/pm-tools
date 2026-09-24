"""Shared screen and Markdown rendering.

Issue keys are the link text, in the terminal and in Markdown. Severity
is a word. `--plain` and `NO_COLOR` drop glyphs and OSC 8 sequences.
"""

import os
import shutil
import sys
import textwrap


def plain_requested(args=None):
    """True when the user asked for the labelled, glyph-free path."""
    if os.environ.get("NO_COLOR"):
        return True
    return bool(getattr(args, "plain", False)) if args is not None else False


def terminal_links(stream=None):
    """True when this terminal can turn an OSC 8 sequence into a click."""
    stream = stream if stream is not None else sys.stdout
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False


def terminal_width(stream=None):
    """Column count when stdout is a terminal. None means do not reflow."""
    if not terminal_links(stream):
        return None
    try:
        columns = shutil.get_terminal_size().columns
    except OSError:
        return None
    return columns if columns and columns > 20 else None


def hyperlink(label, url):
    """OSC 8. The terminator is ST (ESC \\). Windows Terminal opens this."""
    return f"\033]8;;{url}\033\\{label}\033]8;;\033\\"


def issue_cell(key, url, width, links):
    """Pad on the visible key. The link sequence has no width of its own."""
    key = "" if key is None else str(key)
    shown = hyperlink(key, url) if links and url and key else key
    return shown + (" " * max(0, width - len(key)))


def markdown_link(key, url):
    """Link text is the issue key, never the word open."""
    key = "" if key is None else str(key)
    if not url or not key:
        return key
    return f"[{key}]({url})"


def severity_mark(severity, plain=False):
    """Word first. The glyph is extra, and only when colour is allowed."""
    name = {"error": "Error", "warn": "Warn", "review": "Review"}.get(
        severity, str(severity or ""))
    if plain or os.environ.get("NO_COLOR"):
        return name
    glyph = {"error": "🔴", "warn": "🟠", "review": "🔵"}.get(severity, "")
    return f"{glyph} {name}".strip()


def count_phrase(n, singular, plural=None):
    word = singular if int(n) == 1 else (plural or singular + "s")
    return f"{int(n)} {word}"


def hanging(marker, body, indent, width):
    """Wrap so the next line starts under the first word of the body."""
    prefix = indent + marker
    text = (body or "").strip()
    full = prefix + text
    room = (width - len(prefix)) if width else 0
    if not text or not width or room < 8 or len(full) <= width:
        return [full]
    parts = textwrap.wrap(
        text, width=room, break_long_words=False, break_on_hyphens=False)
    if not parts:
        return [full]
    hang = " " * len(prefix)
    return [prefix + parts[0]] + [hang + part for part in parts[1:]]


def run_prefix():
    """A word in front of a command the reader can type."""
    return "Run:"
