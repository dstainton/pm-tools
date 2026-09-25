"""Local-server discovery, recommendations, and optional installers."""

import os
import sys
import tempfile
import textwrap
import unittest
from argparse import Namespace
from io import StringIO
from unittest.mock import patch

import requests
import yaml

from commands import setup, update
from core import local_models, migrations, sources


SHIPPED = textwrap.dedent("""\
    config_version: 7
    model:
      endpoint: "http://127.0.0.1:8080/v1/chat/completions"
      name: "qwen-local"
      api_key: ""
    jira:
      base_url: "https://kept.atlassian.net"
      email: "pm@example.com"
    """)


def _ns(**kwargs):
    base = dict(
        path=None, site=None, email=None, token_env=None, token=None,
        project=None, model_endpoint=None, model_name=None,
        model_api_key=None, model_api_key_env=None, section=None,
        yes=False, open_browser=False)
    base.update(kwargs)
    return Namespace(**base)


class UrlTests(unittest.TestCase):
    def test_a_chat_url_is_rewritten_to_models(self):
        self.assertEqual(
            sources.models_url("http://127.0.0.1:8080/v1/chat/completions"),
            "http://127.0.0.1:8080/v1/models")
        self.assertEqual(
            sources.models_url("http://127.0.0.1:11434/v1"),
            "http://127.0.0.1:11434/v1/models")
        self.assertEqual(
            sources.models_url("http://127.0.0.1:13305/api/v1"),
            "http://127.0.0.1:13305/api/v1/models")

    def test_fetch_sends_a_bearer_token_when_one_is_set(self):
        class Resp:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"data": [{"id": "qwen3:8b"}]}

        with patch("core.sources.requests.get", return_value=Resp()) as get:
            ids = sources.fetch_model_ids(
                "http://127.0.0.1:8080/v1/chat/completions",
                api_key="secret", timeout=2)
        self.assertEqual(ids, ["qwen3:8b"])
        self.assertEqual(get.call_args.args[0], "http://127.0.0.1:8080/v1/models")
        self.assertEqual(
            get.call_args.kwargs["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(get.call_args.kwargs["timeout"], 2)

        with patch("core.sources.requests.get", return_value=Resp()) as get:
            sources.fetch_model_ids("http://127.0.0.1:11434/v1", api_key="")
        self.assertNotIn("Authorization", get.call_args.kwargs["headers"])


class RecommendTests(unittest.TestCase):
    def test_size_hint_matches_across_separators(self):
        chosen, note = local_models.recommend(
            ["qwen3:8b", "llama3.2"], local_models.DEFAULT_RECOMMENDATIONS, 16)
        self.assertEqual(chosen, "qwen3:8b")
        self.assertIn("8B", note)
        chosen, _note = local_models.recommend(
            ["Qwen/Qwen3-8B-GGUF", "other"],
            local_models.DEFAULT_RECOMMENDATIONS, 16)
        self.assertEqual(chosen, "Qwen/Qwen3-8B-GGUF")

    def test_an_alias_is_not_treated_as_a_size(self):
        chosen, note = local_models.recommend(
            ["qwen-local", "llama3.2"], local_models.DEFAULT_RECOMMENDATIONS, 16)
        self.assertIsNone(chosen)
        self.assertIn("None of the served", note)

    def test_a_larger_machine_prefers_the_larger_model(self):
        chosen, note = local_models.recommend(
            ["qwen3:8b", "Qwen/Qwen3-30B-A3B"],
            local_models.DEFAULT_RECOMMENDATIONS, 48)
        self.assertEqual(chosen, "Qwen/Qwen3-30B-A3B")
        self.assertIn("30B", note)

    def test_one_served_model_is_the_recommendation(self):
        chosen, _note = local_models.recommend(
            ["qwen-local"], local_models.DEFAULT_RECOMMENDATIONS, 16)
        self.assertEqual(chosen, "qwen-local")

    def test_unknown_memory_does_not_invent_a_size(self):
        chosen, note = local_models.recommend(
            ["qwen3:8b", "other"], local_models.DEFAULT_RECOMMENDATIONS, None)
        self.assertIsNone(chosen)
        self.assertIn("Could not read", note)
        chosen, note = local_models.recommend(["only"], [], None)
        self.assertEqual(chosen, "only")
        self.assertIn("Could not read", note)


class ProbeTests(unittest.TestCase):
    def test_failures_are_skipped_and_an_empty_list_counts(self):
        def fake(endpoint, api_key="", timeout=15):
            if "11434" in endpoint:
                if api_key != "secret":
                    raise requests.HTTPError("401")
                return ["qwen3:8b"]
            if "1234" in endpoint:
                return []
            raise requests.ConnectionError("down")

        endpoints = [
            {"name": "llama.cpp", "endpoint": "http://127.0.0.1:8080/v1"},
            {"name": "Ollama", "endpoint": "http://127.0.0.1:11434/v1",
             "api_key": "${ENV:LOCAL}"},
            {"name": "LM Studio", "endpoint": "http://127.0.0.1:1234/v1"},
        ]
        with patch("core.local_models.sources.fetch_model_ids", side_effect=fake), \
                patch.dict(os.environ, {"LOCAL": "secret"}):
            found = local_models.probe(endpoints, timeout=2)
        self.assertEqual([item["name"] for item in found], ["Ollama", "LM Studio"])
        self.assertEqual(found[0]["models"], ["qwen3:8b"])
        self.assertEqual(found[0]["api_key"], "${ENV:LOCAL}")
        self.assertEqual(found[1]["models"], [])


class InstallerTests(unittest.TestCase):
    def test_linux_ollama_uses_the_official_script(self):
        with patch("core.local_models.platform.system", return_value="Linux"):
            plan = local_models.installer("ollama")
        self.assertEqual(plan["display"], local_models.OLLAMA_INSTALL)
        self.assertIn("https://ollama.com/install.sh", plan["command"][-1])
        self.assertEqual(plan["docs"], "https://ollama.com/download")

    def test_linux_lemonade_uses_snap_when_it_is_installed(self):
        def which(name):
            return "/usr/bin/snap" if name == "snap" else None

        with patch("core.local_models.platform.system", return_value="Linux"), \
                patch("core.local_models.shutil.which", side_effect=which):
            plan = local_models.installer("lemonade")
        self.assertEqual(
            plan["command"], ["sudo", "snap", "install", "lemonade-server"])

    def test_linux_lemonade_without_snap_does_not_invent_a_command(self):
        with patch("core.local_models.platform.system", return_value="Linux"), \
                patch("core.local_models.shutil.which", return_value=None):
            plan = local_models.installer("lemonade")
        self.assertIsNone(plan["command"])
        self.assertIn("ppa:lemonade-team/stable", plan["display"])
        self.assertIn("lemonade-server.ai", plan["docs"])

    def test_a_missing_command_is_not_run(self):
        with patch("core.local_models.subprocess.run") as run:
            self.assertIsNone(local_models.run_install({"command": None}))
        run.assert_not_called()


class CatalogTests(unittest.TestCase):
    def test_the_template_matches_the_code_defaults(self):
        with open(migrations.bundled_template_path(), encoding="utf-8") as fh:
            data = yaml.safe_load(fh.read())
        self.assertEqual(data["config_version"], 7)
        self.assertEqual(data["model"]["api_key"], "")
        self.assertEqual(
            data["local_models"]["endpoints"], local_models.DEFAULT_ENDPOINTS)
        self.assertEqual(
            data["local_models"]["recommendations"],
            local_models.DEFAULT_RECOMMENDATIONS)

    def test_a_missing_block_uses_the_code_defaults(self):
        got = local_models.settings({})
        self.assertEqual(got["endpoints"], local_models.DEFAULT_ENDPOINTS)
        custom = {"local_models": {
            "endpoints": [{"name": "Mine", "endpoint": "http://x/v1"}],
            "recommendations": [],
        }}
        got = local_models.settings(custom)
        self.assertEqual(got["endpoints"][0]["name"], "Mine")
        self.assertEqual(got["recommendations"], local_models.DEFAULT_RECOMMENDATIONS)

    def test_version_6_gains_the_catalog_and_an_api_key(self):
        text = "config_version: 6\nmodel:\n  timeout: 600\njira:\n  project: APS\n"
        updated = migrations.apply_migrations(text, migrations.MIGRATIONS, 7)
        data = yaml.safe_load(updated)
        self.assertEqual(migrations.read_version(updated), 7)
        self.assertEqual(data["model"]["api_key"], "")
        self.assertEqual(data["model"]["timeout"], 600)
        self.assertEqual(
            data["local_models"]["endpoints"], local_models.DEFAULT_ENDPOINTS)
        self.assertEqual(
            data["local_models"]["recommendations"],
            local_models.DEFAULT_RECOMMENDATIONS)
        again = migrations.apply_migrations(updated, migrations.MIGRATIONS, 7)
        self.assertEqual(again, updated)

    def test_an_existing_catalog_and_key_are_not_replaced(self):
        text = textwrap.dedent("""\
            config_version: 6
            model:
              endpoint: "http://custom/v1/chat/completions"
              name: "mine"
              api_key: "keep-me"
            local_models:
              endpoints:
                - name: "Mine"
                  endpoint: "http://custom/v1"
            """)
        updated = migrations.to_version_7(text)
        self.assertEqual(updated.count("local_models:"), 1)
        self.assertEqual(updated.count('api_key: "keep-me"'), 1)
        self.assertIn("http://custom/v1", updated)
        self.assertNotIn("11434", updated)
        self.assertEqual(migrations.read_version(updated), 7)
        again = migrations.to_version_7(updated)
        self.assertEqual(again.count("local_models:"), 1)

    def test_api_key_is_redacted_in_an_update_preview(self):
        shown = update.redact('  api_key: "super-secret"\n  name: "qwen"\n')
        self.assertNotIn("super-secret", shown)
        self.assertIn("qwen", shown)
        self.assertIn("<redacted>", shown)


class SetupTests(unittest.TestCase):
    def _run(self, path, answers, probe_results, **kwargs):
        prompts = iter(answers)

        def ask(_prompt):
            return next(prompts)

        out = StringIO()
        install = patch("commands.setup.local_models.run_install", return_value=0)
        with patch("commands.setup._tty", return_value=True), \
                patch("commands.setup.local_models.probe", side_effect=probe_results), \
                patch("commands.setup.local_models.memory_gib", return_value=16), \
                patch("commands.setup._ask", side_effect=ask), \
                patch("commands.setup.webbrowser.open") as browser, \
                patch("sys.stdout", out), \
                install as run_install:
            setup.run(_ns(path=path, **kwargs))
        browser.assert_not_called()
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        return text, out.getvalue(), run_install

    def test_a_choice_writes_the_endpoint_name_and_key(self):
        found = [{
            "name": "Ollama",
            "endpoint": "http://127.0.0.1:11434/v1",
            "api_key": "",
            "models": ["qwen3:8b", "llama3.2"],
        }]
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "config.yaml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(SHIPPED)
            text, shown, run_install = self._run(
                path, ["1", "1", "super-secret"], [found], section="model")
        run_install.assert_not_called()
        self.assertIn(
            'endpoint: "http://127.0.0.1:11434/v1/chat/completions"', text)
        self.assertIn('name: "qwen3:8b"', text)
        self.assertIn('api_key: "super-secret"', text)
        self.assertNotIn("super-secret", shown)
        self.assertIn("recommended", shown)
        self.assertIn("https://kept.atlassian.net", text)

    def test_yes_runs_the_installer_and_a_short_answer_does_not(self):
        found = [{
            "name": "Ollama",
            "endpoint": "http://127.0.0.1:11434/v1",
            "api_key": "${ENV:LOCAL_KEY}",
            "models": ["qwen3:8b"],
        }]
        plan = {
            "name": "Ollama",
            "command": ["echo", "ollama"],
            "display": "curl -fsSL https://ollama.com/install.sh | sh",
            "docs": "https://ollama.com/download",
            "after": "then ollama serve",
        }
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "config.yaml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(SHIPPED)
            with patch("commands.setup.local_models.installer", return_value=plan):
                text, _shown, run_install = self._run(
                    path, ["1", "y"], [[], found], section="model")
            self.assertIn("http://127.0.0.1:8080/v1/chat/completions", text)
            run_install.assert_not_called()

            with open(path, "w", encoding="utf-8") as fh:
                fh.write(SHIPPED)
            with patch("commands.setup.local_models.installer", return_value=plan):
                text, shown, run_install = self._run(
                    path, ["1", "yes", "1", "1", ""], [[], found], section="model")
        run_install.assert_called_once()
        self.assertIn(
            'endpoint: "http://127.0.0.1:11434/v1/chat/completions"', text)
        self.assertIn('name: "qwen3:8b"', text)
        self.assertIn('api_key: "${ENV:LOCAL_KEY}"', text)
        self.assertIn("https://ollama.com/install.sh", shown)
        self.assertNotIn("LOCAL_KEY=", shown)

    def test_a_noninteractive_scan_does_not_install_or_write(self):
        found = [{
            "name": "Ollama",
            "endpoint": "http://127.0.0.1:11434/v1",
            "api_key": "",
            "models": ["qwen3:8b"],
        }]
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "config.yaml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(SHIPPED)
            out = StringIO()
            with patch("commands.setup._tty", return_value=False), \
                    patch("commands.setup.local_models.probe", return_value=found), \
                    patch("commands.setup.local_models.memory_gib", return_value=16), \
                    patch("commands.setup.local_models.run_install") as install, \
                    patch("sys.stdout", out):
                setup.run(_ns(path=path, section="model"))
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            install.assert_not_called()
            self.assertEqual(text, SHIPPED)
            shown = out.getvalue()
            self.assertIn("Ollama", shown)
            self.assertIn("qwen3:8b", shown)
            self.assertNotIn("Type yes", shown)

            out = StringIO()
            with patch("commands.setup._tty", return_value=False), \
                    patch("commands.setup.local_models.probe", return_value=[]), \
                    patch("commands.setup.local_models.memory_gib", return_value=None), \
                    patch("commands.setup.local_models.run_install") as quiet, \
                    patch("sys.stdout", out):
                setup.run(_ns(path=path, section="model"))
            quiet.assert_not_called()
            self.assertIn("Did not install", out.getvalue())

    def test_yes_does_not_install_when_nothing_answers(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "config.yaml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(SHIPPED)
            out = StringIO()
            with patch("commands.setup._tty", return_value=True), \
                    patch("commands.setup.local_models.probe", return_value=[]), \
                    patch("commands.setup.local_models.memory_gib", return_value=None), \
                    patch("commands.setup.local_models.run_install") as install, \
                    patch("sys.stdout", out):
                setup.run(_ns(path=path, section="model", yes=True))
        install.assert_not_called()
        self.assertIn("Did not install", out.getvalue())

    def test_flags_replace_the_shipped_default_and_keep_a_custom_endpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "config.yaml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(SHIPPED)
            with patch("commands.setup.sources.fetch_model_ids", return_value=["qwen3:8b"]), \
                    patch("sys.stdout", StringIO()):
                setup.run(_ns(
                    path=path, yes=True,
                    model_endpoint="http://127.0.0.1:11434/v1",
                    model_name="qwen3:8b",
                    model_api_key_env="LOCAL_KEY"))
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            self.assertIn(
                'endpoint: "http://127.0.0.1:11434/v1/chat/completions"', text)
            self.assertIn('name: "qwen3:8b"', text)
            self.assertIn('api_key: "${ENV:LOCAL_KEY}"', text)

            custom = text.replace(
                'endpoint: "http://127.0.0.1:11434/v1/chat/completions"',
                'endpoint: "http://custom/v1/chat/completions"')
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(custom)
            with patch("commands.setup.sources.fetch_model_ids", return_value=[]), \
                    patch("sys.stdout", StringIO()):
                setup.run(_ns(
                    path=path, yes=True,
                    model_endpoint="http://127.0.0.1:1234/v1",
                    model_name="other"))
            with open(path, encoding="utf-8") as fh:
                kept = fh.read()
        self.assertIn("http://custom/v1/chat/completions", kept)
        self.assertIn('name: "qwen3:8b"', kept)

    def test_jira_section_does_not_probe_or_open_a_browser(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "config.yaml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(SHIPPED)
            with patch("commands.setup.local_models.probe") as probe, \
                    patch("commands.setup.webbrowser.open") as browser, \
                    patch("sys.stdout", StringIO()):
                setup.run(_ns(path=path, section="jira", yes=True))
        probe.assert_not_called()
        browser.assert_not_called()

    def test_setup_help_mentions_the_installers_and_the_key(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        proc = subprocess_run(root)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Ollama", proc.stdout)
        self.assertIn("Lemonade", proc.stdout)
        self.assertIn("--model-api-key", proc.stdout)


def subprocess_run(root):
    import subprocess
    return subprocess.run(
        [sys.executable, os.path.join(root, "pm.py"), "setup", "--help"],
        capture_output=True, text=True, encoding="utf-8", timeout=30)


if __name__ == "__main__":
    unittest.main()
