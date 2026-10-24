"""Exercise team rules through the real game/controller entry points."""
import datetime
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyQt6.QtCore import QObject, QCoreApplication
from jparty.game import Game, Player, Board, FinalBoard
from jparty.controller import BuzzerController, BuzzerSocketHandler
from jparty.auto_host import AutoHostController
from jparty.teams import Team


class TeamGameTests(unittest.TestCase):
    def setUp(self):
        self.app = QCoreApplication.instance() or QCoreApplication([])
        self.game = g = Game.__new__(Game)
        QObject.__init__(g)
        g.init_teams()
        g.team_action_trigger.connect(g.handle_team_action)
        g.players = []
        g.current_round = None
        g.active_question = None
        g.answering_player = None
        g.previous_answerer = []
        g.accepting_responses = False
        g.soliciting_player = False
        g.start_countdown_deadline = None
        g.start_countdown_seconds = 0
        g.start_countdown_players = ()
        g.start_countdown_timer = Mock()
        g.config = {'auto_host': {'enabled': False}, 'allownegative': 'True'}
        g.auto_host = AutoHostController(g)
        g.auto_host.preload_buzz_acknowledgement = Mock()
        g.local_services = SimpleNamespace(ready=True)
        g.dc = Mock()
        g.host_display = Mock()
        g.keystroke_manager = Mock()
        g.timer = Mock()
        g.song_player = Mock()
        g._Game__judgement_round = 0
        g._Game__sorted_players = None
        g.play_sound = Mock()
        controller = BuzzerController.__new__(BuzzerController)
        controller.game = g
        controller.connected_players = g.players
        controller.accepting_players = True
        controller.sockets = set()
        controller.start_votes = set()
        controller.play_again_votes = set()
        g.buzzer_controller = self.controller = controller
        g.configure_teams(True, ['Red', 'Blue'])

    def join(self, name='Ada', team='team-1'):
        handler = SimpleNamespace(player=None, send=Mock(), controller=self.controller,
                                  close=Mock())
        BuzzerSocketHandler.init_player(handler, name, 'Phone Only', name, team)
        return handler

    def roster(self):
        return [self.join('Ada').player, self.join('Ben').player,
                self.join('Cal', 'team-2').player]

    def clue(self):
        g = self.game
        g.active_question = SimpleNamespace(value=200, dd=False, complete=False,
                                            includes_audio=False)
        g.accepting_responses = True
        g.accepting_responses_time = datetime.datetime.now()
        return g.active_question

    def test_socket_thread_registration_waits_for_game_thread(self):
        socket = SimpleNamespace(player=None, send=Mock(), close=Mock(), controller=self.controller)
        thread = threading.Thread(target=BuzzerSocketHandler.init_player,
                                  args=(socket, 'Ada', 'Phone Only', 'Ada', 'team-1'))
        thread.start()
        thread.join(timeout=1)
        self.assertIsNone(socket.player)
        self.app.processEvents()
        self.assertIsNotNone(socket.player)
        self.assertIs(socket.player.team, self.game.teams[0])

    def test_shared_score_and_individual_stats(self):
        ada, ben, cal = self.roster()
        self.game.set_score(ben, 600)
        self.assertEqual((ada.score, ben.score, cal.score), (600, 600, 0))
        ben.stats['correct'] += 1
        self.assertEqual(ada.stats['correct'], 0)
        self.assertEqual(len(self.game.contestants()), 2)
        self.assertEqual(len(self.game.players), 3)

    def test_one_attempt_per_team_and_next_clue_resets(self):
        ada, ben, cal = self.roster()
        self.clue()
        self.game.buzz(0)
        self.assertIs(self.game.answering_player, ada)
        self.game.incorrect_answer()
        self.assertEqual(ben.score, -200)
        self.game.buzz(1)
        self.assertIsNone(self.game.answering_player)
        self.game.buzz(2)
        self.assertIs(self.game.answering_player, cal)
        self.game.answer_given()
        self.game.previous_answerer = []
        self.clue()
        self.game.buzz(1)
        self.assertIs(self.game.answering_player, ben)

    def test_correct_answer_updates_representative_but_wrong_does_not(self):
        ada, ben, cal = self.roster()
        self.clue()
        self.game.back_to_board = Mock()
        self.game.buzz(1)
        self.game.correct_answer()
        self.assertIs(ada.team.representative, ben)
        self.assertEqual(ada.score, 200)
        self.assertIs(self.game.auto_host.player_in_control, ben)
        self.game.previous_answerer = []
        self.clue()
        self.game.buzz(0)
        self.game.incorrect_answer()
        self.assertIs(ada.team.representative, ben)

    def test_representative_stays_when_round_control_changes(self):
        ada, ben, cal = self.roster()
        ada.team.representative = ben
        first = SimpleNamespace(questions=[])
        second = SimpleNamespace(questions=[])
        self.game.current_round = first
        self.game.data = SimpleNamespace(rounds=[first, second])
        self.game.preload_images = Mock()
        ada.score = -200
        self.game.next_round()
        self.assertIs(self.game.auto_host.player_in_control, ben)
        self.assertIs(ada.team.representative, ben)

    def test_early_buzz_timeout_is_individual(self):
        ada, ben, cal = self.roster()
        self.clue()
        ada.istimedout = True
        self.game.buzz(0)
        self.assertIsNone(self.game.answering_player)
        self.game.buzz(1)
        self.assertIs(self.game.answering_player, ben)

    def test_daily_double_buzz_cannot_take_control(self):
        ada, ben, cal = self.roster()
        self.clue().dd = True
        self.game.buzz(1)
        self.assertIsNone(self.game.answering_player)

    def test_team_choices_and_mode_are_frozen_during_play(self):
        ada, ben, cal = self.roster()
        self.game.current_round = object()
        self.assertFalse(self.game.assign_team(ada, 'team-2'))
        self.assertFalse(self.game.configure_teams(False, ['A', 'B']))
        self.assertIs(ada.team, ben.team)

    def test_join_requires_valid_team_and_two_occupied_teams_to_start(self):
        handler = self.join(team='missing')
        self.assertIsNone(handler.player)
        self.assertEqual(len(self.game.players), 0)
        self.join()
        self.assertFalse(self.game.teams_ready())
        self.join('B', 'team-2')
        self.assertTrue(self.game.teams_ready())
        self.game.players.append(Player('Unassigned', 'Phone Only', Mock()))
        self.assertFalse(self.game.teams_ready())

    def test_switching_team_updates_initial_representative(self):
        ada, ben, cal = self.roster()
        self.game.assign_team(ada, 'team-2')
        self.assertIs(ben.team.representative, ben)
        self.assertIs(ada.team.representative, cal)
        self.assertNotIn(ada, ben.team.members)

    def test_removing_team_clears_assignment_for_its_members(self):
        self.game.configure_teams(True, ['Red', 'Blue', 'Green'])
        player = self.join('A', 'team-3').player
        self.game.configure_teams(True, ['Red', 'Blue'])
        self.assertIsNone(player.team)
        self.assertFalse(self.game.teams_ready())

    def test_names_are_validated_and_individual_mode_cap_is_preserved(self):
        self.assertFalse(self.game.configure_teams(True, ['Same', 'Same']))
        self.assertFalse(self.game.configure_teams(True, ['A', ' ']))
        self.assertFalse(self.game.configure_teams(True, ['Only one']))
        self.assertFalse(self.game.configure_teams(True, [str(i) for i in range(9)]))
        self.game.configure_teams(False, ['Red', 'Blue'])
        for i in range(8):
            self.assertIsNotNone(self.join(str(i)).player)
        self.assertIsNone(self.join('Ninth').player)

    def test_team_mode_accepts_32_players_and_rejects_33rd(self):
        for i in range(32):
            self.assertIsNotNone(self.join(str(i), f'team-{1 + i % 2}').player)
        handler = self.join('Extra')
        self.assertIsNone(handler.player)
        handler.send.assert_called_with('FULL')
        self.assertTrue(self.game.teams_ready())
        self.assertFalse(self.game.configure_teams(False, ['Red', 'Blue']))

    def test_repeated_registration_and_late_join_are_rejected(self):
        socket = self.join()
        BuzzerSocketHandler.init_player(socket, 'Again', 'Phone Only', 'Again', 'team-2')
        self.assertEqual(len(self.game.players), 1)
        self.game.current_round = object()
        late = self.join('Late')
        self.assertIsNone(late.player)
        late.send.assert_called_with('GAMESTARTED')

    def test_reconnect_restores_team_shared_score_and_control(self):
        ada, ben, cal = self.roster()
        ben.team.representative = ben
        ben.score = 900
        ben.connected = False
        socket = SimpleNamespace(player=None, controller=self.controller, send=Mock())
        BuzzerSocketHandler.check_if_exists(socket, ben.token.hex(), None)
        self.assertIs(socket.player, ben)
        self.assertTrue(ben.connected)
        state = json.loads(next(c.args[1] for c in socket.send.call_args_list if c.args[0] == 'EXISTS'))
        self.assertEqual(state['team_name'], 'Red')
        self.assertEqual(state['score'], 900)
        self.assertTrue(state['is_representative'])
        self.assertIs(ben.team.representative, ben)

    def test_representative_recovery_moves_pending_team_prompt(self):
        ada, ben, cal = self.roster()
        self.game.auto_host.player_in_control = ada
        ada.page, ada.auto_payload = 'dd_wager', {'max_wager': 1000}
        self.game.current_round = object()
        self.clue().dd = True
        self.game.answering_player = ada
        self.game.transfer_representative(ben)
        self.assertIs(ada.team.representative, ben)
        self.assertIs(self.game.answering_player, ben)
        self.assertIs(self.game.auto_host.player_in_control, ben)
        ben.waiter.send.assert_any_call('PROMPT_DD_WAGER', '1000')
        self.assertEqual(ada.page, 'buzz')

    def test_removing_representative_uses_earliest_remaining_member(self):
        ada, ben, cal = self.roster()
        self.game.remove_player(ada)
        self.assertIs(ben.team.representative, ben)
        self.assertNotIn(ada, self.game.players)
        self.assertEqual(len(ben.team.members), 1)

    def test_setup_change_cancels_start_and_pending_service_probe(self):
        self.roster()
        self.game.valid_game = Mock(return_value=True)
        with patch('jparty.game.time.monotonic', return_value=100):
            self.game.request_start_game()
            self.assertIsNotNone(self.game.start_countdown_deadline)
            self.game.configure_teams(True, ['Renamed', 'Blue'])
        self.assertIsNone(self.game.start_countdown_deadline)
        self.game._start_check_pending = object()
        self.game.assign_team(self.game.players[1], 'team-2')
        self.assertFalse(self.game._start_check_pending)

    def test_lobby_setup_broadcasts_to_unregistered_phones(self):
        class WaitingSocket:
            player = None
            send = Mock()
        socket = WaitingSocket()
        self.controller.sockets.add(socket)
        self.game.configure_teams(True, ['One', 'Two'])
        state = json.loads(socket.send.call_args.args[1])
        self.assertEqual(state['teams'][0]['name'], 'One')
        self.assertFalse(state['joined'])

    def test_final_jeopardy_prompts_once_per_team(self):
        ada, ben, cal = self.roster()
        ada.team.representative = ben
        self.game.current_round = FinalBoard('Final', Mock())
        self.game.start_final()
        self.assertEqual(self.game.final_players(), [ben, cal])
        ben.waiter.send.assert_any_call('PROMPTWAGER', '0')
        self.assertFalse(any(c.args[0] == 'PROMPTWAGER' for c in ada.waiter.send.call_args_list))
        self.controller.prompt_answers()
        ben.waiter.send.assert_any_call('PROMPTANSWER')
        self.assertNotEqual(ada.page, 'answer')

    def test_final_wagers_reject_nonrepresentative_invalid_and_duplicate(self):
        ada, ben, cal = self.roster()
        self.game.current_round = FinalBoard('Final', Mock())
        ada.score = 600
        self.game.start_final()
        self.controller.wager(ben, 200)
        self.assertIsNone(ada.wager)
        self.game.wager(0, 700)
        self.assertIsNone(ada.wager)
        self.game.wager(0, -1)
        self.assertIsNone(ada.wager)
        self.game.wager(0, 400)
        self.game.wager(0, 200)
        self.assertEqual(ben.wager, 400)
        self.game.wager(2, 0)
        self.game.keystroke_manager.activate.assert_called_with('OPEN_FINAL')

    def test_final_answers_reject_nonrepresentative_and_duplicate(self):
        ada, ben, cal = self.roster()
        self.game.current_round = FinalBoard('Final', Mock())
        self.game.start_final()
        self.controller.prompt_answers()
        ben.page = 'answer'  # A forged page alone grants no team authority.
        self.controller.answer(ben, 'Forged')
        self.assertEqual(ada.finalanswer, '')
        self.controller.answer(ada, 'Actual')
        self.controller.answer(ada, 'Stale')
        self.assertEqual(ben.finalanswer, 'Actual')

    def test_final_wager_completion_runs_once_when_nonrepresentative_leaves(self):
        ada, ben, cal = self.roster()
        self.game.config['auto_host']['enabled'] = True
        self.game.current_round = FinalBoard('Final', Mock())
        self.game.auto_host.on_final_wagers_complete = Mock()
        self.game.start_final()
        self.game.wager(0, 0)
        self.game.wager(2, 0)
        self.game.remove_player(ben)
        self.game.auto_host.on_final_wagers_complete.assert_called_once()

    def test_removing_last_eligible_final_team_ends_game(self):
        ada, ben, cal = self.roster()
        self.game.config['allownegativeinfinal'] = 'False'
        self.game.current_round = FinalBoard('Final', Mock())
        ada.score = -200
        self.game.start_final()
        self.game.end_game = Mock()
        self.game.remove_player(cal)
        self.game.end_game.assert_called_once()

    def test_departed_answerer_keeps_team_attempt_and_dispute_ledger(self):
        ada, ben, cal = self.roster()
        self.clue()
        self.game.buzz(0)
        self.game.incorrect_answer()
        self.game.remove_player(ada)
        self.game.buzz(0)  # Ben is now the first player in the connection roster.
        self.assertIsNone(self.game.answering_player)
        self.assertEqual(ben.score, -200)
        self.assertIs(self.game.scoring_contestant(ada), ben.team)

    def test_final_negative_eligibility_applies_to_whole_team(self):
        ada, ben, cal = self.roster()
        ada.score = -200
        self.game.config['allownegativeinfinal'] = 'False'
        self.game.start_final()
        self.assertEqual(self.game.final_players(), [cal])
        self.assertEqual(len(self.game.players), 3)

    def test_final_review_and_winner_use_teams_once(self):
        ada, ben, cal = self.roster()
        ada.score = 500
        cal.score = 300
        ada.wager, cal.wager = 100, 50
        self.game.final_next_player()
        self.assertIs(self.game.answering_player, cal)
        self.game.final_correct_answer()
        self.assertEqual(cal.score, 350)
        self.game.final_next_player()
        self.assertIs(self.game.answering_player, ada)
        self.game.final_correct_answer()
        self.assertEqual(ben.score, 600)
        self.game.final_next_player()
        self.game.dc.final_window.show_winner.assert_called_once_with(ada.team)
        self.game.dc.final_window.show_tie.assert_not_called()

    def test_auto_host_judges_one_final_response_per_team(self):
        ada, ben, cal = self.roster()
        self.game.config['auto_host']['enabled'] = True
        self.game.current_round = FinalBoard('Final', SimpleNamespace(answer='Answer'))
        ada.team.representative = ben
        ben.wager, cal.wager = 100, 50
        ben.finalanswer, cal.finalanswer = 'Answer', 'Answer'
        host = self.game.auto_host
        host._play_text_and_wait = Mock()
        host.ai.judge_answer = Mock(return_value=SimpleNamespace(is_correct=True))
        self.game.auto_final_next_player_trigger.connect(self.game.final_next_player)
        self.game.auto_final_show_answer_trigger.connect(self.game.final_show_answer)
        self.game.auto_final_correct_trigger.connect(self.game.final_correct_answer)
        self.game.auto_final_incorrect_trigger.connect(self.game.final_incorrect_answer)
        with patch('jparty.auto_host.time.sleep'):
            host._judge_final_responses()
        self.assertEqual(host.ai.judge_answer.call_count, 2)
        self.assertEqual((ada.score, ben.score, cal.score), (100, 100, 50))
        self.game.dc.final_window.show_winner.assert_called_once_with(ben.team)

    def test_daily_double_uses_shared_score_and_only_representative_wagers(self):
        ada, ben, cal = self.roster()
        self.game.config['auto_host']['enabled'] = True
        self.game.current_round = SimpleNamespace()
        self.game.data = SimpleNamespace(rounds=[self.game.current_round])
        self.clue().dd = True
        self.game.auto_host.player_in_control = ada
        ada.page = "dd_wager"
        ada.score = 2500
        self.game.auto_host._read_daily_double_clue_then_record = Mock()
        self.game.auto_host.retry_daily_double_wager = Mock()
        self.game.auto_host.apply_daily_double_wager(1, 2000)
        self.assertEqual(self.game.active_question.value, 200)
        self.game.auto_host.apply_daily_double_wager(0, 2000)
        self.assertEqual(self.game.active_question.value, 2000)
        self.game.auto_host.apply_daily_double_wager(0, 3000)
        self.assertEqual(self.game.active_question.value, 2000)

    def test_individual_vote_weight_is_preserved(self):
        ada, ben, cal = self.roster()
        self.game.config['auto_host']['enabled'] = True
        self.assertEqual(self.controller.majority_count(), 2)
        self.controller.play_again_vote(ada)
        self.controller.play_again_vote(ben)
        self.assertEqual(len(self.controller.play_again_votes), 2)
        self.game.auto_host.pending_judgement = {'player': ada, 'judgement': Mock()}
        self.game.auto_host._start_finalize_timer = Mock()
        self.game.auto_host.request_challenge(ada)
        ben.waiter.send.assert_any_call('CHALLENGE_OPEN', json.dumps({'answering_player': 'Ada'}))
        cal.waiter.send.assert_any_call('CHALLENGE_OPEN', json.dumps({'answering_player': 'Ada'}))

    def test_dispute_moving_award_within_team_cannot_duplicate_points(self):
        ada, ben, cal = self.roster()
        ada.score = 200
        host = self.game.auto_host
        host.last_resolved_clue = {'awarded_player': ada, 'value': 200, 'was_correct': True}
        host.apply_dispute_result('player:1')
        self.assertEqual(ada.score, 200)
        self.assertIs(ada.team.representative, ben)

    def test_dispute_restores_wrong_penalty_to_shared_team(self):
        ada, ben, cal = self.roster()
        ada.score = -200
        host = self.game.auto_host
        host.last_resolved_clue = {'awarded_player': None, 'answering_player': ada,
                                  'value': 200, 'was_correct': False}
        host.speak_feedback = Mock()
        host.apply_dispute_result('player:1')
        self.assertEqual(ben.score, 200)

    def test_reset_preserves_mode_and_names_but_clears_team_game_state(self):
        ada, ben, cal = self.roster()
        ada.score, ada.wager, ada.finalanswer = 900, 200, 'Answer'
        self.game.close_game()
        self.assertTrue(self.game.team_mode)
        self.assertEqual([t.name for t in self.game.teams], ['Red', 'Blue'])
        self.assertEqual(self.game.players, [])
        for team in self.game.teams:
            self.assertEqual(team.members, [])
            self.assertIsNone(team.representative)
            self.assertEqual(team.score, 0)
            self.assertIsNone(team.wager)
            self.assertEqual(team.finalanswer, '')


if __name__ == '__main__':
    unittest.main()
