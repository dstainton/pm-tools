"""Markdown for the screen: PowerShell, CMD, bash, zsh, or a pipe.

Files keep Markdown. What a command prints is text a terminal can show:
headings without hashes, aligned tables, bullets, and links the reader can
open. A terminal that understands OSC 8 gets a clickable label. Anything
else gets the label and then the address in angle brackets, which Windows
Terminal, VS Code, and most Unix terminals also open on click.

A table wider than the terminal becomes one labelled line per cell, and so
does every table under `--plain` or `NO_COLOR`.
"""

import re
import sys
import unicodedata
from dataclasses import dataclass
from typing import Optional

from core import render


@dataclass
class Caps:
    styles: bool = False
    links: bool = False
    emoji: bool = True
    width: Optional[int] = None
    records: bool = False


def capabilities(args=None, stream=None):
    """What this stream can show. A pipe gets plain text with addresses."""
    stream = stream if stream is not None else sys.stdout
    plain = render.plain_requested(args)
    return Caps(
        styles=render.virtual_terminal(stream) and not plain,
        links=render.terminal_links(stream) and not plain,
        emoji=render.terminal_emoji(stream) and not plain,
        width=render.terminal_width(stream),
        records=plain,
    )


_INLINE = re.compile(
    r"\[(?P<label>[^\]\n]+)\]\((?P<url>[^)\s]*)\)"
    r"|\*\*(?P<bold>.+?)\*\*"
    r"|`(?P<code>[^`\n]+)`"
    r"|(?<![\w*\\])\*(?P<star>[^\s*](?:[^*\n]*?[^\s*])?)\*(?![\w*])"
    r"|(?<![\w\\])_(?P<under>[^\s_](?:[^_\n]*?[^\s_])?)_(?!\w)"
    r"|\\(?P<escaped>[\\`*_\[\]()#|>+\-.!])"
)
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2B50\u2B55\uFE0F\u200D]")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_LIST = re.compile(r"^(?P<indent>\s*)(?P<marker>[-*+]|\d+[.)])\s+(?P<body>.*)$")
_QUOTE = re.compile(r"^\s*>\s?(.*)$")
_RULE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_SEP_CELL = re.compile(r"^:?-+:?$")
_SGR = {"bold": "1", "italic": "3", "code": "36", "underline": "4"}


def _width(text):
    total = 0
    for ch in text:
        if unicodedata.combining(ch) or ch in "\u200d\ufe0f":
            continue
        total += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return total


def _runs(text, styles=frozenset(), url=None):
    """(text, styles, url) pieces. Link labels keep the url they point at."""
    runs = []
    pos = 0
    for match in _INLINE.finditer(text):
        if match.start() > pos:
            runs.append((text[pos:match.start()], styles, url))
        if match.group("label") is not None:
            runs.extend(_runs(match.group("label"), styles,
                              match.group("url") or url))
        elif match.group("bold") is not None:
            runs.extend(_runs(match.group("bold"), styles | {"bold"}, url))
        elif match.group("code") is not None:
            runs.append((match.group("code"), styles | {"code"}, url))
        elif match.group("star") is not None:
            runs.extend(_runs(match.group("star"), styles | {"italic"}, url))
        elif match.group("under") is not None:
            runs.extend(_runs(match.group("under"), styles | {"italic"}, url))
        else:
            runs.append((match.group("escaped"), styles, url))
        pos = match.end()
    if pos < len(text):
        runs.append((text[pos:], styles, url))
    return runs


def _words(runs):
    """Whitespace splits words. A link label never splits."""
    words = []
    current = []
    for text, styles, url in runs:
        if url:
            current.append((text, styles, url))
            continue
        for part in re.split(r"(\s+)", text):
            if not part:
                continue
            if part.isspace():
                if current:
                    words.append(current)
                    current = []
            else:
                current.append((part, styles, None))
    if current:
        words.append(current)
    return words


def _style(text, styles, caps):
    if not caps.styles or not styles or not text:
        return text
    codes = ";".join(_SGR[name] for name in sorted(styles) if name in _SGR)
    return f"\033[{codes}m{text}\033[0m" if codes else text


def _tokens(text, caps, styles=frozenset()):
    """[(visible width, rendered text)], one per unbreakable word."""
    tokens = []
    for pieces in _words(_runs(text, frozenset(styles))):
        visible, shown = "", ""
        index = 0
        while index < len(pieces):
            url = pieces[index][2]
            group = [pieces[index]]
            index += 1
            while index < len(pieces) and pieces[index][2] == url:
                group.append(pieces[index])
                index += 1
            label = "".join(piece[0] for piece in group)
            styled = "".join(_style(t, s, caps) for t, s, _u in group)
            if not url:
                visible += label
                shown += styled
            elif caps.links:
                visible += label
                shown += render.hyperlink(styled, url)
            elif label.strip() == url:
                visible += url
                shown += url
            else:
                visible += label
                shown += styled
                tokens.append((_width(visible), shown))
                visible, shown = f"<{url}>", f"<{url}>"
        if visible or shown:
            tokens.append((_width(visible), shown))
    return tokens


def _inline(text, caps, styles=frozenset()):
    tokens = _tokens(text, caps, styles)
    width = sum(size for size, _shown in tokens) + max(0, len(tokens) - 1)
    return width, " ".join(shown for _size, shown in tokens)


def render_line(text, caps=None):
    """One line of inline Markdown for the screen, without wrapping."""
    return _inline(text, caps or Caps())[1]


def _wrap(tokens, first, rest, width):
    if not tokens:
        return [first.rstrip()]
    if not width:
        return [first + " ".join(shown for _size, shown in tokens)]
    lines = []
    line, used, empty = first, _width(first), True
    for size, shown in tokens:
        need = size if empty else size + 1
        if not empty and used + need > width:
            lines.append(line)
            line, used, empty = rest, _width(rest), True
            need = size
        line += shown if empty else " " + shown
        used += need
        empty = False
    lines.append(line)
    return lines


def _split_row(line):
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|") and not text.endswith("\\|"):
        text = text[:-1]
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", text)]


def _table(raw, caps, indent="  "):
    rows = [_split_row(line) for line in raw]
    header = []
    aligns = []
    if len(rows) > 1 and rows[1] and all(_SEP_CELL.match(c.replace(" ", ""))
                                         for c in rows[1] if c):
        header = rows[0]
        aligns = ["right" if c.strip().endswith(":") and not c.strip().startswith(":")
                  else "left" for c in rows[1]]
        rows = rows[2:]
    columns = max([len(header)] + [len(row) for row in rows])
    header = header + [""] * (columns - len(header))
    aligns = aligns + ["left"] * (columns - len(aligns))
    shown_header = [_inline(cell, caps, {"bold"}) for cell in header]
    shown_rows = [[_inline(cell, caps) for cell in row + [""] * (columns - len(row))]
                  for row in rows]
    widths = [0] * columns
    for row in ([shown_header] if any(header) else []) + shown_rows:
        for index, (size, _shown) in enumerate(row):
            widths[index] = max(widths[index], size)
    total = len(indent) + sum(widths) + 2 * (columns - 1)
    if caps.records or (caps.width and total > caps.width):
        padded = [row + [""] * (columns - len(row)) for row in rows]
        return _records(header, padded, caps, indent)

    def line(cells):
        parts = []
        for index, (size, shown) in enumerate(cells):
            pad = " " * (widths[index] - size)
            parts.append(pad + shown if aligns[index] == "right" else shown + pad)
        return (indent + "  ".join(parts)).rstrip()

    out = []
    if any(header):
        out.append(line(shown_header))
        dash = "─" if caps.styles else "-"
        out.append(indent + "  ".join(dash * width for width in widths))
    out.extend(line(row) for row in shown_rows)
    return out


def _records(header, rows, caps, indent):
    """One labelled line per cell. Reads the same at any width."""
    labels = [_inline(cell, caps)[1] for cell in header]
    plain_labels = [_inline(cell, Caps())[1] for cell in header]
    out = []
    for row in rows:
        filled = [index for index, cell in enumerate(row) if _inline(cell, caps)[0]]
        if not filled:
            continue
        if out:
            out.append("")
        title = filled[0]
        out.extend(_wrap(_tokens(row[title], caps, {"bold"}), indent,
                         indent, caps.width))
        for index in filled[1:]:
            label = labels[index] if index < len(labels) else ""
            first = f"{indent}  {label}: " if label else f"{indent}  "
            hang = " " * (len(indent) + 2 + (_width(plain_labels[index]) + 2 if label else 0))
            out.extend(_wrap(_tokens(row[index], caps), first, hang, caps.width))
    return out



def to_terminal(markdown, caps=None):
    """Markdown in, screen text out. Files keep the Markdown."""
    caps = caps or Caps()
    out = []

    def blank():
        if out and out[-1] != "":
            out.append("")

    lines = (markdown or "").replace("\r\n", "\n").split("\n")
    index = 0
    fenced = False
    while index < len(lines):
        line = lines[index].rstrip()
        index += 1
        if line.strip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            out.append("    " + line)
            continue
        if not caps.emoji:
            line = _EMOJI.sub("", line)
        if not line.strip():
            blank()
            continue
        if line.lstrip().startswith("|"):
            block = [line]
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                block.append(lines[index].rstrip() if caps.emoji
                             else _EMOJI.sub("", lines[index].rstrip()))
                index += 1
            out.extend(_table(block, caps))
            continue
        heading = _HEADING.match(line)
        if heading:
            level = len(heading.group(1))
            blank()
            size, shown = _inline(heading.group(2), caps, {"bold"})
            out.append(shown)
            if level == 1:
                out.append(("═" if caps.styles else "=") * size)
            elif level == 2:
                out.append(("─" if caps.styles else "-") * size)
            continue
        if _RULE.match(line):
            out.append(("─" if caps.styles else "-") * min(caps.width or 40, 40))
            continue
        quote = _QUOTE.match(line)
        if quote:
            bar = "│ " if caps.styles else "| "
            out.extend(_wrap(_tokens(quote.group(1), caps), "  " + bar,
                             "  " + bar, caps.width))
            continue
        item = _LIST.match(line)
        if item:
            depth = len(item.group("indent").expandtabs(4)) // 2
            marker = item.group("marker")
            if marker in "-*+":
                marker = ("•" if depth == 0 else "◦") if caps.styles else "-"
            first = "  " * (depth + 1) + marker + " "
            out.extend(_wrap(_tokens(item.group("body"), caps), first,
                             " " * _width(first), caps.width))
            continue
        lead = line[:len(line) - len(line.lstrip())]
        out.extend(_wrap(_tokens(line.strip(), caps), lead, lead, caps.width))
    while out and out[-1] == "":
        out.pop()
    while out and out[0] == "":
        out.pop(0)
    return "\n".join(out) + "\n" if out else ""


def preview(markdown, limit=40):
    """The first `limit` lines, never stopping inside a table."""
    lines = (markdown or "").splitlines()
    cut = min(limit, len(lines))
    while cut < len(lines) and lines[cut - 1].lstrip().startswith("|") \
            and lines[cut].lstrip().startswith("|"):
        cut += 1
    return "\n".join(lines[:cut]), len(lines) - cut


def show(markdown, args=None, stream=None):
    """Print Markdown the way this terminal, or this pipe, can show it."""
    stream = stream if stream is not None else sys.stdout
    text = to_terminal(markdown, capabilities(args, stream))
    stream.write(text)
    stream.flush()
