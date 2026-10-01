"""Shared screen and Markdown rendering.

The reference is the link text, in the terminal and in Markdown: a Jira
key, a Confluence page title, or a SharePoint file name. The address is
not printed beside it when the terminal can open OSC 8. Severity is a
word. `--plain` and `NO_COLOR` drop glyphs and OSC 8 sequences.
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


def _isatty(stream):
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False


_VT_ENABLED = {}


def virtual_terminal(stream=None):
    """True when escape sequences reach a terminal that understands them.

    A pipe, a file, and TERM=dumb do not. On Windows the console has to be
    switched into virtual-terminal mode first. Windows 10 and later allow
    that for CMD and PowerShell; an older console refuses and gets text.
    """
    stream = stream if stream is not None else sys.stdout
    if not _isatty(stream):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    if sys.platform != "win32":
        return True
    if os.environ.get("WT_SESSION") or os.environ.get("TERM_PROGRAM"):
        return True
    return _enable_windows_vt(stream)


def _enable_windows_vt(stream):
    handle_id = -12 if stream is sys.stderr else -11
    if handle_id in _VT_ENABLED:
        return _VT_ENABLED[handle_id]
    enabled = False
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(handle_id)
        mode = wintypes.DWORD()
        if handle and kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            wanted = mode.value | 0x0004           # ENABLE_VIRTUAL_TERMINAL_PROCESSING
            enabled = bool(kernel32.SetConsoleMode(handle, wanted))
    except (AttributeError, OSError, ImportError, ValueError):
        enabled = False
    _VT_ENABLED[handle_id] = enabled
    return enabled


def terminal_links(stream=None):
    """True when the reference itself can be the link.

    OSC 8 makes the label clickable and does not print the address beside
    it. PowerShell, CMD, Windows Terminal, VS Code, and the usual Unix
    terminals get the sequence once virtual-terminal processing is on. A
    console that ignores OSC 8 still shows the label. A pipe, a file, and
    TERM=dumb never get the sequence. FORCE_HYPERLINK=1 or 0 overrides the
    guess. Callers drop the sequence for ``--plain`` and ``NO_COLOR``, and
    then print the address after the name.
    """
    stream = stream if stream is not None else sys.stdout
    forced = os.environ.get("FORCE_HYPERLINK")
    if forced is not None and forced.strip() != "":
        return forced.strip() not in ("0", "false", "no")
    return virtual_terminal(stream)


def terminal_emoji(stream=None):
    """False on the classic Windows console, whose fonts draw boxes."""
    if not virtual_terminal(stream):
        return False
    if sys.platform != "win32":
        return True
    return bool(os.environ.get("WT_SESSION") or os.environ.get("TERM_PROGRAM"))


def terminal_width(stream=None):
    """Column count when stdout is a terminal. None means do not reflow."""
    stream = stream if stream is not None else sys.stdout
    if not _isatty(stream):
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


def browse_url(cfg, key, sample=None):
    """The Jira page for `key`, from jira.base_url or another issue's url."""
    key = str(key or "").strip()
    if not key:
        return ""
    base = (((cfg or {}).get("jira") or {}).get("base_url") or "").rstrip("/")
    if not base and sample and "/browse/" in str(sample):
        base = str(sample).split("/browse/")[0]
    return f"{base}/browse/{key}" if base else ""


def issue_link(key, summary="", url="", sep=" "):
    """`[KEY](url) summary`. The key stays the link text."""
    shown = markdown_link(key, url)
    summary = (summary or "").strip()
    if not summary:
        return shown
    return f"{shown}{sep}{summary}" if shown else summary


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
