"""`pm update`, config migrations, and first-install init."""

import os
import sys
import tempfile
import textwrap
import unittest
from argparse import Namespace
from io import StringIO
from unittest.mock import patch

from commands import init, update
from core import migrations
from core.migrations import (apply_migrations, insert_missing_block,
                             read_version, set_version)


LIVE = textwrap.dedent("""\
    # keep this comment
    config_version: 1
    jira:
      base_url: "https://example.atlassian.net"
      email: "pm@example.com"
      api_token: "secret-token"
      project: "APS"
    workstreams:
      - name: "Secure Data Exchange"
        abbrev: "SDX"
        components: ["Secure Data Exchange"]
    """)


def _add_marker(text):
    text = insert_missing_block(text, "marker", ['  note: "added"'])
    return set_version(text, read_version(text) + 1)


def _drop_components(text):
    text = text.replace('components: ["Secure Data Exchange"]', "components: []")
    return set_version(text, read_version(text) + 1)


class MigrationTests(unittest.TestCase):
    def test_current_file_is_unchanged(self):
        self.assertEqual(apply_migrations(LIVE, [_pair()], 1), LIVE)

    def test_sample_migration_adds_only_the_new_key(self):
        updated = apply_migrations(LIVE, [_pair()], 2)
        self.assertEqual(read_version(updated), 2)
        self.assertIn('note: "added"', updated)
        self.assertIn("secret-token", updated)
        self.assertIn("Secure Data Exchange", updated)
        self.assertIn("# keep this comment", updated)
        self.assertNotIn("Integration Platform", updated)
        again = apply_migrations(updated, [_pair()], 2)
        self.assertEqual(again, updated)

    def test_missing_migration_does_not_pretend_to_finish(self):
        with self.assertRaises(migrations.MigrationError):
            apply_migrations(LIVE, [], 2)


def _pair():
    return (1, _add_marker)


class UpdateCommandTests(unittest.TestCase):
    def test_default_home_is_pm_tools(self):
        from core.paths import HOME, config_file, local_dir
        self.assertEqual(HOME, "~/.pm-tools")
        self.assertEqual(config_file(), "~/.pm-tools/config.yaml")
        with tempfile.TemporaryDirectory() as folder:
            home = os.path.join(folder, "home")
            os.makedirs(home)
            env = {k: v for k, v in os.environ.items() if k != "PM_CONFIG"}
            env["HOME"] = home
            env["USERPROFILE"] = home
            out = StringIO()
            with patch.dict(os.environ, env, clear=True), patch("sys.stdout", out):
                self.assertEqual(local_dir(None), os.path.join(home, ".pm-tools"))
                init.run(Namespace(path=None, force=False))
            dest = os.path.join(home, ".pm-tools", "config.yaml")
            self.assertTrue(os.path.isfile(dest))
            self.assertFalse(os.path.exists(os.path.join(home, ".pm")))
            with open(dest, encoding="utf-8") as fh:
                text = fh.read()
            self.assertIn("~/.pm-tools/cache", text)
            self.assertIn("~/.pm-tools/out", text)
            self.assertIn("~/.pm-tools/today.json", text)
            self.assertNotIn("~/.pm/", text.replace("~/.pm-tools", ""))
            with patch.dict(os.environ, env, clear=True):
                self.assertEqual(update.user_config_path(), os.path.abspath(dest))

    def test_init_writes_the_template_version_and_will_not_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            dest = os.path.join(folder, "config.yaml")
            out = StringIO()
            with patch("sys.stdout", out):
                init.run(Namespace(path=dest, force=False))
            with open(dest, encoding="utf-8") as fh:
                first = fh.read()
            self.assertEqual(read_version(first), migrations.template_version())
            self.assertIn("config_version:", first)
            with patch("sys.stdout", out):
                init.run(Namespace(path=dest, force=False))
            with open(dest, encoding="utf-8") as fh:
                second = fh.read()
            self.assertEqual(first, second)
            self.assertIn("pm update", out.getvalue())

    def test_update_leaves_a_current_config_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "config.yaml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(LIVE)
            with open(path, "rb") as fh:
                before = fh.read()
            out = StringIO()
            with patch("sys.stdout", out):
                update.upgrade_config(path, migrations=[], target=1)
            with open(path, "rb") as fh:
                self.assertEqual(fh.read(), before)
            self.assertIn(b"secret-token", before)
            self.assertIn("current", out.getvalue())
            self.assertNotIn("secret-token", out.getvalue())

    def test_dry_run_redacts_the_token_and_does_not_write(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "config.yaml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(LIVE)
            with open(path, encoding="utf-8") as fh:
                before = fh.read()
            out = StringIO()
            with patch("sys.stdout", out):
                update.upgrade_config(path, dry_run=True, migrations=[_pair()],
                                       target=2)
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), before)
            shown = out.getvalue()
            self.assertNotIn("secret-token", shown)
            self.assertIn("marker", shown)
            self.assertIn("<redacted>", update.redact('  api_token: "secret-token"\n'))

    def test_invalid_migration_is_not_written(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "config.yaml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(LIVE)
            with open(path, encoding="utf-8") as fh:
                before = fh.read()
            with self.assertRaises(SystemExit):
                update.upgrade_config(path, migrations=[(1, _drop_components)],
                                       target=2)
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), before)

    def test_refuses_the_bundled_template(self):
        with self.assertRaises(SystemExit) as caught:
            update.user_config_path(migrations.bundled_template_path())
        self.assertIn("Refusing", str(caught.exception.code))

    def test_help_lists_update_and_both_scripts_exist(self):
        import subprocess
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        proc = subprocess.run(
            [sys.executable, os.path.join(root, "pm.py"), "--help"],
            capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("update", proc.stdout)
        self.assertIn("coverage", proc.stdout)
        self.assertIn("release-notes", proc.stdout)
        self.assertIn("usage: pm", proc.stdout)
        today = subprocess.run(
            [sys.executable, os.path.join(root, "pm.py"), "today", "--help"],
            capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertIn("full name", today.stdout)
        review = subprocess.run(
            [sys.executable, os.path.join(root, "pm.py"), "review", "--help"],
            capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertIn("--apply", review.stdout)
        import pm
        saved = sys.argv[:]
        try:
            sys.argv = ["pm-tools", "--help"]
            self.assertEqual(pm._prog_name(), "pm-tools")
        finally:
            sys.argv = saved
        with open(os.path.join(root, "pyproject.toml"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn('name = "pm-tools"', text)
        self.assertIn('pm-tools = "pm:main"', text)


class RestartTests(unittest.TestCase):
    def test_a_code_install_migrates_config_in_a_new_process(self):
        args = Namespace(code_only=False, config_only=False, dry_run=False,
                         config="/tmp/pm-config.yaml")
        completed = Namespace(returncode=0)
        with patch.object(update, "upgrade_code", return_value="replaced"), \
                patch.object(update, "upgrade_config") as migrate, \
                patch.object(update.subprocess, "run", return_value=completed) as run, \
                patch.object(update.sys, "argv", ["pm", "update"]), \
                patch.object(update.shutil, "which", return_value="/usr/bin/pm"), \
                patch.object(update.sys, "exit", side_effect=SystemExit) as stop:
            with self.assertRaises(SystemExit):
                update.run(args)
        migrate.assert_not_called()
        command = run.call_args.args[0]
        self.assertEqual(
            command,
            ["/usr/bin/pm", "update", "--config-only",
             "--config", "/tmp/pm-config.yaml"])
        stop.assert_called_with(0)

    def test_dry_run_does_not_migrate_with_the_old_code(self):
        args = Namespace(code_only=False, config_only=False, dry_run=True,
                         config=None)
        with patch.object(update, "upgrade_code", return_value="preview"), \
                patch.object(update, "upgrade_config") as migrate:
            update.run(args)
        migrate.assert_not_called()

    def test_config_only_uses_the_loaded_migrations(self):
        args = Namespace(code_only=False, config_only=True, dry_run=False,
                         config=None)
        with patch.object(update, "upgrade_code") as code, \
                patch.object(update, "user_config_path", return_value="/tmp/x"), \
                patch.object(update, "upgrade_config") as migrate:
            update.run(args)
        code.assert_not_called()
        migrate.assert_called_once()


class GitUpgradeTests(unittest.TestCase):
    def test_git_spec_adds_the_git_prefix(self):
        self.assertEqual(
            update.git_spec("https://github.com/dstainton/pm-tools.git"),
            "git+https://github.com/dstainton/pm-tools.git")
        self.assertEqual(update.git_spec(""), update.GIT_SPEC)
        self.assertEqual(
            update.git_spec("git+https://github.com/dstainton/pm-tools.git"),
            "git+https://github.com/dstainton/pm-tools.git")

    def test_pipx_reinstalls_from_git_instead_of_upgrade(self):
        import json

        class FakeDist:
            def locate_file(self, name):
                return "/home/user/.local/pipx/venvs/pm-tools/"

            def read_text(self, name):
                if name == "direct_url.json":
                    return json.dumps({
                        "url": "https://github.com/dstainton/pm-tools.git",
                        "vcs_info": {"vcs": "git", "commit_id": "old"},
                    })
                return None

        with patch("importlib.metadata.distribution", return_value=FakeDist()), \
                patch.object(update.sys, "prefix",
                             "/home/user/.local/pipx/venvs/pm-tools"):
            info = update.classify_install()
        self.assertEqual(info["kind"], "pipx")
        self.assertEqual(
            info["command"],
            ["pipx", "install", "--force",
             "git+https://github.com/dstainton/pm-tools.git"])
