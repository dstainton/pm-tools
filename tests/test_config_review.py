"""`pm update` fills in every shipped setting; `pm setup --review` walks the changes."""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from argparse import Namespace
from io import StringIO
from unittest.mock import patch

import yaml

from commands import init, setup, setup_review, update
from core import config as config_core
from core import config_template as ct
from core.migrations import bundled_template_path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _template():
    with open(bundled_template_path(), encoding="utf-8") as fh:
        return fh.read()


def _filled_template():
    return (_template()
            .replace("<YOUR_ORG>", "acme")
            .replace("<YOUR_LOGIN_EMAIL>", "pm@acme.com")
            .replace("<YOUR_JIRA_API_TOKEN>", "secret-token"))


def _without(text, *snippets):
    for snippet in snippets:
        assert snippet in text, snippet
        text = text.replace(snippet, "", 1)
    return text


WORK = '  # The detailed report with people\'s names left out.\n  work:\n    name: "Team"\n'
ESTIMATE = "  # Which issue types need that estimate.\n  estimate_types: [story]\n"

MINIMAL = textwrap.dedent("""\
    # my own notes
    config_version: 7
    jira:
      base_url: "https://acme.atlassian.net"
      email: "pm@acme.com"
      api_token: "secret-token"
      project: "APS"
    workstreams:
      - name: "Secure Data Exchange"
        abbrev: "SDX"
        components: ["Secure Data Exchange"]
    """)


class Folder:
    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.path = os.path.join(self.dir, "config.yaml")
        return self

    def __exit__(self, *exc):
        self._tmp.cleanup()

    def write(self, text):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def read(self):
        with open(self.path, encoding="utf-8") as fh:
            return fh.read()

    def record(self):
        with open(ct.record_path(self.path), encoding="utf-8") as fh:
            return json.load(fh)


def _update(path, **kw):
    out = StringIO()
    with patch("sys.stdout", out), patch.dict(os.environ, {"NO_COLOR": "1"}):
        update.upgrade_config(path, **kw)
    return out.getvalue()


class FillTests(unittest.TestCase):
    def test_a_key_added_without_a_version_bump_is_filled_in(self):
        with Folder() as f:
            f.write(_without(_filled_template(), WORK, ESTIMATE))
            shown = _update(f.path)
            text = f.read()
            self.assertIn(WORK, text)
            self.assertIn(ESTIMATE, text)
            self.assertIn("secret-token", text)
            self.assertIn("audiences.work", shown)
            self.assertIn("lint.estimate_types", shown)
            self.assertIn("pm setup --review", shown)
            self.assertNotIn("secret-token", shown)
            self.assertEqual(text, _filled_template())
            again = _update(f.path)
            self.assertEqual(f.read(), text)
            self.assertIn("current", again)

    def test_a_minimal_config_gets_every_setting_but_not_blocks_needing_details(self):
        with Folder() as f:
            f.write(MINIMAL)
            shown = _update(f.path)
            data = yaml.safe_load(f.read())
            config_core.validate(data)
            self.assertTrue(f.read().startswith("# my own notes\n"))
            template = ct.load(_template())
            for path in ct.leaves(template):
                if path[0] in ("sharepoint", "confluence"):
                    continue
                self.assertEqual(ct.lookup(data, path)[0], "yes", ct.dotted(path))
            self.assertNotIn("sharepoint", data)
            self.assertNotIn("confluence", data)
            self.assertNotIn("products", data)
            self.assertEqual([w["abbrev"] for w in data["workstreams"]], ["SDX"])
            self.assertEqual(data["jira"]["api_token"], "secret-token")
            self.assertIn("need your own details", shown)
            self.assertIn("`sharepoint`".strip("`"), shown)

    def test_dry_run_lists_what_it_would_add_and_writes_nothing(self):
        with Folder() as f:
            f.write(_without(_filled_template(), WORK))
            shown = _update(f.path, dry_run=True)
            self.assertNotIn(WORK, f.read())
            self.assertIn("+  work:", shown)
            self.assertIn("Would add", shown)
            self.assertFalse(os.path.exists(ct.record_path(f.path)))

    def test_insertion_follows_the_file_s_own_indent(self):
        text = textwrap.dedent("""\
            config_version: 7
            jira:
                base_url: "https://acme.atlassian.net"
                email: "pm@acme.com"
                api_token: "t"
                project: "APS"
            lint:
                stale_days: 30
            workstreams:
              - name: "A"
                abbrev: "A"
                components: ["A"]
            """)
        filled, added, _needs, _hand = ct.fill_missing(text, _template())
        data = yaml.safe_load(filled)
        self.assertEqual(data["lint"]["stale_days"], 30)
        self.assertEqual(data["lint"]["estimate_types"], ["story"])
        self.assertIn("    estimate_types: [story]", filled)
        self.assertIn(("lint", "estimate_types"), added)

    def test_a_key_under_a_one_line_value_is_listed_not_forced(self):
        template = "a:\n  b:\n    c: 1\n    d: 2\n"
        filled, added, _needs, hand = ct.fill_missing("a:\n  b: {c: 1}\n", template)
        self.assertEqual(filled, "a:\n  b: {c: 1}\n")
        self.assertEqual(hand, [("a", "b", "d")])
        self.assertEqual(added, [])


class ReportTests(unittest.TestCase):
    def test_an_old_default_is_reported_and_a_chosen_value_is_not(self):
        with Folder() as f:
            f.write(_filled_template().replace('name: "qwen3:4b"', 'name: "qwen-local"'))
            shown = _update(f.path)
            self.assertIn("model.name", shown)
            self.assertIn("still has the old default", shown)
            self.assertIn('name: "qwen-local"', f.read())
        with Folder() as f:
            f.write(_filled_template().replace('name: "qwen3:4b"', 'name: "llama3.1:8b"'))
            shown = _update(f.path)
            self.assertNotIn("model.name", shown)

    def test_the_record_tells_a_changed_default_from_a_chosen_value(self):
        with Folder() as f:
            f.write(_filled_template().replace('name: "qwen3:4b"', 'name: "mine"'))
            record = ct.full_record(_template())
            record["defaults"]["model.name"] = "older"
            ct.write_record(f.path, record)
            shown = _update(f.path)
            self.assertIn('was "older", now "qwen3:4b"', shown)
            self.assertIn('your own value, "mine"', shown)

    def test_old_names_and_retired_settings_are_listed(self):
        text = _filled_template().replace(
            "  # space: \"POSM Chapter\"", '  root_title: "APS Team"\n  # space: "POSM Chapter"'
        ).replace("  require_estimate: true\n",
                  "  require_estimate: true\n  vague_title_terms: [wip]\n")
        with Folder() as f:
            f.write(text)
            shown = _update(f.path)
            self.assertIn("`confluence.root_title` is now `confluence.team_page`".replace("`", ""),
                          shown)
            self.assertIn("lint.vague_title_terms", shown)
            self.assertIn("vague_title_alone", shown)

    def test_init_records_every_default_so_update_is_quiet(self):
        with Folder() as f:
            with patch("sys.stdout", StringIO()):
                init.run(Namespace(path=f.path, force=False))
            self.assertIn("model.name", f.record()["defaults"])
            shown = _update(f.path)
            self.assertIn("every setting this version ships", shown)

    def test_a_first_update_writes_the_record_it_assumed(self):
        with Folder() as f:
            f.write(_without(_filled_template(), WORK))
            _update(f.path)
            record = f.record()
            self.assertNotIn("audiences.work.name", record["defaults"])
            self.assertIn("audiences.pm.name", record["defaults"])


def _review(path, answers, every=False, secrets=()):
    replies = list(answers)
    hidden = list(secrets)
    prompts = []

    def ask(prompt):
        prompts.append(prompt)
        if not replies:
            raise AssertionError(f"unexpected prompt: {prompt}")
        return replies.pop(0)

    def secret(prompt):
        prompts.append(prompt)
        return hidden.pop(0) if hidden else ""

    out = StringIO()
    args = Namespace(all=every, plain=True)
    with patch.dict(os.environ, {"NO_COLOR": "1"}):
        setup_review.run(args, path, True, ask=ask, secret=secret, out=out)
    return out.getvalue(), prompts, replies


class ReviewTests(unittest.TestCase):
    def test_review_sets_a_new_value_takes_a_new_default_and_records_it(self):
        with Folder() as f:
            text = _without(_filled_template(), WORK).replace(
                'name: "qwen3:4b"', 'name: "qwen-local"')
            f.write(text)
            shown, prompts, left = _review(f.path, ["d", "Engineering"])
            self.assertEqual(left, [])
            data = yaml.safe_load(f.read())
            self.assertEqual(data["model"]["name"], "qwen3:4b")
            self.assertEqual(data["audiences"]["work"]["name"], "Engineering")
            self.assertIn("model.name", shown)
            self.assertIn("default changed", shown)
            self.assertIn("d takes", prompts[0])
            self.assertEqual(f.record()["defaults"]["audiences.work.name"], "Team")
            shown, _prompts, _left = _review(f.path, [])
            self.assertIn("Nothing to review", shown)

    def test_enter_keeps_everything_and_the_file_is_unchanged(self):
        with Folder() as f:
            f.write(_filled_template().replace('name: "qwen3:4b"', 'name: "qwen-local"'))
            before = f.read()
            shown, _prompts, _left = _review(f.path, [""])
            self.assertEqual(f.read(), before)
            self.assertIn("No change", shown)
            self.assertIn("Nothing to review", _review(f.path, [])[0])

    def test_a_value_that_fails_validation_is_asked_again(self):
        with Folder() as f:
            f.write(_without(_filled_template(),
                             "  by: component\n"))
            shown, prompts, left = _review(f.path, ["bogus", ""])
            self.assertEqual(left, [])
            self.assertIn("Not kept", shown)
            self.assertEqual(len(prompts), 2)
            self.assertEqual(yaml.safe_load(f.read())["membership"]["by"], "component")

    def test_typed_values_follow_the_default_s_type(self):
        self.assertIs(setup_review.parse_answer("no", True), False)
        self.assertEqual(setup_review.parse_answer("12", 8), 12)
        self.assertEqual(setup_review.parse_answer("Story, Bug", ["story"]), ["Story", "Bug"])
        self.assertEqual(setup_review.parse_answer("[a, b]", []), ["a", "b"])
        self.assertEqual(setup_review.parse_answer("yes", "text"), "yes")
        self.assertEqual(setup_review.parse_answer('"q"', "text"), "q")
        with self.assertRaises(ValueError):
            setup_review.parse_answer("many", 3)

    def test_q_saves_answers_so_far_and_leaves_the_rest_on_the_list(self):
        with Folder() as f:
            f.write(_without(_filled_template(), WORK, ESTIMATE))
            shown, _prompts, left = _review(f.path, ["[story, task]", "q"])
            self.assertEqual(left, [])
            self.assertIn("Stopped", shown)
            data = yaml.safe_load(f.read())
            self.assertEqual(data["lint"]["estimate_types"], ["story", "task"])
            self.assertEqual(data["audiences"]["work"]["name"], "Team")
            record = f.record()
            self.assertIn("lint.estimate_types", record["defaults"])
            self.assertNotIn("audiences.work.name", record["defaults"])
            shown, _prompts, _left = _review(f.path, [""])
            self.assertIn("audiences.work.name", shown)
            self.assertNotIn("lint.estimate_types", shown)

    def test_a_new_block_is_one_question(self):
        block = _template().split("comments:\n", 1)[1].split("\n\n", 1)[0]
        text = _filled_template().replace("comments:\n" + block + "\n", "")
        with Folder() as f:
            f.write(text)
            with patch("sys.stdout", StringIO()):
                update.upgrade_config(f.path)
            shown, prompts, _left = _review(f.path, [""])
            self.assertEqual(len(prompts), 1)
            self.assertIn("comments (6 settings)", shown)
            self.assertIn("Enter keeps these 6 defaults", prompts[0])
            shown, prompts, _left = _review(f.path, [])
            self.assertIn("Nothing to review", shown)

    def test_renames_move_the_value_and_retired_keys_can_go(self):
        text = _filled_template().replace(
            "  # space: \"POSM Chapter\"", '  root_title: "APS Team"\n  # space: "POSM Chapter"'
        ).replace("  require_estimate: true\n",
                  "  require_estimate: true\n  vague_title_terms: [wip]\n")
        with Folder() as f:
            f.write(text)
            _review(f.path, ["", "y"])
            data = yaml.safe_load(f.read())
            self.assertEqual(data["confluence"]["team_page"], "APS Team")
            self.assertNotIn("root_title", data["confluence"])
            self.assertNotIn("vague_title_terms", data["lint"])

    def test_a_kept_unknown_key_is_not_asked_again(self):
        text = _filled_template().replace(
            "  require_estimate: true\n", "  require_estimate: true\n  vague_title_terms: [wip]\n")
        with Folder() as f:
            f.write(text)
            _review(f.path, [""])
            self.assertIn("vague_title_terms", f.read())
            self.assertIn("Nothing to review", _review(f.path, [])[0])
            self.assertIn("every setting", _update(f.path))

    def test_a_block_needing_details_can_be_added_and_filled(self):
        start = _filled_template().index("sharepoint:\n")
        end = _filled_template().index("\n\n", start)
        text = _filled_template()[:start] + _filled_template()[end + 2:]
        with Folder() as f:
            f.write(text)
            shown, prompts, left = _review(
                f.path, ["y", "tenant-1", "client-1", "sites/team"], secrets=[""])
            self.assertEqual(left, [])
            data = yaml.safe_load(f.read())
            self.assertEqual(data["sharepoint"]["tenant_id"], "tenant-1")
            self.assertEqual(data["sharepoint"]["client_id"], "client-1")
            self.assertEqual(data["sharepoint"]["site_path"], "sites/team")
            self.assertIs(data["sharepoint"]["enabled"], False)
            self.assertIn("needs your details", shown)

    def test_all_steps_through_every_setting(self):
        with Folder() as f:
            f.write(_filled_template())
            before = f.read()
            count = len([p for p in ct.leaves(ct.load(_template()))])
            shown, prompts, _left = _review(f.path, [""] * count, every=True)
            self.assertGreater(len(prompts), 100)
            self.assertIn("(hidden)", shown)
            self.assertNotIn("secret-token", shown)
            self.assertEqual(f.read(), before)

    def test_without_a_terminal_it_lists_and_writes_nothing(self):
        with Folder() as f:
            f.write(_without(_filled_template(), WORK))
            before = f.read()
            proc = subprocess.run(
                [sys.executable, os.path.join(ROOT, "pm.py"), "setup", "--review",
                 "--path", f.path],
                capture_output=True, text=True, encoding="utf-8", timeout=60,
                stdin=subprocess.DEVNULL, env={**os.environ, "NO_COLOR": "1"})
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("audiences.work", proc.stdout)
            self.assertIn("will not prompt", proc.stdout)
            self.assertEqual(f.read(), before)

    def test_all_needs_review_and_review_refuses_the_template(self):
        with self.assertRaises(SystemExit):
            setup.run(Namespace(all=True, review=False, section=None, yes=True))
        with self.assertRaises(SystemExit) as caught:
            setup_review.run(Namespace(all=False), bundled_template_path(), False)
        self.assertIn("Refusing", str(caught.exception.code))


class OutlineTests(unittest.TestCase):
    def test_every_template_key_has_a_node_and_a_value_that_round_trips(self):
        template = _template()
        nodes = ct.outline(template)
        for path in ct.leaves(ct.load(template)):
            probe = path
            while probe and probe not in nodes:
                probe = probe[:-1]
            self.assertTrue(probe, ct.dotted(path))

    def test_set_value_keeps_the_inline_comment(self):
        text = "today:\n  max_moved: 8   # shown on screen\n"
        updated = ct.set_value(text, ("today", "max_moved"), 12)
        self.assertEqual(updated, "today:\n  max_moved: 12  # shown on screen\n")

    def test_a_hash_inside_quotes_is_not_a_comment(self):
        nodes = ct.outline('a:\n  b: "x # y"  # note\n')
        self.assertEqual(nodes[("a", "b")].inline, '"x # y"')
        self.assertEqual(nodes[("a", "b")].comment, "# note")

    def test_template_defaults_match_the_defaults_filled_in_memory(self):
        template = ct.load(_template())
        for section, defaults in config_core.SECTION_DEFAULTS.items():
            for key, value in defaults.items():
                self.assertEqual(template[section].get(key), value, f"{section}.{key}")


if __name__ == "__main__":
    unittest.main()
