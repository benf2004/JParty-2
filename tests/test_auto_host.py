import unittest
from unittest.mock import patch

from jparty.auto_host import AutoHostController, AutoHostAI, Judgement


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

    def set_player_in_control(self, player):
        self.highlighted_player = player

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

        for _ in range(5):
            controller.request_dispute(player)
            self.assertTrue(controller.dispute_open)
            controller.dispute_open = False
            controller.dispute_votes = {}

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
        controller.request_dispute(game.players[1])

        self.assertTrue(controller.dispute_open)
        self.assertTrue(controller._resume_clue_selection_after_dispute)

        controller.resolve_dispute()

        self.assertFalse(controller.dispute_open)
        self.assertFalse(controller._resume_clue_selection_after_dispute)
        self.assertIn("PROMPT_SELECT_CLUE", [message for message, _text in game.players[0].waiter.messages])

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

        self.assertEqual(game.players[0].page, "record_answer")
        self.assertEqual(game.players[0].waiter.messages[-1][0], "PROMPT_RECORD_ANSWER_AUTO")

    def test_openai_api_key_prefers_environment(self):
        ai = AutoHostAI({"ai_provider": "openai", "openai_api_key": "saved-key"})

        with patch.dict("os.environ", {"OPENAI_API_KEY": "env-key"}):
            self.assertEqual(ai.api_key(), "env-key")

        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(ai.api_key(), "saved-key")

    def test_fast_judgement_skips_openai_for_exact_match(self):
        game = FakeGame()
        ai = AutoHostAI({"ai_provider": "openai", "openai_api_key": "saved-key"})

        with patch.object(ai, "_openai_judge_answer") as openai_judge:
            judgement = ai.judge_answer(game.active_question, "Who is Ada Lovelace?")

        self.assertTrue(judgement.is_correct)
        self.assertEqual(judgement.confidence, 0.98)
        openai_judge.assert_not_called()

    def test_obvious_wrong_judgement_skips_openai(self):
        game = FakeGame()
        ai = AutoHostAI({"ai_provider": "openai", "openai_api_key": "saved-key"})

        with patch.object(ai, "_openai_judge_answer") as openai_judge:
            judgement = ai.judge_answer(game.active_question, "zzzzzzzz")

        self.assertFalse(judgement.is_correct)
        self.assertEqual(judgement.confidence, 0.97)
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


if __name__ == "__main__":
    unittest.main()
