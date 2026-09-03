import unittest
from unittest.mock import patch

from core import model
from commands import review


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise model.requests.HTTPError("boom")

    def json(self):
        return self._payload


def cfg(**overrides):
    data = {
        "endpoint": "http://127.0.0.1:8080/v1/chat/completions",
        "name": "qwen-local",
        "temperature": 0.4,
        "json_temperature": 0.2,
        "top_p": 0.8,
        "top_k": 20,
        "presence_penalty": 1.5,
        "max_tokens": 2048,
        "timeout": 30,
        "enable_thinking": False,
    }
    data.update(overrides)
    return data


class ThinkingStripTests(unittest.TestCase):
    def test_think_block_is_removed(self):
        raw = "<think>I will list the tickets.</think>\n[{\"key\":\"APS-1\"}]"
        self.assertEqual(model.strip_thinking(raw), '[{"key":"APS-1"}]')

    def test_unclosed_tags_are_dropped(self):
        self.assertEqual(model.strip_thinking("<think>oops"), "oops")

    def test_message_text_prefers_content_over_reasoning(self):
        payload = {"choices": [{"message": {
            "content": "<think>plan</think>\n### What changed since last week\n- None.",
            "reasoning_content": "do not use this",
        }}]}
        self.assertTrue(model.message_text(payload).startswith("### What changed"))
        self.assertNotIn("plan", model.message_text(payload))

    def test_multipart_content_is_joined(self):
        payload = {"choices": [{"message": {
            "content": [{"type": "text", "text": "hello "},
                        {"type": "text", "text": "world"}],
        }}]}
        self.assertEqual(model.message_text(payload), "hello world")


class PayloadTests(unittest.TestCase):
    def test_thinking_is_off_and_no_think_is_prefixed(self):
        payload = model.build_payload(cfg(), "sys", "hello")
        self.assertEqual(payload["chat_template_kwargs"],
                         {"enable_thinking": False, "preserve_thinking": False})
        self.assertEqual(payload["messages"][1]["content"], "/no_think\nhello")
        self.assertEqual(payload["temperature"], 0.4)
        self.assertEqual(payload["top_p"], 0.8)
        self.assertEqual(payload["top_k"], 20)
        self.assertEqual(payload["presence_penalty"], 1.5)

    def test_thinking_can_be_turned_on(self):
        payload = model.build_payload(cfg(enable_thinking=True), "sys", "hello")
        self.assertTrue(payload["chat_template_kwargs"]["enable_thinking"])
        self.assertEqual(payload["messages"][1]["content"], "hello")

    def test_json_calls_use_the_cooler_temperature(self):
        reply = {"choices": [{"message": {"content": "[]"}}]}
        with patch("core.model.requests.post",
                   return_value=FakeResponse(reply)) as post:
            model.call_model_json(cfg(), "sys", "[]")
        self.assertEqual(post.call_args.kwargs["json"]["temperature"], 0.2)


class JsonParseTests(unittest.TestCase):
    def _parse(self, content):
        reply = {"choices": [{"message": {"content": content}}]}
        with patch("core.model.requests.post", return_value=FakeResponse(reply)):
            return model.call_model_json(cfg(), "sys", "body")

    def test_plain_array(self):
        data, err = self._parse('[{"key":"APS-1"}]')
        self.assertIsNone(err)
        self.assertEqual(data[0]["key"], "APS-1")

    def test_array_hidden_in_a_think_block_and_prose(self):
        data, err = self._parse(
            "<think>flag the vague one</think>\n"
            "Here you go:\n"
            '```json\n[{"key":"APS-11","problem":"vague"}]\n```\n')
        self.assertIsNone(err)
        self.assertEqual(data[0]["key"], "APS-11")

    def test_a_single_object_is_wrapped(self):
        data, err = self._parse('{"key":"APS-11","problem":"vague"}')
        self.assertIsNone(err)
        self.assertEqual(data[0]["key"], "APS-11")

    def test_brackets_inside_a_string_do_not_cut_the_array(self):
        data, err = self._parse(
            '[{"key":"APS-1","problem":"title is [WIP] still"}]')
        self.assertIsNone(err)
        self.assertEqual(data[0]["problem"], "title is [WIP] still")

    def test_empty_reply_is_an_error(self):
        data, err = self._parse("<think>still thinking</think>")
        self.assertIsNone(data)
        self.assertIn("empty", err.lower())


class ReportPromptTests(unittest.TestCase):
    def test_all_seven_headings_are_in_the_system_prompt(self):
        text = model.REPORT_SYSTEM_PROMPT.format(audience="directors")
        for heading in model.REPORT_HEADINGS:
            self.assertIn(f"### {heading}", text)

    def test_material_is_capped_so_the_prompt_stays_short(self):
        items = [{"ref": f"SDX-J{i}", "source": "Jira",
                  "title": f"Item {i}", "detail": "x" * 400}
                 for i in range(50)]
        block = model.build_material(items, max_items=40, detail_limit=180)
        self.assertIn("+10 more items omitted", block)
        self.assertLess(len(block), 40 * 250)

    def test_report_user_message_ends_with_the_write_now_line(self):
        with patch("core.model.call_model", return_value="ok") as call:
            model.infer_report_section(
                cfg(), "directors",
                {"name": "Secure Data Exchange", "abbrev": "SDX"},
                [{"ref": "SDX-J1", "source": "Jira",
                  "title": "APS-10: Publish", "detail": "In Review"}],
                "(First run for this workstream — no previous week to compare.)")
        user = call.call_args.args[2]
        self.assertTrue(user.endswith(model.REPORT_USER_TAIL))
        self.assertIn("CHANGE SUMMARY:", user)
        system = call.call_args.args[1]
        self.assertIn("directors", system)
        self.assertIn("/no_think", model._with_no_think(cfg(), user))


class ReviewPromptTests(unittest.TestCase):
    def test_titles_prompt_has_a_worked_example_and_the_schema(self):
        self.assertIn("JSON array", review.TITLES_PROMPT)
        self.assertIn('"key"', review.TITLES_PROMPT)
        self.assertIn("APS-11", review.TITLES_PROMPT)
        self.assertIn("[]", review.TITLES_PROMPT)

    def test_criteria_prompt_has_a_worked_example_and_the_schema(self):
        self.assertIn("JSON array", review.CRITERIA_PROMPT)
        self.assertIn('"missing"', review.CRITERIA_PROMPT)
        self.assertIn("APS-20", review.CRITERIA_PROMPT)

    def test_user_input_puts_the_output_cue_last(self):
        issues = [{"key": "APS-1", "summary": "Do the thing",
                   "acceptance_criteria": "", "description": "n/a"}]
        titles = review.build_titles_input(issues)
        self.assertTrue(titles.endswith(review.TITLES_USER_TAIL))
        self.assertLess(titles.find("APS-1"), titles.find(review.TITLES_USER_TAIL))

        criteria = review.build_criteria_input(issues)
        self.assertTrue(criteria.endswith(review.CRITERIA_USER_TAIL))
        # Long descriptions are trimmed so the instruction is not buried.
        long = [{"key": "APS-2", "summary": "Story",
                 "acceptance_criteria": "", "description": "word " * 200}]
        trimmed = review.build_criteria_input(long)
        self.assertLess(len(trimmed), 800)


if __name__ == "__main__":
    unittest.main()
