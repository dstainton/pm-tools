"""What a long command is doing, and how long it has been doing it.

A terminal rewrites one line and adds the elapsed seconds, so a slow Jira
read or model call does not look stuck. Output that is not a terminal (a
test, a pipe, a scheduled run) gets one plain line per step, and a reminder
every 15 seconds while that step is still going.
"""

import sys
import threading
import time


STILL_EVERY = 15

_lock = threading.Lock()
_state = {
    "label": "",
    "base": "",
    "t0": 0.0,
    "live": False,
    "width": 0,
    "next_still": STILL_EVERY,
    "out": None,
    "raw": None,
    "wrapper": None,
    "thread": None,
}


def numbered(index, total, text):
    """`[2/5] text` when there is more than one step, otherwise just the text."""
    if total and total > 1:
        return f"[{index}/{total}] {text}"
    return text


def busy():
    """True while a step is on screen."""
    with _lock:
        return bool(_state["label"])


def start(label, hold=False):
    """Begin a step. The previous step is finished first.

    `hold` waits a second before printing when output is not a terminal, so a
    call that returns immediately does not add a line. A terminal shows the
    step straight away.
    """
    text = str(label or "").strip()
    if not text:
        return
    with _lock:
        if _state["label"] == text:
            return
        _end_locked()
        _state["label"] = text
        _state["base"] = text
        _state["t0"] = time.monotonic()
        _state["next_still"] = STILL_EVERY
        _state["held"] = False
        _state["live"] = False
        _state["width"] = 0
        if _use_terminal():
            _paint_locked(0)
        elif hold:
            _state["held"] = True
            _state["out"] = sys.stdout
        else:
            _state["out"] = sys.stdout
            _write_locked(text + "\n")
        _ensure_thread()


def note(extra):
    """Add a counter to the current step, such as `200 issues`.

    A terminal rewrites the line. Other output keeps the original step and
    mentions the counter only in the "still going" reminder.
    """
    extra = str(extra or "").strip()
    if not extra:
        return
    with _lock:
        if not _state["label"]:
            return
        text = f"{_state['base']} — {extra}"
        if text == _state["label"]:
            return
        _state["label"] = text
        if _state["raw"] is not None:
            elapsed = time.monotonic() - _state["t0"]
            _paint_locked(elapsed)


def finish():
    """Finish the current step and stop rewriting the line."""
    with _lock:
        _end_locked()


class running:
    """Close the last step when the command returns, including on an error."""

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        finish()
        return False


def _isatty(stream):
    try:
        return bool(stream.isatty())
    except Exception:  # noqa: BLE001 — a captured buffer has no isatty
        return False


def _use_terminal():
    """Install the one-line rewriter when stdout is a terminal."""
    if _state["raw"] is not None:
        if sys.stdout is _state["wrapper"]:
            return True
        # stdout was replaced, for example by a test capturing output.
        _state["raw"] = None
        _state["wrapper"] = None
        _state["live"] = False
    if not _isatty(sys.stdout):
        return False
    raw = sys.stdout
    wrapper = _Stream(raw)
    _state["raw"] = raw
    _state["out"] = raw
    _state["wrapper"] = wrapper
    sys.stdout = wrapper
    return True


def _write_locked(text):
    stream = _state["raw"] or _state["out"] or sys.stdout
    try:
        stream.write(text)
        stream.flush()
    except Exception:  # noqa: BLE001 — a closed capture must not kill the timer
        return


def _paint_locked(elapsed):
    seconds = f"  {int(elapsed)}s" if elapsed >= 1 else ""
    text = _state["label"] + seconds
    pad = " " * max(0, _state["width"] - len(text))
    _write_locked("\r" + text + pad)
    _state["live"] = True
    _state["width"] = len(text)


def _end_locked():
    if not _state["label"]:
        return
    if _state.get("held"):
        _state["label"] = ""
        _state["base"] = ""
        _state["held"] = False
        return
    if _state["live"]:
        elapsed = time.monotonic() - _state["t0"]
        suffix = f"  ({int(elapsed)}s)" if elapsed >= 1 else ""
        text = _state["label"] + suffix
        pad = " " * max(0, _state["width"] - len(text))
        _write_locked("\r" + text + pad + "\n")
    _state["label"] = ""
    _state["base"] = ""
    _state["live"] = False
    _state["width"] = 0


def _beat_once():
    with _lock:
        if not _state["label"]:
            return
        if _state.get("held"):
            if _state["out"] is not None and _state["out"] is not sys.stdout:
                _end_locked()
                return
            if time.monotonic() - _state["t0"] < 1:
                return
            _state["held"] = False
            _write_locked(_state["label"] + "\n")
            return
        if _state["raw"] is not None:
            if sys.stdout is not _state["wrapper"]:
                _end_locked()
                return
            _paint_locked(time.monotonic() - _state["t0"])
            return
        if _state["out"] is not None and _state["out"] is not sys.stdout:
            _end_locked()
            return
        elapsed = time.monotonic() - _state["t0"]
        mark = _state["next_still"]
        if elapsed < mark:
            return
        _write_locked(f"  ... still {_state['label']} ({int(elapsed)}s)\n")
        _state["next_still"] = mark + STILL_EVERY


def _loop():
    while True:
        time.sleep(1)
        try:
            _beat_once()
        except Exception:  # noqa: BLE001 — the timer never interrupts the command
            continue


def _ensure_thread():
    thread = _state.get("thread")
    if thread is not None and thread.is_alive():
        return
    thread = threading.Thread(target=_loop, name="pm-progress", daemon=True)
    _state["thread"] = thread
    thread.start()


class _Stream:
    """Pass output through, after giving the progress line its own row."""

    def __init__(self, raw):
        self._raw = raw

    def write(self, text):
        with _lock:
            if _state["live"] and text and not str(text).startswith("\r"):
                try:
                    self._raw.write("\n")
                except Exception:  # noqa: BLE001
                    pass
                _state["live"] = False
                _state["label"] = ""
                _state["base"] = ""
                _state["width"] = 0
            try:
                return self._raw.write(text)
            except Exception:  # noqa: BLE001
                return 0

    def flush(self):
        return self._raw.flush()

    def isatty(self):
        return True

    def __getattr__(self, name):
        return getattr(self._raw, name)
