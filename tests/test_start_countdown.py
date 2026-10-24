import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyQt6.QtCore import QObject
from jparty.controller import BuzzerController, BuzzerSocketHandler
from jparty.game import Game


class StartCountdownTests(unittest.TestCase):
    def setUp(self):
        self.players = [SimpleNamespace(waiter=Mock()), SimpleNamespace(waiter=Mock())]
        self.game = Game.__new__(Game)
        QObject.__init__(self.game)
        self.game.current_round = None
        self.game.players = self.players
        self.game.init_teams()
        self.game.auto_host = SimpleNamespace(enabled=True)
        self.game.local_services = SimpleNamespace(ready=True)
        self.game.buzzer_controller = SimpleNamespace(connected_players=self.players)
        self.game.start_countdown_deadline = None
        self.game.start_countdown_players = ()
        self.game.start_countdown_seconds = 0
        self.game.start_countdown_timer = Mock()
        self.game.startable = Mock(return_value=True)
        self.game.start_game = Mock()
        self.clock = patch('jparty.game.time.monotonic', return_value=100)
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)

    def last_state(self, player=0):
        message, payload = self.players[player].waiter.send.call_args.args
        self.assertEqual(message, 'START_GAME_COUNTDOWN')
        return json.loads(payload)

    def test_shared_countdown_starts_once_after_three_seconds(self):
        self.game.request_start_game()
        self.assertEqual(self.last_state()['seconds_remaining'], 3)
        self.assertEqual(self.last_state(1)['seconds_remaining'], 3)
        self.now.return_value = 101
        self.game.request_start_game()  # A second click cannot extend the timer.
        self.game.update_start_countdown()
        self.assertEqual(self.last_state()['seconds_remaining'], 2)
        self.now.return_value = 102
        self.game.update_start_countdown()
        self.assertEqual(self.last_state()['seconds_remaining'], 1)
        self.now.return_value = 102.99
        self.game.update_start_countdown()
        self.game.start_game.assert_not_called()
        self.now.return_value = 103
        self.game.update_start_countdown()
        self.game.update_start_countdown()
        self.game.start_game.assert_called_once()

    def test_cancel_prevents_start_and_allows_fresh_countdown(self):
        self.game.request_start_game()
        self.game.cancel_start_game()
        self.assertEqual(self.last_state()['seconds_remaining'], 0)
        self.assertTrue(self.last_state()['can_start_game'])
        self.now.return_value = 110
        self.game.update_start_countdown()
        self.game.start_game.assert_not_called()
        self.game.request_start_game()
        self.assertEqual(self.game.start_countdown_deadline, 113)

    def test_new_player_cancels_even_before_join_signal_is_processed(self):
        self.game.request_start_game()
        self.players.append(SimpleNamespace(waiter=Mock()))
        self.now.return_value = 103
        self.game.update_start_countdown()
        self.game.start_game.assert_not_called()
        self.assertIsNone(self.game.start_countdown_deadline)
        self.assertIn('cancelled', self.last_state(2)['message'])

    def test_not_ready_or_already_started_cannot_begin_countdown(self):
        self.game.startable.return_value = False
        self.game.request_start_game()
        self.assertIsNone(self.game.start_countdown_deadline)
        self.game.startable.return_value = True
        self.game.current_round = object()
        self.game.request_start_game()
        self.assertIsNone(self.game.start_countdown_deadline)

    def test_game_becoming_invalid_cancels_countdown(self):
        self.game.request_start_game()
        self.game.startable.return_value = False
        self.now.return_value = 103
        self.game.update_start_countdown()
        self.game.start_game.assert_not_called()
        self.assertIsNone(self.game.start_countdown_deadline)

    def test_any_joined_player_can_start_or_cancel_without_majority(self):
        controller = BuzzerController.__new__(BuzzerController)
        controller.game = self.game
        controller.accepting_players = True
        controller.connected_players = self.players
        self.game.auto_start_game_trigger.connect(self.game.request_start_game)
        self.game.cancel_start_game_trigger.connect(self.game.cancel_start_game)
        controller.start_game_vote(self.players[0])
        self.assertEqual(self.game.start_countdown_seconds, 3)
        controller.cancel_start_game(self.players[1])
        self.assertEqual(self.game.start_countdown_seconds, 0)
        controller.start_game_vote(None)
        controller.cancel_start_game(None)
        self.assertIsNone(self.game.start_countdown_deadline)

    def test_manual_host_countdown_can_be_cancelled_with_auto_host_off(self):
        self.game.auto_host.enabled = False
        self.game.request_start_game()
        self.assertEqual(self.last_state()['seconds_remaining'], 3)
        self.assertFalse(self.last_state()['can_start_game'])
        self.game.cancel_start_game()
        self.assertEqual(self.last_state()['seconds_remaining'], 0)

    def test_reconnected_player_receives_active_countdown(self):
        self.game.request_start_game()
        player = self.players[0]
        player.score = 0
        player.state = Mock(return_value={"page": "buzz", "score": 0})
        controller = SimpleNamespace(
            game=self.game, accepting_players=True,
            player_with_token=Mock(return_value=player),
        )
        socket = SimpleNamespace(controller=controller, send=Mock())
        BuzzerSocketHandler.check_if_exists(socket, 'existing-token', None)
        message, payload = socket.send.call_args.args
        self.assertEqual(message, 'START_GAME_COUNTDOWN')
        self.assertEqual(json.loads(payload)['seconds_remaining'], 3)
        self.assertIs(socket.player, player)

    def test_live_service_loss_cancels_countdown(self):
        self.game.request_start_game()
        self.game.local_services.ready = False
        self.game._auto_host_services_changed()
        self.assertIsNone(self.game.start_countdown_deadline)
        self.assertFalse(self.last_state()['can_start_game'])
        self.game.start_game.assert_not_called()

    def test_service_readiness_is_part_of_game_startability(self):
        self.game.valid_game = Mock(return_value=True)
        self.game.local_services.ready = False
        self.assertFalse(Game.startable(self.game))
        self.game.auto_host.enabled = False
        self.assertTrue(Game.startable(self.game))

    def test_direct_start_cannot_bypass_offline_services(self):
        self.game.local_services.ready = False
        Game.start_game(self.game)
        self.assertIsNone(self.game.current_round)
        self.assertIn('not ready', self.last_state()['message'])

    def test_final_live_probe_prevents_start_if_a_service_has_stopped(self):
        callbacks = []
        self.game.local_services.refresh = lambda callback: callbacks.append(callback)
        Game.start_game(self.game)
        self.assertEqual(len(callbacks), 1)
        self.assertTrue(self.last_state()['checking_services'])
        self.game.local_services.ready = False
        self.game.startable.return_value = False
        callbacks[0]()
        self.game.start_game.assert_not_called()

    def test_final_probe_can_be_cancelled_before_it_returns(self):
        callbacks = []
        self.game.local_services.refresh = lambda callback: callbacks.append(callback)
        Game.start_game(self.game)
        self.game.cancel_start_game()
        callbacks[0]()
        self.game.start_game.assert_not_called()

    def test_final_probe_starts_once_when_still_ready(self):
        callbacks = []
        self.game.local_services.refresh = lambda callback: callbacks.append(callback)
        Game.start_game(self.game)
        callbacks[0]()
        self.game.start_game.assert_called_once_with(services_verified=True)

    def test_joining_player_receives_offline_service_state(self):
        self.game.local_services.ready = False
        controller = SimpleNamespace(accepting_players=True, connected_players=self.players,
                                     game=self.game, new_player=Mock())
        self.game.buzzer_controller = controller
        self.game.new_player = Mock()
        self.game.team_action_trigger.connect(self.game.handle_team_action)
        socket = SimpleNamespace(controller=controller, player=None, send=Mock())
        BuzzerSocketHandler.init_player(socket, 'Ada', '#ffffff')
        message, payload = socket.send.call_args.args
        self.assertEqual(message, 'START_GAME_COUNTDOWN')
        self.assertFalse(json.loads(payload)['can_start_game'])


if __name__ == '__main__':
    unittest.main()
