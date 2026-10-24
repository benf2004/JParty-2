import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock


spec = importlib.util.spec_from_file_location('answer_benchmark', Path(__file__).resolve().parents[1] / 'scripts/benchmark_answer_judging.py')
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class AnswerBenchmarkTests(unittest.TestCase):
    def test_exact_only_replay_defers_negation_and_semantic_aliases(self):
        ai = benchmark.AutoHostAI({})
        self.assertFalse(benchmark.exact_only_replay(ai, {'answer': 'Paris'}, 'not Paris', False))
        self.assertTrue(benchmark.exact_only_replay(ai, {'answer': 'water'}, 'H2O', True))
        self.assertTrue(benchmark.exact_only_replay(ai, {'answer': 'Paris'}, 'What is Paris?', False))
        self.assertFalse(benchmark.exact_only_replay(ai, {'answer': 'Paris'}, '', True))

    def test_unreviewed_cases_and_errors_do_not_become_false_rejections(self):
        rows = [
            {'gold': True, 'prediction': True, 'seconds': .1},
            {'gold': False, 'prediction': True, 'seconds': .2},
            {'gold': None, 'prediction': False, 'seconds': .3},
            {'gold': True, 'error': 'Unavailable'},
        ]
        metrics = benchmark.metrics(rows, 'prediction')
        self.assertEqual(metrics['labeled'], 2)
        self.assertEqual(metrics['accuracy'], .5)
        self.assertEqual(metrics['errors'], 1)
        self.assertEqual(metrics['unreviewed'], 1)
        self.assertEqual(metrics['false_rejects'], 0)
        self.assertEqual(metrics['false_accepts'], 1)

    def test_full_and_reduced_context_preserve_response(self):
        session = Mock()
        session.post.return_value.json.return_value = {'answers': {'is_correct': {'noul': .2}}}
        clue = {'text': 'The capital of France.', 'answer': 'Paris'}
        case = {'response': 'What is ...?'}
        for context in ['full', 'answer_only']:
            prediction, probability, _, _ = benchmark.predict(session, 'kev', 'http://localhost:8009/v1', 'kev-latest', clue, case, context)
            self.assertFalse(prediction)
            self.assertEqual(probability, .2)
            import json
            state = json.loads(session.post.call_args.kwargs['json']['state'])
            self.assertEqual(state['player_answer'], case['response'])
            self.assertEqual('clue' in state, context == 'full')

    def test_invalid_decision_probability_is_an_error(self):
        for value in [True, '0.8', float('nan'), 1.1]:
            session = Mock()
            session.post.return_value.json.return_value = {'answers': {'is_correct': {'noul': value}}}
            with self.subTest(value=value), self.assertRaises(ValueError):
                benchmark.predict(session, 'kev', 'http://localhost:8009/v1', 'kev-latest',
                                  {'text': 'clue', 'answer': 'reference'}, {'response': '...'}, 'full')

    def test_boolean_model_must_return_a_valid_decision(self):
        session = Mock()
        session.post.return_value.json.return_value = {'choices': [{'message': {'content': 'maybe'}}]}
        with self.assertRaises(ValueError):
            benchmark.predict(session, 'local_boolean', 'http://localhost:11434/v1', 'model',
                              {'text': 'clue', 'answer': 'reference'}, {'response': '...'}, 'full')

    def test_boolean_model_can_add_a_harmless_final_period(self):
        session = Mock()
        session.post.return_value.json.return_value = {'choices': [{'message': {'content': 'False.'}}]}
        prediction, _, _, _ = benchmark.predict(session, 'local_boolean', 'http://localhost:11434/v1', 'model',
                                                {'text': 'clue', 'answer': 'reference'}, {'response': '...'}, 'full')
        self.assertFalse(prediction)


if __name__ == '__main__':
    unittest.main()
