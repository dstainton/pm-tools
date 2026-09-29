"""`pm setup --review` — step through the settings an update brought.

Asks about each new setting, each shipped default that changed since the
last review, each block that needs your details, each old name, and each
setting this version does not read. `--all` asks about every setting.
Enter keeps what the file has. Every answer is checked before it is kept,
and the file is written once, at the end.
"""

import getpass
import os
import sys

import yaml

from core import config as config_core
from core import config_template as ct
from core import terminal
from core.migrations import MIGRATIONS, bundled_template_path, template_version


class Stop(Exception):
    """The user typed q."""


def _problem(text):
    """Why `text` would not load, or None."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as err:
        return f"that is not valid YAML ({err})"
    if not isinstance(data, dict):
        return "the config would not be a mapping"
    try:
        config_core.validate(data)
    except SystemExit as err:
        return err.code if isinstance(err.code, str) else str(err)
    except Exception as err:                                   # noqa: BLE001
        return f"the config would not load ({err})"
    return None


def parse_answer(raw, default):
    """Turn typed text into a value shaped like the default."""
    raw = raw.strip()
    if isinstance(default, bool):
        low = raw.lower()
        if low in ("true", "yes", "y", "on"):
            return True
        if low in ("false", "no", "n", "off"):
            return False
        raise ValueError("Type true or false.")
    if isinstance(default, int):
        try:
            return int(raw)
        except ValueError:
            raise ValueError("Type a whole number.") from None
    if isinstance(default, float):
        try:
            return float(raw)
        except ValueError:
            raise ValueError("Type a number.") from None
    if isinstance(default, list):
        if raw.startswith("["):
            value = yaml.safe_load(raw)
            if not isinstance(value, list):
                raise ValueError("Type a list, such as [Story, Bug].")
            return value
        return [part.strip() for part in raw.split(",") if part.strip()]
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    if isinstance(default, str):
        return raw
    try:
        return yaml.safe_load(raw)
    except yaml.YAMLError:
        return raw


class Review:
    def __init__(self, path, text, template_text, record, args=None,
                 ask=None, secret=None, out=None):
        self.path = path
        self.original = text
        self.text = text
        self.template_text = template_text
        self.template = ct.load(template_text)
        self.record = record
        self.args = args
        self.ask = ask or (lambda prompt: input(prompt))
        self.secret = secret or (lambda prompt: getpass.getpass(prompt))
        self.out = out or sys.stdout
        self.caps = terminal.capabilities(args, self.out)
        self.baseline = _problem(text)
        self.reviewed = set()
        self.kept = set(record.get("kept", []))
        self.changes = 0

    # -- output -------------------------------------------------------------

    def say(self, line="", indent="  "):
        if not line:
            self.out.write("\n")
        else:
            self.out.write(terminal.wrap_line(line, self.caps, indent) + "\n")
        self.out.flush()

    def _help(self, path):
        text = ct.first_sentence(self.template_text, path, count=2)
        if not text and len(path) > 1:
            text = ct.first_sentence(self.template_text, path[:-1])
        if text:
            self.say(text)

    # -- edits --------------------------------------------------------------

    def _try(self, updated):
        """Keep `updated` when it loads as well as the file did. Else say why."""
        if updated is None:
            self.say("  That key is written on one line in your file, so "
                     "edit it there.")
            return False
        problem = _problem(updated)
        if problem and problem != self.baseline:
            self.say(f"  Not kept: {problem}")
            return False
        if updated != self.text:
            self.text = updated
            self.changes += 1
        return True

    def current(self, path):
        return ct.lookup(ct.load(self.text), path)

    # -- one item -----------------------------------------------------------

    def _read(self, prompt, path):
        reader = self.secret if ct.is_secret(path) else self.ask
        try:
            answer = reader(prompt)
        except EOFError:
            raise Stop() from None
        answer = (answer or "").strip()
        if answer.lower() == "q":
            raise Stop()
        return answer

    def value_item(self, path, earlier=None):
        path = tuple(path)
        default = ct.lookup(self.template, path)[1]
        self._help(path)
        state, mine = self.current(path)
        if earlier is not None:
            self.say(f"  The default was {ct.shown(earlier, path)}. "
                     f"It is now {ct.shown(default, path)}.")
        if state != "yes":
            self.say("  This file does not have it.")
        elif mine == default:
            self.say(f"  This file has {ct.shown(mine, path)}, the shipped default.")
        else:
            self.say(f"  This file has {ct.shown(mine, path)}.")
        offer_default = state == "yes" and mine != default
        while True:
            choices = "Enter keeps it"
            if offer_default:
                choices += f", d takes {ct.shown(default, path)}"
            answer = self._read(f"  {choices}, or type a value (q stops): ", path)
            if not answer:
                break
            if offer_default and answer.lower() == "d":
                if self._try(ct.set_value(self.text, path, default, self.template_text)):
                    break
                continue
            try:
                value = parse_answer(answer, default)
            except ValueError as err:
                self.say(f"  {err}")
                continue
            if self._try(ct.set_value(self.text, path, value, self.template_text)):
                break
        self.reviewed.add(ct.dotted(path))

    def block_item(self, path, names):
        """A new block of several settings: keep them all, or go through each."""
        self._help(path)
        data = ct.load(self.text)
        for name in names[:12]:
            self.say(f"`{ct.dotted(name)}` = {ct.shown(ct.lookup(data, name)[1], name)}",
                     indent="    ")
        if len(names) > 12:
            self.say(f"and {len(names) - 12} more", indent="    ")
        answer = self._read(f"  Enter keeps these {len(names)} defaults, e goes "
                            "through each one (q stops): ", ())
        if answer.lower() == "e":
            return [("new", name) for name in names]
        for name in names:
            self.reviewed.add(ct.dotted(name))
        return []

    def details_item(self, path):
        path = tuple(path)
        value = ct.lookup(self.template, path)[1]
        self._help(path)
        names = list(ct.leaves(value, path)) if isinstance(value, dict) else [path]
        self.say("  It is not in this file, and it needs your own details.")
        answer = self._read("  Add it from the template? [y/N] (q stops): ", path)
        added = answer.lower() in ("y", "yes") and self._try(
            ct.insert_from_template(self.text, self.template_text, path))
        for name in names:
            self.reviewed.add(ct.dotted(name))
        if not added:
            return []
        return [("new", name) for name in names
                if ct.has_placeholder(ct.lookup(self.template, name)[1])]

    def renamed_item(self, old, new):
        self.say(f"  pm reads this as `{new}` now. The old name still works.")
        answer = self._read(f"  Move the value to {new}? [Y/n] (q stops): ", ())
        if answer.lower() in ("", "y", "yes"):
            self._try(ct.rename_key(self.text, old.split("."), new.split("."),
                                    self.template_text))
        else:
            self.kept.add(old)

    def unknown_item(self, path):
        why = ct.RETIRED.get(ct.dotted(path))
        if why:
            self.say(f"Instead: {why}.")
        state, mine = self.current(path)
        if state == "yes":
            self.say(f"  This file has {ct.shown(mine, path)}. pm does not read it.")
        answer = self._read("  Remove it? [y/N] (q stops): ", path)
        if answer.lower() in ("y", "yes"):
            self._try(ct.remove_key(self.text, path))
        else:
            self.kept.add(ct.dotted(path))

    # -- the walk -----------------------------------------------------------

    def items(self, report, every=False):
        order = list(ct.leaves(self.template))
        by_path = {}
        new = set(report.new)
        groups = {}
        for path in report.new:
            top = path
            for depth in range(1, len(path)):
                value = ct.lookup(self.template, path[:depth])[1]
                if isinstance(value, dict) and all(
                        p in new for p in ct.leaves(value, path[:depth])):
                    top = path[:depth]
                    break
            groups.setdefault(top, []).append(path)
        for top, names in groups.items():
            if len(names) > 1:
                by_path[names[0]] = ("block", (top, names))
            else:
                by_path[names[0]] = ("new", names[0])
        for item in report.changed:
            by_path[item["path"]] = ("changed", item)
        if every:
            for path in order:
                if ct.lookup(ct.load(self.text), path)[0] == "yes":
                    by_path.setdefault(path, ("setting", path))
        queue = [by_path[p] for p in order if p in by_path]
        queue += [("details", p) for p in report.needs_details]
        queue += [("renamed", pair) for pair in report.renamed]
        queue += [("unknown", p) for p in report.unknown]
        return queue

    def walk(self, queue):
        labels = {"new": "new", "block": "new", "changed": "default changed",
                  "details": "needs your details", "renamed": "old name",
                  "unknown": "not read by this version", "setting": ""}
        index = 0
        total = len(queue)
        while index < len(queue):
            kind, item = queue[index]
            index += 1
            if kind == "renamed":
                name = item[0]
            elif kind == "block":
                name = f"{ct.dotted(item[0])} ({len(item[1])} settings)"
            else:
                name = ct.dotted(item["path"] if kind == "changed" else item)
            label = labels[kind]
            self.say("")
            self.say(f"**[{index}/{total}] {name}**" + (f" — {label}" if label else ""),
                     indent="")
            if kind == "block":
                more = self.block_item(*item)
                queue[index:index] = more
                total += len(more)
            elif kind in ("new", "setting"):
                self.value_item(item)
            elif kind == "changed":
                self.value_item(item["path"], earlier=item["earlier"])
            elif kind == "details":
                more = self.details_item(item)
                queue[index:index] = more
                total += len(more)
            elif kind == "renamed":
                self.renamed_item(*item)
            else:
                self.unknown_item(item)

    def new_record(self, finished):
        if finished:
            record = ct.full_record(self.template_text, kept=self.kept)
            for name, value in self.record.get("defaults", {}).items():
                if name not in record["defaults"]:
                    record["defaults"][name] = value
            return record
        defaults = dict(self.record.get("defaults", {}))
        seen = {ct.dotted(p): v for p, v in ct.leaves(self.template).items()}
        for name in self.reviewed:
            if name in seen:
                defaults[name] = seen[name]
        return {"defaults": defaults, "kept": sorted(self.kept)}


def _write(path, text):
    folder = os.path.dirname(path) or "."
    tmp = os.path.join(folder, f".{os.path.basename(path)}.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def run(args, path, interactive, ask=None, secret=None, out=None):
    from commands import update
    out = out or sys.stdout
    template_path = bundled_template_path()
    if os.path.abspath(path) == os.path.abspath(template_path):
        sys.exit(f"Refusing to edit {path}.\nThat file is part of the pm-tools "
                 "install. Pass --path with your own config.")
    if not os.path.exists(path):
        sys.exit(f"No config at {path}.\nCreate one with:  pm setup")
    with open(template_path, "r", encoding="utf-8") as fh:
        template_text = fh.read()
    with open(path, "r", encoding="utf-8") as fh:
        original = fh.read()
    record = ct.read_record(path) or ct.assumed_record(original, template_text)
    try:
        text, fill = update.bring_up_to_date(
            original, template_text, MIGRATIONS, template_version(template_path))
    except Exception as err:                                   # noqa: BLE001
        sys.exit(f"Could not bring {path} up to date: {err}\n"
                 "The file was not changed. Run:  pm update --config-only")
    report = update.review_report(text, template_text, record, fill)
    every = bool(getattr(args, "all", False))

    if not interactive:
        if report.empty():
            print("Nothing to review: the config has every setting this "
                  "version ships.", file=out)
            return
        terminal.show(ct.summary(report, template_text, ct.load(text)), args, out)
        print("stdin is not a terminal, so `pm setup --review` will not prompt. "
              "Nothing was written. Run it in a terminal.", file=out)
        return

    review = Review(path, text, template_text, record, args=args,
                    ask=ask, secret=secret, out=out)
    queue = review.items(report, every=every)
    if fill[0]:
        review.say(f"Added {len(fill[0])} missing setting"
                   f"{'s' if len(fill[0]) != 1 else ''} with the shipped default "
                   "first. Each one is in the list.")
    if not queue:
        review.say("Nothing to review: the config has every setting this version "
                   "ships, and no shipped default has changed since your last review.")
        review.say("Step through every setting:  pm setup --review --all")
    else:
        review.say(f"Reviewing {path}. Enter keeps what the file has.")
    finished = True
    try:
        review.walk(queue)
    except Stop:
        finished = False
        review.say("")
        review.say("Stopped. Your answers so far are saved; the rest stay on the list.")
    except KeyboardInterrupt:
        print("\nStopped. Nothing was written.", file=out)
        sys.exit(1)

    review.say("")
    problem = _problem(review.text)
    if problem and problem != _problem(original):
        sys.exit(f"Refusing to write: {problem}\nThe file was not changed.")
    if review.text != original:
        _write(path, review.text)
        parts = []
        if text != original:
            parts.append("the upgrade and missing settings")
        if review.changes:
            parts.append(f"{review.changes} change{'s' if review.changes != 1 else ''} "
                         "you made")
        review.say(f"Saved {path}: " + " and ".join(parts) + ".")
    else:
        review.say(f"No change to {path}.")
    ct.write_record(path, review.new_record(finished))
    review.say("Next: pm doctor")
