import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from jparty.auto_host import AutoHostAI, DEFAULT_AUTO_HOST_CONFIG, Judgement
from jparty.constants import DEFAULT_CONFIG
from jparty.local_services import check_services, script_environment


class BinaryJudgeTests(unittest.TestCase):
    def setUp(self):
        self.ai = AutoHostAI({})
        self.clue = SimpleNamespace(text='This city is the capital of France.', answer='Paris')

    def test_defaults_select_binary_without_changing_generation(self):
        self.assertEqual(DEFAULT_AUTO_HOST_CONFIG['judge_provider'], 'local_binary')
        self.assertEqual(DEFAULT_CONFIG['auto_host']['judge_provider'], 'local_binary')
        self.assertEqual(DEFAULT_AUTO_HOST_CONFIG['local_llm_model'], 'qwen2.5:7b')
        self.assertEqual(script_environment({})['JPARTY_LOCAL_KEV_ENABLED'], '0')
        with patch.object(self.ai, '_local_judge_answer', return_value=Judgement(False, None, 'Rejected', 'not Paris')) as local, patch.object(self.ai, '_openai_judge_answer') as cloud:
            self.assertFalse(self.ai.judge_answer(self.clue, 'not Paris').is_correct)
            local.assert_called_once()
            cloud.assert_not_called()

    def test_tested_prompt_and_two_token_payload(self):
        response = Mock(json=Mock(return_value={'choices': [{'message': {'content': 'true'}}]}))
        with patch('jparty.auto_host.requests.post', return_value=response) as post:
            result = self.ai.judge_answer(self.clue, 'City of Paris')
        self.assertTrue(result.is_correct)
        self.assertIsNone(result.confidence)
        self.assertEqual(post.call_args.args[0], 'http://localhost:11434/v1/chat/completions')
        body = post.call_args.kwargs['json']
        self.assertEqual(body['model'], 'qwen2.5:7b')
        self.assertEqual(body['max_tokens'], 2)
        self.assertEqual(body['temperature'], 0)
        prompt = body['messages'][0]['content']
        instructions, state, suffix = prompt.split('\n')
        self.assertEqual(json.loads(state), {'clue': self.clue.text, 'expected_answer': 'Paris', 'player_answer': 'City of Paris'})
        self.assertIn('Apply normal leniency.', instructions)
        self.assertEqual(suffix, 'Return only true or false, without an explanation.')

    def test_strict_binary_parsing_and_failure(self):
        for content, expected in [('true', True), (' FALSE. ', False), ('true because yes', None), ('{"is_correct":true}', None), ('', None), ('yes', None)]:
            with self.subTest(content=content), patch('jparty.auto_host.requests.post', return_value=Mock(json=Mock(return_value={'choices': [{'message': {'content': content}}]}))), patch('jparty.auto_host.logging.exception'):
                result = self.ai._local_judge_answer(self.clue, 'not Paris', 'strict')
                if expected is None:
                    self.assertIsNone(result)
                else:
                    self.assertEqual(result.is_correct, expected)
        with patch('jparty.auto_host.requests.post', side_effect=TimeoutError), patch('jparty.auto_host.logging.exception'):
            result = self.ai.judge_answer(self.clue, 'not Paris')
        self.assertFalse(result.is_correct)
        self.assertEqual(result.confidence, 0)
        self.assertIn('unavailable', result.reason)

    def test_only_empty_and_exact_answers_bypass_model(self):
        with patch.object(self.ai, '_local_judge_answer') as local:
            self.assertFalse(self.ai.judge_answer(self.clue, '').is_correct)
            self.assertTrue(self.ai.judge_answer(self.clue, 'What is Paris?').is_correct)
            local.assert_not_called()
        for expected, given in [('Paris', 'not Paris'), ('Paris', 'Paris or London'), ('Gilbert Stuart', 'Stuart Gilbert'), ('water', 'H2O'), ('Paris', 'Pariss')]:
            with self.subTest(given=given), patch.object(self.ai, '_local_judge_answer', return_value=Judgement(False, None, 'Judged', given)) as local:
                self.clue.answer = expected
                self.ai.judge_answer(self.clue, given)
                local.assert_called_once()

    def test_cloud_generation_still_requires_selected_local_judge(self):
        with patch('jparty.local_services.requests.get', return_value=Mock(json=Mock(return_value={'data': []}))) as get:
            rows = check_services({'ai_provider': 'openai', 'openai_api_key': 'test'})
        self.assertTrue(rows[0]['ready'])
        self.assertFalse(rows[1]['ready'])
        self.assertEqual(rows[1]['name'], 'Answer judge · local LLM')
        get.assert_called_once_with('http://localhost:11434/v1/models', timeout=(0.7, 1.2))


if __name__ == '__main__':
    unittest.main()
