import unittest
import tempfile
from unittest.mock import patch

from jparty import auto_host as auto_host_module
from jparty.auto_host import AutoHostController, AutoHostAI, Judgement

try:
    from jparty.controller import BuzzerController
    from jparty.game import FinalBoard, Game, KeystrokeManager
except ModuleNotFoundError:
    BuzzerController = None
    FinalBoard = None
    Game = None
    KeystrokeManager = None


class FakeWaiter:
    def __init__(self):
        self.messages = []

    def send(self, message, text=""):
        self.messages.append((message, text))


class FakePlayer:
    def __init__(self, name):
        self.name = name
        self.display_name = name
        self.waiter = FakeWaiter()
        self.page = "buzz"
        self.auto_payload = {}
        self.score = 0
        self.finalanswer = ""


class FakeSignal:
    def __init__(self):
        self.calls = []

    def emit(self):
        self.calls.append(())


class FakeKeyStrokeManager:
    def __init__(self):
        self.activated = []

    def activate(self, *events):
        self.activated.append(events)


class FakeQuestionWidget:
    def __init__(self):
        self.show_calls = 0

    def show_question(self):
        self.show_calls += 1


class FakeDisplayController:
    def __init__(self):
        self.question_widget = FakeQuestionWidget()


class FakeData:
    def __init__(self, board):
        self.rounds = [board]


class FakeQuestion:
    def __init__(self, index=(0, 0), value=200, answer="Ada Lovelace", complete=False, dd=False):
        self.index = index
        self.value = value
        self.answer = answer
        self.text = "This programmer wrote notes on the Analytical Engine"
        self.category = "Computers"
        self.complete = complete
        self.dd = dd


class FakeResponse:
    def __init__(self, json_data=None, content=b"audio", raise_error=None, status_code=200, text=""):
        self._json_data = json_data or {}
        self.content = content
        self.raise_error = raise_error
        self.status_code = status_code
        self.text = text
        self.ok = 200 <= status_code < 400

    def raise_for_status(self):
        if self.raise_error:
            raise self.raise_error

    def json(self):
        return self._json_data


class FakeBoard:
    def __init__(self):
        self.categories = ["Computers", "History"]
        self.dj = False
        self.questions = [
            FakeQuestion((0, 0), 200),
            FakeQuestion((1, 0), 200, answer="Rome"),
            FakeQuestion((0, 1), 400),
        ]

    def get_question(self, i, j):
        for question in self.questions:
            if question.index == (i, j):
                return question
        return None


def fake_final_board():
    board = type("FinalBoard", (), {})()
    board.categories = ["Final Jeopardy"]
    board.category = "Final Jeopardy"
    board.question = FakeQuestion()
    board.questions = [board.question]
    return board


class FakeGame:
    def __init__(self):
        self.config = {"auto_host": {"enabled": True}}
        self.players = [FakePlayer("A"), FakePlayer("B"), FakePlayer("C")]
        self.host_display = None
        self.current_round = FakeBoard()
        self.active_question = self.current_round.questions[0]
        self.answering_player = self.players[0]
        self.correct_calls = 0
        self.incorrect_calls = 0
        self.auto_finalize_judgement_trigger = FakeSignal()
        self.auto_open_responses_trigger = FakeSignal()
        self.loaded_question = None
        self.data = FakeData(self.current_round)
        self.keystroke_manager = FakeKeyStrokeManager()
        self.dc = FakeDisplayController()
        self.accepting_responses = False
        self.soliciting_player = False

    def set_player_in_control(self, player):
        self.highlighted_player = player

    def set_score(self, player, score):
        player.score = score

    def correct_answer(self):
        self.correct_calls += 1

    def incorrect_answer(self):
        self.incorrect_calls += 1

    def load_question(self, question):
        self.loaded_question = question


class AutoHostTests(unittest.TestCase):
    def test_first_player_gets_control_and_prompt(self):
        game = FakeGame()
        controller = AutoHostController(game)
        controller.player_in_control = None

        controller.on_new_player(game.players[0])
        controller.prompt_clue_selection()

        self.assertIs(controller.player_in_control, game.players[0])
        self.assertEqual(game.players[0].page, "select")
        self.assertIn("PROMPT_SELECT_CLUE", [message for message, _text in game.players[0].waiter.messages])
        prompt_payload = next(text for message, text in game.players[0].waiter.messages if message == "PROMPT_SELECT_CLUE")
        self.assertIn('"auto_start_delay_ms": 800', prompt_payload)

    def test_heuristic_clue_selection(self):
        game = FakeGame()
        ai = AutoHostAI({"ai_provider": "local"})

        clue = ai.parse_clue_selection("Computers for 400", game.current_round)

        self.assertIs(clue, game.current_round.questions[2])

    def test_heuristic_clue_selection_accepts_spoken_value(self):
        game = FakeGame()
        ai = AutoHostAI({"ai_provider": "local"})

        clue = ai.parse_clue_selection("Computers for four hundred", game.current_round)

        self.assertIs(clue, game.current_round.questions[2])

    def test_heuristic_clue_selection_accepts_category_number(self):
        game = FakeGame()
        ai = AutoHostAI({"ai_provider": "local"})

        clue = ai.parse_clue_selection("category one for four hundred", game.current_round)

        self.assertIs(clue, game.current_round.questions[2])

    def test_clue_selection_uses_local_parse_before_openai(self):
        game = FakeGame()
        ai = AutoHostAI({"ai_provider": "openai", "openai_api_key": "saved-key"})

        with patch.object(ai, "_openai_parse_clue") as openai_parse:
            clue = ai.parse_clue_selection("Computers for four hundred", game.current_round)

        self.assertIs(clue, game.current_round.questions[2])
        openai_parse.assert_not_called()

    def test_clue_selection_uses_openai_fallback_after_local_miss(self):
        game = FakeGame()
        ai = AutoHostAI({"ai_provider": "openai", "openai_api_key": "saved-key"})

        with patch("jparty.auto_host.requests", object()), patch.object(
            ai, "_heuristic_parse_clue", return_value=None
        ), patch.object(
            ai, "_openai_parse_clue", return_value=game.current_round.questions[2]
        ) as openai_parse:
            clue = ai.parse_clue_selection("the programming clue in the second box", game.current_round)

        self.assertIs(clue, game.current_round.questions[2])
        openai_parse.assert_called_once()

    def test_select_clue_returns_players_to_buzz(self):
        game = FakeGame()
        controller = AutoHostController(game)
        game.active_question = None
        for player in game.players:
            player.page = "select"
            player.auto_payload = {"stale": True}

        controller.select_clue(0, 1)

        self.assertIs(game.loaded_question, game.current_round.questions[2])
        for player in game.players:
            self.assertEqual(player.page, "buzz")
            self.assertEqual(player.auto_payload, {})
            self.assertIn("PROMPT_BUZZ", [message for message, _text in player.waiter.messages])

    def test_select_clue_clears_last_resolved_clue(self):
        game = FakeGame()
        controller = AutoHostController(game)
        controller.last_resolved_clue = {
            "clue": game.current_round.questions[0],
            "answer": "Ada Lovelace",
            "value": 200,
            "awarded_player": game.players[0],
        }
        game.active_question = None

        controller.select_clue(0, 1)

        self.assertIsNone(controller.last_resolved_clue)

    def test_request_dispute_limits_to_five_per_player(self):
        game = FakeGame()
        controller = AutoHostController(game)
        controller.last_resolved_clue = {
            "clue": game.current_round.questions[0],
            "answer": "Ada Lovelace",
            "value": 200,
            "awarded_player": game.players[0],
        }
        player = game.players[0]
        game.active_question = None
        game.answering_player = None
        controller.player_in_control = player
        player.page = "select"

        for _ in range(5):
            player.page = "select"
            controller.request_dispute(player)
            self.assertTrue(controller.dispute_open)
            controller.dispute_open = False
            controller.dispute_votes = {}

        player.page = "select"
        controller.request_dispute(player)

        self.assertEqual(controller.dispute_counts[player], 5)
        self.assertIn(
            ("AUTO_HOST_FALLBACK", "You have reached your 5 dispute limit for this game."),
            player.waiter.messages,
        )

    def test_dispute_pauses_and_resumes_clue_selection(self):
        game = FakeGame()
        controller = AutoHostController(game)
        controller.player_in_control = game.players[0]
        controller.last_resolved_clue = {
            "clue": game.current_round.questions[0],
            "answer": "Ada Lovelace",
            "value": 200,
            "awarded_player": game.players[0],
        }
        game.active_question = None
        game.answering_player = None
        game.players[0].page = "select"
        controller.request_dispute(game.players[1])

        self.assertTrue(controller.dispute_open)
        self.assertTrue(controller._resume_clue_selection_after_dispute)
        dispute_payload = next(text for message, text in game.players[0].waiter.messages if message == "DISPUTE_OPEN")
        self.assertIn('"seconds_remaining": 30', dispute_payload)

        controller.resolve_dispute()

        self.assertFalse(controller.dispute_open)
        self.assertFalse(controller._resume_clue_selection_after_dispute)
        self.assertIn("PROMPT_SELECT_CLUE", [message for message, _text in game.players[0].waiter.messages])

    def test_dispute_awards_double_value_after_prior_incorrect_penalty(self):
        game = FakeGame()
        controller = AutoHostController(game)
        controller.player_in_control = game.players[0]
        game.players[1].score = -200
        controller.last_resolved_clue = {
            "clue": game.current_round.questions[0],
            "answer": "Ada Lovelace",
            "value": 200,
            "awarded_player": None,
            "answering_player": game.players[1],
            "was_correct": False,
        }

        controller.apply_dispute_result("player:1")

        self.assertEqual(game.players[1].score, 200)
        self.assertIs(controller.player_in_control, game.players[1])

    def test_daily_double_dispute_to_nobody_applies_incorrect_wager_penalty(self):
        game = FakeGame()
        controller = AutoHostController(game)
        clue = game.current_round.questions[0]
        clue.dd = True
        clue.value = 800
        game.players[0].score = 800
        controller.last_resolved_clue = {
            "clue": clue,
            "answer": "Ada Lovelace",
            "value": 800,
            "awarded_player": game.players[0],
            "answering_player": game.players[0],
            "was_daily_double": True,
            "was_correct": True,
        }

        controller.apply_dispute_result("nobody")

        self.assertEqual(game.players[0].score, -800)

    def test_dispute_reassigns_single_value_after_prior_correct_award(self):
        game = FakeGame()
        controller = AutoHostController(game)
        game.players[0].score = 200
        game.players[1].score = 0
        controller.last_resolved_clue = {
            "clue": game.current_round.questions[0],
            "answer": "Ada Lovelace",
            "value": 200,
            "awarded_player": game.players[0],
            "was_correct": True,
        }

        controller.apply_dispute_result("player:1")

        self.assertEqual(game.players[0].score, 0)
        self.assertEqual(game.players[1].score, 200)

    def test_dispute_rejects_before_next_clue_picker_opens(self):
        game = FakeGame()
        controller = AutoHostController(game)
        controller.player_in_control = game.players[0]
        controller.last_resolved_clue = {
            "clue": game.current_round.questions[0],
            "answer": "Ada Lovelace",
            "value": 200,
            "awarded_player": game.players[0],
        }
        game.active_question = None
        game.answering_player = None
        game.players[0].page = "buzz"

        controller.request_dispute(game.players[1])

        self.assertFalse(controller.dispute_open)
        self.assertEqual(controller.dispute_counts, {})

    def test_prompt_clue_selection_enables_dispute_controls_after_picker_opens(self):
        game = FakeGame()
        controller = AutoHostController(game)
        controller.player_in_control = game.players[0]
        controller.last_resolved_clue = {
            "clue": game.current_round.questions[0],
            "answer": "Ada Lovelace",
            "value": 200,
            "awarded_player": game.players[0],
        }
        game.active_question = None
        game.answering_player = None

        controller.prompt_clue_selection()

        self.assertEqual(game.players[0].page, "select")
        control_messages = [
            text
            for player in game.players
            for message, text in player.waiter.messages
            if message == "AUTO_HOST_CONTROLS"
        ]
        self.assertTrue(any('"can_dispute": true' in text for text in control_messages))

    def test_dispute_rejects_live_response_window(self):
        game = FakeGame()
        controller = AutoHostController(game)
        controller.last_resolved_clue = {
            "clue": game.current_round.questions[0],
            "answer": "Ada Lovelace",
            "value": 200,
            "awarded_player": game.players[0],
        }
        game.active_question = None
        controller.player_in_control = game.players[0]
        game.players[0].page = "select"
        game.accepting_responses = True

        controller.request_dispute(game.players[1])

        self.assertFalse(controller.dispute_open)
        self.assertEqual(controller.dispute_counts, {})

    def test_dispute_rejects_completed_round(self):
        game = FakeGame()
        controller = AutoHostController(game)
        controller.last_resolved_clue = {
            "clue": game.current_round.questions[0],
            "answer": "Ada Lovelace",
            "value": 200,
            "awarded_player": game.players[0],
        }
        game.active_question = None
        controller.player_in_control = game.players[0]
        game.players[0].page = "select"
        for clue in game.current_round.questions:
            clue.complete = True

        controller.request_dispute(game.players[1])

        self.assertFalse(controller.dispute_open)
        self.assertEqual(controller.dispute_counts, {})

    def test_select_clue_ignores_late_voice_result_after_clue_loaded(self):
        game = FakeGame()
        controller = AutoHostController(game)
        game.active_question = game.current_round.questions[0]

        controller.select_clue(0, 1)

        self.assertIsNone(game.loaded_question)

    def test_audio_clue_selection_ignores_stale_result_after_tap(self):
        game = FakeGame()
        controller = AutoHostController(game)
        controller.player_in_control = game.players[0]
        game.players[0].page = "buzz"
        game.active_question = game.current_round.questions[0]

        controller.ai.transcribe = lambda audio_bytes, mime_type: "Computers for four hundred"
        controller._process_audio(game.players[0], "clue_selection", b"audio", "audio/webm", "1")

        self.assertIsNone(game.loaded_question)

    def test_acknowledge_buzz_sends_auto_record_prompt(self):
        game = FakeGame()
        controller = AutoHostController(game)
        controller._play_text_and_wait = lambda text, purpose: None

        controller._acknowledge_buzz_then_record(game.players[0])

        self.assertEqual(game.players[0].page, "buzz")
        self.assertEqual(game.players[0].auto_payload["answer_state"], "ready")
        self.assertEqual(game.players[0].waiter.messages[-1][0], "PROMPT_RECORD_ANSWER_AUTO")

    def test_buzz_wait_prompt_precedes_auto_record_prompt(self):
        game = FakeGame()
        controller = AutoHostController(game)
        controller._play_text_and_wait = lambda text, purpose: None

        with patch("jparty.auto_host.threading.Thread") as thread_class:
            controller.acknowledge_buzz(game.players[0])
            target = thread_class.call_args.kwargs["target"]
            args = thread_class.call_args.kwargs["args"]

        self.assertEqual(game.players[0].page, "buzz")
        self.assertEqual(game.players[0].auto_payload["answer_state"], "waiting")
        self.assertEqual(game.players[0].waiter.messages[-1][0], "PROMPT_WAIT_ANSWER")

        target(*args)

        self.assertEqual(game.players[0].auto_payload["answer_state"], "ready")
        self.assertEqual(game.players[0].waiter.messages[-1][0], "PROMPT_RECORD_ANSWER_AUTO")

    def test_openai_api_key_prefers_environment(self):
        ai = AutoHostAI({"ai_provider": "openai", "openai_api_key": "saved-key"})

        with patch.dict("os.environ", {"OPENAI_API_KEY": "env-key"}):
            self.assertEqual(ai.api_key(), "env-key")

        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(ai.api_key(), "saved-key")

    def test_local_transcription_posts_to_configured_endpoint(self):
        ai = AutoHostAI({
            "ai_provider": "local",
            "local_stt_base_url": "http://localhost:8082/v1/",
            "local_stt_model": "whisper-large-v3-turbo",
        })
        calls = []

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse({"text": "Computers for four hundred"})

        with patch("jparty.auto_host.requests.post", side_effect=fake_post):
            transcript = ai.transcribe(b"audio", "audio/webm")

        self.assertEqual(transcript, "Computers for four hundred")
        self.assertEqual(calls[0][0], "http://localhost:8082/v1/audio/transcriptions")
        self.assertEqual(calls[0][1]["data"]["model"], "whisper-large-v3-turbo")

    def test_local_transcription_failure_returns_empty_string(self):
        ai = AutoHostAI({"ai_provider": "local"})

        with patch("jparty.auto_host.requests.post", side_effect=RuntimeError("down")), patch(
            "jparty.auto_host.logging.exception"
        ):
            self.assertEqual(ai.transcribe(b"audio", "audio/webm"), "")

    def test_local_clue_selection_posts_to_local_llm_after_heuristic_miss(self):
        game = FakeGame()
        ai = AutoHostAI({
            "ai_provider": "local",
            "local_llm_base_url": "http://localhost:11434/v1/",
            "local_llm_model": "qwen2.5:7b",
        })
        payload = {
            "choices": [
                {
                    "message": {
                        "content": '{"category_index": 0, "value": 400, "needs_gui": false}'
                    }
                }
            ]
        }
        calls = []

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse(payload)

        with patch.object(ai, "_heuristic_parse_clue", return_value=None), patch(
            "jparty.auto_host.requests.post", side_effect=fake_post
        ):
            clue = ai.parse_clue_selection("the second programming clue", game.current_round)

        self.assertIs(clue, game.current_round.questions[2])
        self.assertEqual(calls[0][0], "http://localhost:11434/v1/chat/completions")
        self.assertEqual(calls[0][1]["json"]["model"], "qwen2.5:7b")

    def test_local_judgement_posts_to_local_llm_for_ambiguous_answer(self):
        game = FakeGame()
        ai = AutoHostAI({"ai_provider": "local", "local_llm_model": "llama3.2:3b"})
        payload = {
            "choices": [
                {
                    "message": {
                        "content": '{"is_correct": false, "confidence": 0.7, "reason": "Different person"}'
                    }
                }
            ]
        }

        with patch("jparty.auto_host.requests.post", return_value=FakeResponse(payload)):
            judgement = ai.judge_answer(game.active_question, "Ada Byron")

        self.assertFalse(judgement.is_correct)
        self.assertEqual(judgement.confidence, 0.7)
        self.assertEqual(judgement.reason, "Different person")

    def test_local_invalid_judgement_json_falls_back_to_heuristic(self):
        game = FakeGame()
        ai = AutoHostAI({"ai_provider": "local"})
        payload = {"choices": [{"message": {"content": "not json"}}]}

        with patch("jparty.auto_host.requests.post", return_value=FakeResponse(payload)):
            judgement = ai.judge_answer(game.active_question, "Ada Byron")

        self.assertEqual(judgement.reason, "Did not closely match expected answer.")

    def test_local_tts_posts_to_configured_endpoint_and_reuses_cache(self):
        ai = AutoHostAI({
            "ai_provider": "local",
            "local_tts_base_url": "http://localhost:8880/v1/",
            "local_tts_model": "kokoro",
            "local_tts_voice": "af_heart",
        })
        calls = []

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse(content=b"RIFF-local-wav")

        with tempfile.TemporaryDirectory() as tmpdir, patch("jparty.auto_host.user_data_dir", tmpdir), patch(
            "jparty.auto_host.requests.post", side_effect=fake_post
        ):
            path = ai.speech_file("Correct!", "host")
            cached_path = ai.speech_file("Correct!", "host")

        self.assertEqual(path, cached_path)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "http://localhost:8880/v1/audio/speech")
        self.assertEqual(calls[0][1]["json"]["voice"], "af_heart")

    def test_kokoro_tts_softens_all_caps_words_before_speech(self):
        ai = AutoHostAI({
            "ai_provider": "local",
            "local_tts_base_url": "http://localhost:8880/v1/",
            "local_tts_model": "kokoro",
            "local_tts_voice": "af_heart",
        })
        calls = []

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse(content=b"RIFF-local-wav")

        with tempfile.TemporaryDirectory() as tmpdir, patch("jparty.auto_host.user_data_dir", tmpdir), patch(
            "jparty.auto_host.requests.post", side_effect=fake_post
        ):
            ai.speech_file("THIS CATEGORY is about NASA and COMPUTERS", "host")

        self.assertEqual(
            calls[0][1]["json"]["input"],
            "this category is about NASA and computers",
        )

    def test_basic_clue_speech_normalization_expands_number_abbreviation(self):
        ai = AutoHostAI({"ai_provider": "local", "speech_normalization": False})

        spoken = ai.normalize_clue_for_speech("this no. 1 big city in america")

        self.assertEqual(spoken, "this number one big city in america")

    def test_local_clue_speech_normalization_uses_ollama_style_endpoint(self):
        ai = AutoHostAI({
            "ai_provider": "local",
            "local_llm_base_url": "http://localhost:11434/v1/",
            "local_llm_model": "qwen2.5:7b",
        })
        payload = {
            "choices": [
                {
                    "message": {
                        "content": '{"spoken_text": "this number one big city in america"}'
                    }
                }
            ]
        }
        calls = []

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse(payload)

        with patch("jparty.auto_host.requests.post", side_effect=fake_post):
            spoken = ai.normalize_clue_for_speech("this no. 1 big city in america")
            cached = ai.normalize_clue_for_speech("this no. 1 big city in america")

        self.assertEqual(spoken, "this number one big city in america")
        self.assertEqual(cached, spoken)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "http://localhost:11434/v1/chat/completions")
        self.assertIn("no. 1", calls[0][1]["json"]["messages"][0]["content"])

    def test_clue_text_caches_normalized_speech_on_clue(self):
        game = FakeGame()
        controller = AutoHostController(game)
        calls = []

        def normalize(text):
            calls.append(text)
            return "normalized clue"

        controller.ai.normalize_clue_for_speech = normalize

        self.assertEqual(controller.clue_text(game.active_question), "normalized clue")
        self.assertEqual(controller.clue_text(game.active_question), "normalized clue")
        self.assertEqual(calls, [game.active_question.text])

    def test_category_announcement_uses_sentence_pauses(self):
        game = FakeGame()
        controller = AutoHostController(game)

        text = controller.category_announcement_text(["Computers", "History"])

        self.assertEqual(text, "Computers. History.")

    def test_local_tts_retries_connection_failure_once(self):
        ai = AutoHostAI({
            "ai_provider": "local",
            "local_tts_base_url": "http://localhost:8880/v1/",
            "local_tts_model": "macos-say",
            "local_tts_voice": "Ben Personal Voice",
        })
        calls = []

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            if len(calls) == 1:
                raise auto_host_module.requests.exceptions.ConnectionError("dropped")
            return FakeResponse(content=b"RIFF-local-wav")

        with tempfile.TemporaryDirectory() as tmpdir, patch("jparty.auto_host.user_data_dir", tmpdir), patch(
            "jparty.auto_host.requests.post", side_effect=fake_post
        ), patch("jparty.auto_host.time.sleep"):
            path = ai.speech_file("Hello", "host")

        self.assertIsNotNone(path)
        self.assertEqual(len(calls), 2)

    def test_local_tts_failure_returns_none(self):
        ai = AutoHostAI({"ai_provider": "local"})

        with tempfile.TemporaryDirectory() as tmpdir, patch("jparty.auto_host.user_data_dir", tmpdir), patch(
            "jparty.auto_host.requests.post", side_effect=RuntimeError("down")
        ), patch("jparty.auto_host.logging.exception"):
            self.assertIsNone(ai.speech_file("Hello", "host"))

    def test_local_tts_defaults_to_macos_personal_voice_bridge(self):
        ai = AutoHostAI({"ai_provider": "local"})

        self.assertEqual(ai.config["local_tts_model"], "macos-say")
        self.assertEqual(ai.config["local_tts_preset"], "macos_say")
        self.assertTrue(ai.should_preload_audio())

    def test_fast_judgement_skips_openai_for_exact_match(self):
        game = FakeGame()
        ai = AutoHostAI({"ai_provider": "openai", "openai_api_key": "saved-key"})

        with patch.object(ai, "_openai_judge_answer") as openai_judge:
            judgement = ai.judge_answer(game.active_question, "Who is Ada Lovelace?")

        self.assertTrue(judgement.is_correct)
        self.assertEqual(judgement.confidence, 0.98)
        openai_judge.assert_not_called()

    def test_plausible_non_matching_judgement_uses_openai(self):
        game = FakeGame()
        ai = AutoHostAI({"ai_provider": "openai", "openai_api_key": "saved-key"})

        with patch("jparty.auto_host.requests", object()), patch.object(
            ai,
            "_openai_judge_answer",
            return_value=Judgement(False, 0.7, "OpenAI rejected it", "Ada Byron"),
        ) as openai_judge:
            judgement = ai.judge_answer(game.active_question, "Ada Byron")

        self.assertFalse(judgement.is_correct)
        self.assertEqual(judgement.reason, "OpenAI rejected it")
        openai_judge.assert_called_once()

    def test_obvious_wrong_judgement_skips_openai(self):
        game = FakeGame()
        ai = AutoHostAI({"ai_provider": "openai", "openai_api_key": "saved-key"})

        with patch.object(ai, "_openai_judge_answer") as openai_judge:
            judgement = ai.judge_answer(game.active_question, "zzzzzzzz")

        self.assertFalse(judgement.is_correct)
        self.assertEqual(judgement.confidence, 0.97)
        openai_judge.assert_not_called()

    def test_fast_judgement_skips_openai_for_near_match(self):
        game = FakeGame()
        ai = AutoHostAI({"ai_provider": "openai", "openai_api_key": "saved-key"})

        with patch.object(ai, "_openai_judge_answer") as openai_judge:
            judgement = ai.judge_answer(game.active_question, "What is Ada Lovelace")

        self.assertTrue(judgement.is_correct)
        self.assertEqual(judgement.confidence, 0.98)
        openai_judge.assert_not_called()

    def test_correct_judgement_finalizes_correct(self):
        game = FakeGame()
        controller = AutoHostController(game)

        controller.open_pending_judgement(
            game.players[0],
            Judgement(True, 0.95, "Looks right", "Ada Lovelace"),
        )
        controller.finalize_pending_judgement()

        self.assertEqual(game.correct_calls, 1)
        self.assertEqual(game.incorrect_calls, 0)

    def test_judgement_resolves_immediately_without_live_challenge(self):
        game = FakeGame()
        controller = AutoHostController(game)

        controller.open_pending_judgement(
            game.players[0],
            Judgement(False, 0.7, "Looks wrong", "Wrong answer"),
        )

        self.assertIsNone(controller.pending_judgement)
        self.assertEqual(game.correct_calls, 0)
        self.assertEqual(game.incorrect_calls, 1)

    def test_daily_double_incorrect_judgement_sequences_reveal(self):
        game = FakeGame()
        game.active_question.dd = True
        controller = AutoHostController(game)

        with patch("jparty.auto_host.threading.Thread") as thread_class:
            controller.open_pending_judgement(
                game.players[0],
                Judgement(False, 0.7, "Looks wrong", "Wrong answer"),
            )

        self.assertEqual(game.incorrect_calls, 1)
        self.assertTrue(controller._suppress_next_board_prompt)
        self.assertEqual(
            thread_class.call_args.kwargs["target"],
            controller._speak_daily_double_incorrect_then_prompt_next_clue,
        )

    def test_daily_double_incorrect_feedback_reveals_answer_before_next_clue(self):
        game = FakeGame()
        controller = AutoHostController(game)
        game.active_question = None
        played = []
        controller._play_text_and_wait = lambda text, purpose: played.append(purpose)
        controller._speak_next_clue_then_prompt = lambda: played.append("next-clue")

        controller._speak_daily_double_incorrect_then_prompt_next_clue(game.current_round.questions[0])

        self.assertEqual(
            played,
            ["daily-double-incorrect-feedback", "daily-double-answer-reveal", "next-clue"],
        )

    def test_correct_answer_suppresses_immediate_board_prompt(self):
        game = FakeGame()
        controller = AutoHostController(game)
        controller.player_in_control = game.players[0]

        controller._suppress_next_board_prompt = True
        game.active_question = None
        controller.after_back_to_board()

        messages = [message for message, _text in game.players[0].waiter.messages]
        self.assertNotIn("PROMPT_SELECT_CLUE", messages)
        self.assertFalse(controller._suppress_next_board_prompt)

    def test_correct_feedback_sequence_prompts_after_speech(self):
        game = FakeGame()
        controller = AutoHostController(game)
        controller.player_in_control = game.players[0]
        game.active_question = None
        played = []
        controller._play_text_and_wait = lambda text, purpose: played.append(purpose)

        controller._speak_correct_then_prompt_next_clue(game.players[0])

        self.assertEqual(played, ["correct-feedback", "next-clue"])
        self.assertIn("PROMPT_SELECT_CLUE", [message for message, _text in game.players[0].waiter.messages])

    def test_correct_feedback_does_not_prompt_clue_selection_in_final(self):
        game = FakeGame()
        controller = AutoHostController(game)
        controller.player_in_control = None
        game.current_round = fake_final_board()
        game.active_question = None
        played = []
        controller._play_text_and_wait = lambda text, purpose: played.append(purpose)

        controller._speak_correct_then_prompt_next_clue(game.players[0])

        self.assertEqual(played, ["correct-feedback"])
        self.assertNotIn("PROMPT_SELECT_CLUE", [message for message, _text in game.players[0].waiter.messages])

    def test_final_wager_prompt_survives_last_correct_judgement(self):
        game = FakeGame()
        controller = AutoHostController(game)
        player = game.players[0]

        def advance_to_final():
            game.correct_calls += 1
            game.active_question = None
            game.current_round = fake_final_board()
            player.page = "wager"
            player.waiter.send("PROMPTWAGER", str(max(player.score, 0)))

        game.correct_answer = advance_to_final
        controller.pending_judgement = {
            "player": player,
            "judgement": Judgement(True, 0.95, "Looks right", "Ada Lovelace"),
        }

        with patch("jparty.auto_host.threading.Thread") as thread_class:
            controller.finalize_pending_judgement()

        messages = [message for message, _text in player.waiter.messages]
        self.assertIn("PROMPTWAGER", messages)
        self.assertNotIn("JUDGEMENT_RESULT", messages)
        thread_class.assert_not_called()

    def test_round_started_announces_double_jeopardy_before_prompt(self):
        game = FakeGame()
        controller = AutoHostController(game)
        controller.player_in_control = game.players[0]
        game.current_round.dj = True
        played = []
        controller._play_text_and_wait = lambda text, purpose: played.append((text, purpose))

        controller._announce_round_started()

        self.assertEqual(played[0][1], "round-intro")
        self.assertIn("Double Jeopardy", played[0][0])
        self.assertIn("PROMPT_SELECT_CLUE", [message for message, _text in game.players[0].waiter.messages])

    @unittest.skipIf(BuzzerController is None, "PyQt6 game runtime is unavailable")
    def test_final_answer_ignores_stale_toolate_submit_after_player_submits(self):
        game = type("GameStub", (), {})()
        game.current_round = FinalBoard("Final", FakeQuestion())
        game.auto_host = type("AutoHost", (), {"enabled": True})()
        game.answering_player = None
        game.active_question = None
        player = FakePlayer("A")
        player.page = "answer"

        def record_answer(answering_player, guess):
            answering_player.finalanswer = guess

        game.answer = record_answer
        controller = BuzzerController.__new__(BuzzerController)
        controller.game = game

        controller.answer(player, "real final answer")
        controller.answer(player, "old daily double answer")

        self.assertEqual(player.finalanswer, "real final answer")
        self.assertEqual(player.page, "null")

    @unittest.skipIf(Game is None or KeystrokeManager is None, "PyQt6 game runtime is unavailable")
    def test_end_game_disarms_stale_final_space_handlers_before_play_again(self):
        game = Game.__new__(Game)
        players = [FakePlayer("A"), FakePlayer("B")]
        players[0].score = 1000
        players[1].score = 500
        game.players = players
        game.auto_host = type("AutoHost", (), {"enabled": True})()
        game.play_sound = lambda _file_name: None

        class PlayerWidget:
            def set_lights(self, _value):
                pass

        class FinalWindow:
            def show_winner(self, _winner):
                pass

            def show_tie(self):
                pass

        class Display:
            def __init__(self):
                self.final_window = FinalWindow()

            def player_widget(self, _player):
                return PlayerWidget()

        game.dc = Display()
        game.keystroke_manager = KeystrokeManager()
        calls = []
        space_key = 32
        hint = lambda _active: None
        for event_name in Game.FINAL_KEYSTROKE_EVENTS:
            game.keystroke_manager.addEvent(
                event_name,
                space_key,
                lambda event_name=event_name: calls.append(event_name),
                hint,
            )
        game.keystroke_manager.addEvent(
            "CLOSE_GAME", space_key, lambda: calls.append("CLOSE_GAME"), hint
        )
        game.keystroke_manager.activate("FINAL_OPEN_RESPONSES", "FINAL_NEXT_PLAYER")

        Game.end_game(game)
        game.keystroke_manager.call(space_key)

        self.assertEqual(calls, ["CLOSE_GAME"])
        for player in players:
            self.assertIn("PROMPT_PLAY_AGAIN", [message for message, _text in player.waiter.messages])

    def test_daily_double_amount_parsing(self):
        game = FakeGame()
        controller = AutoHostController(game)
        controller.player_in_control = game.players[0]
        game.players[0].score = 1600

        cases = {
            "500": 500,
            "one thousand": 1000,
            "five hundred": 500,
            "two grand": 2000,
            "true daily double": 1600,
            "all in": 1600,
            "all of it": 1600,
            "everything": 1600,
        }
        for transcript, expected in cases.items():
            with self.subTest(transcript=transcript):
                self.assertEqual(controller._parse_amount(transcript), expected)

    def test_daily_double_wager_accepts_valid_wager_and_records_after_clue(self):
        game = FakeGame()
        controller = AutoHostController(game)
        controller.player_in_control = game.players[0]
        game.active_question = FakeQuestion((0, 0), 200, dd=True)
        game.players[0].score = 600
        played = []
        controller._play_text_and_wait = lambda text, purpose: played.append(purpose)

        with patch("jparty.auto_host.threading.Thread") as thread_class:
            controller.apply_daily_double_wager(0, 800)
            target = thread_class.call_args.kwargs["target"]
            args = thread_class.call_args.kwargs["args"]

        target(*args)

        self.assertEqual(game.active_question.value, 800)
        self.assertEqual(game.keystroke_manager.activated[-1], ("CORRECT_ANSWER", "INCORRECT_ANSWER"))
        self.assertEqual(game.dc.question_widget.show_calls, 1)
        self.assertIn("dd-clue-0-0", played)
        self.assertEqual(game.players[0].waiter.messages[-1][0], "PROMPT_RECORD_ANSWER_AUTO")

    def test_daily_double_wager_rejects_over_max_wager(self):
        game = FakeGame()
        controller = AutoHostController(game)
        controller.player_in_control = game.players[0]
        game.active_question = FakeQuestion((0, 0), 200, dd=True)
        game.players[0].score = 600

        with patch("jparty.auto_host.threading.Thread") as thread_class:
            controller.apply_daily_double_wager(0, 2000)

        self.assertEqual(game.active_question.value, 200)
        self.assertEqual(game.keystroke_manager.activated, [])
        self.assertEqual(game.players[0].page, "dd_wager")
        self.assertEqual(game.players[0].waiter.messages[-2][0], "PROMPT_DD_WAGER")
        self.assertEqual(game.players[0].waiter.messages[-1][0], "AUTO_HOST_FALLBACK")
        self.assertIn("not valid", game.players[0].waiter.messages[-1][1])
        thread_class.assert_called_once()

    def test_daily_double_wager_ignores_players_not_in_control(self):
        game = FakeGame()
        controller = AutoHostController(game)
        controller.player_in_control = game.players[0]
        game.active_question = FakeQuestion((0, 0), 200, dd=True)

        controller.apply_daily_double_wager(1, 800)

        self.assertEqual(game.active_question.value, 200)
        self.assertEqual(game.keystroke_manager.activated, [])

    @unittest.skipIf(Game is None, "PyQt6 game runtime is unavailable")
    def test_completed_double_jeopardy_auto_advances_from_board(self):
        game = Game.__new__(Game)
        question = FakeQuestion(complete=False)
        game.active_question = question
        game.current_round = FakeBoard()
        game.current_round.dj = True
        for clue in game.current_round.questions:
            clue.complete = True
        game.current_round.questions[0] = question
        game.previous_answerer = [object()]
        game.players = []
        game.timer = object()
        game.keystroke_manager = FakeKeyStrokeManager()
        game.auto_host = type("AutoHost", (), {"enabled": True, "after_back_to_board": lambda _self: None})()
        game.dc = type(
            "Display",
            (),
            {
                "hide_question": lambda _self: None,
                "player_widget": lambda _self, _player: None,
            },
        )()
        advanced = []
        game.next_round = lambda: advanced.append(True)

        Game.back_to_board(game)

        self.assertTrue(question.complete)
        self.assertEqual(advanced, [True])

    @unittest.skipIf(Game is None, "PyQt6 game runtime is unavailable")
    def test_completed_first_round_auto_advances_from_board(self):
        game = Game.__new__(Game)
        question = FakeQuestion(complete=False)
        game.active_question = question
        game.current_round = FakeBoard()
        game.current_round.dj = False
        for clue in game.current_round.questions:
            clue.complete = True
        game.current_round.questions[0] = question
        game.previous_answerer = [object()]
        game.players = []
        game.timer = object()
        game.keystroke_manager = FakeKeyStrokeManager()
        game.auto_host = type("AutoHost", (), {"enabled": True, "after_back_to_board": lambda _self: None})()
        game.dc = type(
            "Display",
            (),
            {
                "hide_question": lambda _self: None,
                "player_widget": lambda _self, _player: None,
            },
        )()
        advanced = []
        game.next_round = lambda: advanced.append(True)

        Game.back_to_board(game)

        self.assertTrue(question.complete)
        self.assertEqual(advanced, [True])

if __name__ == "__main__":
    unittest.main()
