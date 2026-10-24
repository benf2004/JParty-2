import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from jparty.auto_host import AutoHostAI, Judgement


class KevJudgeTests(unittest.TestCase):
    def setUp(self):
        self.ai = AutoHostAI({
            "ai_provider": "local", "judge_provider": "kev",
            "kev_base_url": "http://localhost:8009/v1/",
        })
        self.clue = SimpleNamespace(text="This programmer worked on the Analytical Engine.", answer="Ada Lovelace")

    def response(self, probability):
        return Mock(json=Mock(return_value={"answers": {"is_correct": {"type": "noul", "noul": probability}}}))

    def test_kev_request_and_probability_mapping(self):
        for probability, correct, confidence in [(0.91, True, 0.91), (0.12, False, 0.88)]:
            with self.subTest(probability=probability), patch(
                "jparty.auto_host.requests.post", return_value=self.response(probability)
            ) as post, patch.object(self.ai, "_local_judge_answer") as local:
                result = self.ai.judge_answer(self.clue, "Ada Byron", "generous")
                self.assertEqual(result.is_correct, correct)
                self.assertAlmostEqual(result.confidence, confidence)
                self.assertEqual(result.transcript, "Ada Byron")
                local.assert_not_called()
                args, kwargs = post.call_args
                self.assertEqual(args[0], "http://localhost:8009/v1/systemone")
                self.assertEqual(kwargs["json"]["model"], "kev-latest")
                self.assertIn("Ada Byron", kwargs["json"]["state"])
                self.assertIn("Ada Lovelace", kwargs["json"]["state"])
                question = kwargs["json"]["questions"]["is_correct"]
                self.assertEqual(question["type"], "noul")
                self.assertIn("generous", question["instructions"])
                self.assertEqual(kwargs["timeout"], 3)

    def test_fast_checks_skip_kev(self):
        with patch("jparty.auto_host.requests.post") as post:
            self.assertTrue(self.ai.judge_answer(self.clue, "Who is Ada Lovelace?").is_correct)
            self.assertFalse(self.ai.judge_answer(self.clue, "").is_correct)
            post.assert_not_called()

    def test_invalid_response_falls_back_to_local_judge(self):
        fallback = Judgement(False, 0.7, "Fallback", "Ada Byron")
        for value in [None, True, "0.9", -0.1, 1.1, float("nan"), float("inf"), {}]:
            with self.subTest(value=value), patch(
                "jparty.auto_host.requests.post", return_value=self.response(value)
            ), patch.object(self.ai, "_local_judge_answer", return_value=fallback) as local, patch(
                "jparty.auto_host.logging.exception"
            ):
                self.assertIs(self.ai.judge_answer(self.clue, "Ada Byron"), fallback)
                local.assert_called_once()

    def test_transport_http_and_schema_failures_fall_back(self):
        for response in [Mock(raise_for_status=Mock(side_effect=RuntimeError("HTTP error"))),
                         Mock(json=Mock(return_value={})),
                         Mock(json=Mock(side_effect=ValueError("bad JSON")))]:
            with self.subTest(response=response), patch(
                "jparty.auto_host.requests.post", return_value=response
            ), patch.object(self.ai, "_local_judge_answer", return_value=None), patch(
                "jparty.auto_host.logging.exception"
            ):
                self.assertEqual(self.ai.judge_answer(self.clue, "Ada Byron").reason,
                                 "Answer judge unavailable; could not verify the answer.")
        with patch("jparty.auto_host.requests.post", side_effect=TimeoutError), patch(
            "jparty.auto_host.logging.exception"
        ), patch.object(self.ai, "_local_judge_answer", return_value=None):
            self.assertIsNotNone(self.ai.judge_answer(self.clue, "Ada Byron"))

    def test_default_judge_does_not_call_kev(self):
        ai = AutoHostAI({"ai_provider": "local"})
        with patch.object(ai, "_kev_judge_answer") as kev, patch.object(ai, "_local_judge_answer") as local:
            ai.judge_answer(self.clue, "Ada Byron")
            kev.assert_not_called()
            local.assert_called_once()

    def test_kev_failure_uses_openai_when_configured(self):
        ai = AutoHostAI({"ai_provider": "openai", "judge_provider": "kev", "openai_api_key": "test"})
        with patch.object(ai, "_kev_judge_answer", return_value=None), patch.object(ai, "_openai_judge_answer") as judge:
            ai.judge_answer(self.clue, "Ada Byron")
            judge.assert_called_once()

    def test_text_generation_still_uses_local_llm(self):
        response = Mock(json=Mock(return_value={"choices": [{"message": {"content": '{"text": "spoken clue"}'}}]}))
        with patch("jparty.auto_host.requests.post", return_value=response) as post:
            self.assertEqual(self.ai._local_chat_json("Normalize this clue"), {"text": "spoken clue"})
            self.assertEqual(post.call_args.args[0], "http://localhost:11434/v1/chat/completions")
            self.assertEqual(post.call_args.kwargs["json"]["model"], "qwen2.5:7b")


if __name__ == "__main__":
    unittest.main()
