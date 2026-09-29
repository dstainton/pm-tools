"""Compare a config file with the template this install ships.

`pm update` fills in every setting the template has and the file lacks, then
says what else changed. `pm setup --review` steps through the same list.
Edits are made line by line, so the author's comments and order stay put.

The review record next to the config (`config.reviewed.json` beside
`config.yaml`) holds the shipped defaults the user last saw. With it, a
default that changed since is told apart from a value the user chose. A
config older than the record keeps working: the defaults of earlier releases
in EARLIER_DEFAULTS stand in for it.
"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

import yaml


# Lists and maps that hold the user's own data. The template has examples.
USER_DATA = ("config_version", "products", "workstreams", "registers")
# Checked by their own validators. Every key under them is optional.
FREE_FORM = USER_DATA + ("prompts", "queries", "conventions",
                         "definition_of_done")
SECRET_KEYS = ("api_token", "client_secret", "webhook", "api_key")

# Shipped defaults that a later release changed. A file that still has one
# of these was never edited there.
EARLIER_DEFAULTS = {
    "model.endpoint": ["http://127.0.0.1:8080/v1/chat/completions"],
    "model.name": ["qwen-local"],
    "cache.path": ["~/.pm/cache"],
    "today.state_file": ["~/.pm/today.json"],
    "output.directory": ["~/.pm/out"],
}

# Old names that are still read. The value belongs under the new name.
RENAMED = {
    "confluence.root_title": "confluence.team_page",
    "confluence.root_page_id": "confluence.team_page_id",
    "publish.teams_webhook": "publish.teams.webhook",
}

# Settings an earlier release read and this one does not.
RETIRED = {
    "lint.vague_title_terms": "lint.vague_title_alone replaced it; those "
                              "words flag only when they are the whole title",
    "lint.acceptance_criteria_markers": "acceptance criteria are found by a "
                                        "heading or a Given/When/Then scenario",
}

_KEY = re.compile(
    r"""^(?P<indent> *)(?P<key>[A-Za-z_][\w-]*|"[^"\n]+"|'[^'\n]+')\s*:"""
    r"""(?:[ \t]+(?P<rest>.*))?$""")
_PLACEHOLDER = re.compile(r"<[A-Z][A-Z0-9_]*>")
_RULE = re.compile(r"^[-=~*]{3,}$")
_SECTION = re.compile(r"^\d+[a-z]?\d*\.\s+")


@dataclass
class Node:
    """One block-mapping key and the lines it spans."""
    path: Tuple[str, ...]
    indent: int
    lead: int
    line: int
    end: int
    inline: str
    comment: str = ""
    kind: str = "scalar"
    children: List["Node"] = field(default_factory=list)


@dataclass
class Report:
    """What `pm update` changed in the file and what it left for review."""
    added: List[Tuple[str, ...]] = field(default_factory=list)
    needs_details: List[Tuple[str, ...]] = field(default_factory=list)
    by_hand: List[Tuple[str, ...]] = field(default_factory=list)
    new: List[Tuple[str, ...]] = field(default_factory=list)
    changed: List[dict] = field(default_factory=list)
    renamed: List[Tuple[str, str]] = field(default_factory=list)
    unknown: List[Tuple[str, ...]] = field(default_factory=list)

    def empty(self):
        return not (self.added or self.needs_details or self.by_hand
                    or self.new or self.changed or self.renamed
                    or self.unknown)


# ---------------------------------------------------------------------------
#  Reading the file as lines
# ---------------------------------------------------------------------------

def _indent(line):
    return len(line) - len(line.lstrip(" "))


def _is_comment(line):
    return line.lstrip().startswith("#")


def _split_comment(rest):
    """`value  # note` -> (`value`, `# note`). A # inside quotes is kept."""
    quote = None
    for index, ch in enumerate(rest):
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in "\"'" and (index == 0 or rest[index - 1] in " [{,:"):
            quote = ch
        elif ch == "#" and (index == 0 or rest[index - 1] in " \t"):
            return rest[:index].rstrip(), rest[index:]
    return rest.rstrip(), ""


def _end(lines, start, indent, may_list):
    last = start
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if not line.strip():
            continue
        depth = _indent(line)
        if _is_comment(line):
            if depth > indent:
                last = index
            continue
        if depth > indent:
            last = index
            continue
        stripped = line.lstrip()
        if may_list and depth == indent and (stripped == "-" or stripped.startswith("- ")):
            last = index
            continue
        break
    return last + 1


def _lead(lines, index, indent):
    start = index
    while start > 0 and _is_comment(lines[start - 1]) \
            and _indent(lines[start - 1]) == indent:
        start -= 1
    return start


def _parse(lines, lo, hi, parent, nodes):
    """Keys of the block mapping in lines[lo:hi]. None when it is a list."""
    children = []
    level = None
    index = lo
    while index < hi:
        line = lines[index]
        if not line.strip() or _is_comment(line):
            index += 1
            continue
        depth = _indent(line)
        if level is None:
            level = depth
        stripped = line.lstrip()
        if stripped == "-" or stripped.startswith("- "):
            if not children:
                return None
            index += 1
            continue
        match = _KEY.match(line)
        if depth != level or not match:
            index += 1
            continue
        key = match.group("key")
        if key[0] in "\"'":
            key = key[1:-1]
        inline, comment = _split_comment(match.group("rest") or "")
        end = _end(lines, index, depth, may_list=not inline)
        node = Node(parent + (key,), depth, _lead(lines, index, depth),
                    index, end, inline, comment)
        nodes[node.path] = node
        if not inline and end > index + 1:
            sub = _parse(lines, index + 1, end, node.path, nodes)
            if sub is None:
                node.kind = "list"
            elif sub:
                node.kind = "map"
                node.children = sub
        children.append(node)
        index = end
    return children


def outline(text):
    """`{path: Node}` for every key outside a list, parents first."""
    nodes = {}
    roots = _parse(text.splitlines(), 0, len(text.splitlines()), (), nodes)
    nodes[()] = Node((), -2, 0, -1, len(text.splitlines()), "", kind="map",
                     children=roots or [])
    return nodes


# ---------------------------------------------------------------------------
#  Values
# ---------------------------------------------------------------------------

def dotted(path):
    return ".".join(path)


def load(text):
    data = yaml.safe_load(text) if text.strip() else {}
    return data if isinstance(data, dict) else {}


def lookup(data, path):
    """(`yes`, value), (`no`, None), or (`blocked`, None).

    `blocked` means a parent is set to something that is not a mapping, so
    this key cannot be added under it.
    """
    node = data
    for depth, key in enumerate(path):
        if node is None:
            return "no", None
        if not isinstance(node, dict):
            return "blocked", None
        if key not in node:
            return ("no", None)
        node = node[key]
        if depth < len(path) - 1 and node is not None and not isinstance(node, dict):
            return "blocked", None
    return "yes", node


def leaves(data, prefix=()):
    """`{path: value}` for every setting, not descending into lists."""
    out = {}
    for key, value in (data or {}).items():
        path = prefix + (str(key),)
        if not prefix and key in USER_DATA:
            continue
        if isinstance(value, dict) and value:
            out.update(leaves(value, path))
        else:
            out[path] = value
    return out


def has_placeholder(value):
    if isinstance(value, str):
        return bool(_PLACEHOLDER.search(value))
    if isinstance(value, dict):
        return any(has_placeholder(v) for v in value.values())
    if isinstance(value, list):
        return any(has_placeholder(v) for v in value)
    return False


def is_secret(path):
    return bool(path) and path[-1] in SECRET_KEYS


def shown(value, path=()):
    """A value as the user would type it. Secrets are hidden."""
    if is_secret(path) and isinstance(value, str) and value \
            and not value.startswith("${ENV:") and not has_placeholder(value):
        return "(hidden)"
    text = value_text(value)
    if isinstance(value, (list, dict)) and len(text) > 80:
        return f"a list of {len(value)} entries" if isinstance(value, list) \
            else f"a mapping of {len(value)} keys"
    return text


def value_text(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    text = yaml.safe_dump(value, default_flow_style=True, width=10 ** 6,
                          allow_unicode=True, sort_keys=False)
    text = text.strip()
    if text.endswith("\n..."):
        text = text[:-4].strip()
    if text.endswith("..."):
        text = text[:-3].strip()
    return text


def help_lines(template_text, path, limit=4):
    """The template's comment for a setting, without rules or blank lines."""
    nodes = outline(template_text)
    node = nodes.get(tuple(path))
    if node is None:
        return []
    lines = template_text.splitlines()
    out = []
    for raw in lines[node.lead:node.line]:
        body = raw.strip().lstrip("#").strip()
        if not body or _RULE.match(body):
            continue
        titled = _SECTION.sub("", body)
        if titled != body and titled[-1:] not in ".!?:":
            titled += "."
        body = titled
        out.append(body)
    if node.comment:
        out.append(node.comment.lstrip("#").strip())
    return out[:limit]


def first_sentence(template_text, path, count=1):
    """The opening sentences of a setting's comment, or an empty string."""
    text = " ".join(help_lines(template_text, path, limit=8))
    found = re.findall(r".+?[.!?](?=\s|$)", text)
    if found:
        return " ".join(part.strip() for part in found[:count])
    return text if len(text) <= 100 else text[:97].rstrip() + "..."


# ---------------------------------------------------------------------------
#  Editing the file
# ---------------------------------------------------------------------------

def _shift(lines, delta):
    out = []
    for line in lines:
        if not line.strip():
            out.append("")
        elif delta >= 0:
            out.append(" " * delta + line)
        else:
            out.append(line[min(-delta, _indent(line)):])
    return out


def _join(lines):
    return "\n".join(lines).rstrip("\n") + "\n"


def insert_from_template(text, template_text, path):
    """Copy one key, with its comment, from the template. None when it cannot."""
    path = tuple(path)
    tnodes = outline(template_text)
    tnode = tnodes.get(path)
    tparent = tnodes.get(path[:-1])
    if tnode is None or tparent is None:
        return None
    nodes = outline(text)
    parent = nodes.get(path[:-1])
    if parent is None or parent.inline:
        return None
    lines = text.splitlines()
    names = [child.path[-1] for child in tparent.children]
    position = names.index(path[-1])
    before = next((nodes[path[:-1] + (n,)] for n in reversed(names[:position])
                   if path[:-1] + (n,) in nodes), None)
    after = next((nodes[path[:-1] + (n,)] for n in names[position + 1:]
                  if path[:-1] + (n,) in nodes), None)
    if before is not None:
        at, indent = before.end, before.indent
    elif after is not None:
        at, indent = after.lead, after.indent
    elif path[:-1]:
        at = parent.end
        if parent.children:
            indent = parent.children[0].indent
        else:
            indent = parent.indent + (tnode.indent - tparent.indent)
    else:
        at = len(lines)
        while at > 0 and not lines[at - 1].strip():
            at -= 1
        indent = 0
    template_lines = template_text.splitlines()
    block = _shift(template_lines[tnode.lead:tnode.end], indent - tnode.indent)
    if not path[:-1]:
        if at > 0 and lines[at - 1].strip():
            block = [""] + block
        if at < len(lines) and lines[at].strip():
            block = block + [""]
    updated = _join(lines[:at] + block + lines[at:])
    template_value = lookup(load(template_text), path)[1]
    try:
        state, value = lookup(load(updated), path)
    except yaml.YAMLError:
        return None
    if state != "yes" or value != template_value:
        return None
    return updated


def fill_missing(text, template_text):
    """Add every setting the template has and `text` lacks.

    Returns (text, added, needs_details, by_hand). A block that holds a
    placeholder such as <YOUR_TENANT_ID> is not added: it needs the user's
    own details first. `by_hand` lists keys under a value written on one
    line, which a line edit cannot reach.
    """
    template = load(template_text)
    added, needs, by_hand = [], [], []
    data = load(text)
    for path in outline(template_text):
        if not path or path[0] in USER_DATA:
            continue
        if any(path[:n] in added or path[:n] in needs or path[:n] in by_hand
               for n in range(1, len(path))):
            continue
        state, _value = lookup(data, path)
        if state != "no":
            continue
        value = lookup(template, path)[1]
        if has_placeholder(value):
            needs.append(path)
            continue
        updated = insert_from_template(text, template_text, path)
        if updated is None:
            by_hand.append(path)
            continue
        text = updated
        data = load(text)
        added.append(path)
    return text, added, needs, by_hand


def newly_present(before, after, template_text):
    """Template keys `after` has and `before` lacked, outermost first."""
    old, new = load(before), load(after)
    found = []
    for path in outline(template_text):
        if not path or path[0] in USER_DATA:
            continue
        if any(path[:n] in found for n in range(1, len(path))):
            continue
        if lookup(old, path)[0] == "no" and lookup(new, path)[0] == "yes":
            found.append(path)
    return found


def set_value(text, path, value, template_text=None):
    """Replace the value at `path`. None when that key is not on its own line.

    When `value` is the template's value, the template's lines are copied so
    a list keeps its layout and comments.
    """
    path = tuple(path)
    nodes = outline(text)
    node = nodes.get(path)
    if node is None:
        return None
    lines = text.splitlines()
    new_lines = None
    if template_text is not None:
        tnode = outline(template_text).get(path)
        if tnode is not None and lookup(load(template_text), path)[1] == value:
            source = template_text.splitlines()[tnode.line:tnode.end]
            new_lines = _shift(source, node.indent - tnode.indent)
    if new_lines is None:
        key = lines[node.line].strip().split(":", 1)[0]
        comment = f"  {node.comment}" if node.comment else ""
        new_lines = [f"{' ' * node.indent}{key}: {value_text(value)}{comment}"]
    return _join(lines[:node.line] + new_lines + lines[node.end:])


def add_key(text, path, value):
    """Add `key: value` after the last key of its parent. None when it cannot."""
    path = tuple(path)
    nodes = outline(text)
    parent = nodes.get(path[:-1])
    if parent is None or parent.inline or parent.kind == "list":
        return None
    lines = text.splitlines()
    if parent.children:
        indent, at = parent.children[0].indent, parent.children[-1].end
    else:
        indent, at = parent.indent + 2, parent.end
    line = f"{' ' * indent}{path[-1]}: {value_text(value)}"
    updated = _join(lines[:at] + [line] + lines[at:])
    if lookup(load(updated), path) != ("yes", value):
        return None
    return updated


def remove_key(text, path):
    """Cut one key and its value. None when it is not on its own line."""
    node = outline(text).get(tuple(path))
    if node is None:
        return None
    lines = text.splitlines()
    return _join(lines[:node.line] + lines[node.end:])


def rename_key(text, old, new, template_text):
    """Move a value from an old name to the new one. None when it cannot."""
    old, new = tuple(old), tuple(new)
    state, value = lookup(load(text), old)
    if state != "yes":
        return None
    have, current = lookup(load(text), new)
    inserted = False
    if have == "no":
        depth = next(n for n in range(1, len(new) + 1)
                     if lookup(load(text), new[:n])[0] == "no")
        grown = insert_from_template(text, template_text, new[:depth])
        if grown is None and depth == len(new):
            grown = add_key(text, new, value)
        if grown is None:
            return None
        text = grown
        inserted = True
        have, current = lookup(load(text), new)
    if have != "yes":
        return None
    if inserted or current in (None, "") or has_placeholder(current):
        text = set_value(text, new, value)
        if text is None:
            return None
    return remove_key(text, old)


# ---------------------------------------------------------------------------
#  The review record
# ---------------------------------------------------------------------------

def record_path(config_path):
    folder, name = os.path.split(os.path.abspath(config_path))
    stem = os.path.splitext(name)[0]
    return os.path.join(folder, f"{stem}.reviewed.json")


def read_record(config_path):
    """The saved record, or None when this config has none yet."""
    path = record_path(config_path)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("defaults"), dict):
        return None
    data.setdefault("kept", [])
    return data


def write_record(config_path, record):
    path = record_path(config_path)
    body = {
        "about": "The pm-tools defaults this config was last reviewed "
                 "against. pm update and pm setup --review read it. "
                 "Delete it to review every setting again.",
        "defaults": record.get("defaults", {}),
        "kept": sorted(set(record.get("kept", []))),
    }
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(body, fh, indent=2, sort_keys=True, default=str)
        fh.write("\n")
    os.replace(tmp, path)


def full_record(template_text, kept=()):
    """A record that says every shipped default has been seen."""
    defaults = {dotted(p): v for p, v in leaves(load(template_text)).items()}
    return {"defaults": defaults, "kept": list(kept)}


def assumed_record(text, template_text):
    """The record a config had before records existed.

    A setting the file has counts as seen at today's default, unless its
    value is a default an earlier release shipped. A setting the file lacks
    is new to this user.
    """
    data = load(text)
    defaults = {}
    for path, value in leaves(load(template_text)).items():
        state, mine = lookup(data, path)
        if state != "yes":
            continue
        earlier = EARLIER_DEFAULTS.get(dotted(path)) or []
        defaults[dotted(path)] = mine if mine in earlier else value
    return {"defaults": defaults, "kept": []}


# ---------------------------------------------------------------------------
#  What to tell the user
# ---------------------------------------------------------------------------

def _mentioned(template_text, key):
    return bool(re.search(rf"(^|[\s#{{,]){re.escape(key)}\s*:", template_text, re.M))


def compare(text, template_text, record):
    """New, changed, renamed, and unknown settings. Nothing is edited here."""
    report = Report()
    data = load(text)
    template = load(template_text)
    tleaves = leaves(template)
    seen = record.get("defaults", {})
    kept = set(record.get("kept", []))
    for path, value in tleaves.items():
        state, mine = lookup(data, path)
        if state == "blocked":
            continue
        name = dotted(path)
        if name not in seen:
            if state == "yes" or not has_placeholder(value):
                report.new.append(path)
            continue
        earlier = seen[name]
        if earlier == value or has_placeholder(value) or state != "yes":
            continue
        if mine == value:
            continue
        report.changed.append({
            "path": path, "earlier": earlier, "default": value,
            "current": mine, "yours": mine != earlier,
        })
    for path, _value in leaves(data).items():
        if path[0] in FREE_FORM or dotted(path) in kept:
            continue
        if any(path[:n] in tleaves for n in range(1, len(path) + 1)):
            continue
        if dotted(path) in RENAMED:
            report.renamed.append((dotted(path), RENAMED[dotted(path)]))
            continue
        if not _mentioned(template_text, path[-1]):
            report.unknown.append(path)
    return report


def unseen(path, template_text, record):
    """True when a template key, or any setting under it, is not in the record."""
    value = lookup(load(template_text), path)[1]
    names = leaves(value, tuple(path)) if isinstance(value, dict) and value \
        else {tuple(path): value}
    seen = record.get("defaults", {})
    return any(dotted(p) not in seen for p in names)


def pending(report):
    """How many items `pm setup --review` would ask about."""
    return len(report.new) + len(report.changed) + len(report.renamed) \
        + len(report.unknown) + len(report.needs_details)


def summary(report, template_text, data=None):
    """Markdown for the screen. `data` is the file after the update."""
    data = data if data is not None else {}
    template = load(template_text)
    out = []

    def described(path):
        text = f"`{dotted(path)}`"
        state, value = lookup(data, path)
        if state == "yes" and not isinstance(value, dict):
            text += f" = {shown(value, path)}"
        elif state == "yes":
            count = len(leaves(value, path))
            text += f" ({count} setting{'s' if count != 1 else ''})"
        note = first_sentence(template_text, path)
        if note:
            text += f": {note}"
        return text

    new = set(report.new)
    if report.added:
        count = len(report.added)
        out.append(f"Added {count} setting{'s' if count != 1 else ''} "
                   "with the shipped default:")
        for path in report.added:
            fresh = any(p[:len(path)] == path for p in new)
            out.append(f"- {described(path)}" + ("" if fresh else " (was missing)"))
        out.append("")
    if report.changed:
        out.append("Defaults that changed since your last review:")
        for item in report.changed:
            path = item["path"]
            line = (f"- `{dotted(path)}`: was {shown(item['earlier'], path)}, "
                    f"now {shown(item['default'], path)}.")
            if item["yours"]:
                line += f" This file has your own value, {shown(item['current'], path)}, and keeps it."
            else:
                line += " This file still has the old default."
            out.append(line)
        out.append("")
    if report.needs_details:
        out.append("Not added, because they need your own details:")
        for path in report.needs_details:
            value = lookup(template, path)[1]
            count = len(leaves(value, path)) if isinstance(value, dict) else 1
            label = f" ({count} settings)" if count > 1 else ""
            out.append(f"- `{dotted(path)}`{label}")
        out.append("")
    if report.by_hand:
        out.append("Not added, because the value above them is written on one line. "
                   "Copy them from the template:")
        for path in report.by_hand:
            value = lookup(template, path)[1]
            out.append(f"- `{dotted(path)}` = {value_text(value)}")
        out.append("")
    if report.renamed:
        out.append("Old names that still work:")
        for old, new_name in report.renamed:
            out.append(f"- `{old}` is now `{new_name}`.")
        out.append("")
    if report.unknown:
        out.append("Settings this version does not read:")
        for path in report.unknown:
            why = RETIRED.get(dotted(path))
            out.append(f"- `{dotted(path)}`" + (f": {why}." if why else ""))
        out.append("")
    return "\n".join(out)
