"""Real HTTP/WebSocket contracts for team phone sessions."""
import json
from types import SimpleNamespace

from tornado.testing import AsyncHTTPTestCase, gen_test
from tornado.websocket import websocket_connect

import test_teams
from jparty.controller import Application
from jparty.game import FinalBoard


class TeamSocketTests(AsyncHTTPTestCase):
    def get_app(self):
        self.fixture = test_teams.TeamGameTests()
        self.fixture.setUp()
        self.game = self.fixture.game
        self.controller = self.fixture.controller
        self.clients = []
        return Application(self.controller)

    def tearDown(self):
        for client in self.clients:
            client.close()
        super().tearDown()

    async def connect(self):
        client = await websocket_connect(self.get_url('/buzzersocket').replace('http:', 'ws:'))
        self.clients.append(client)
        return client

    async def read_until(self, client, message):
        for _ in range(100):
            data = json.loads(await client.read_message())
            if data['message'] == message:
                return data['text']
        self.fail(f'Did not receive {message}')

    async def join(self, name, team):
        client = await self.connect()
        client.write_message(json.dumps({'message': 'NAME', 'text': name,
                                         'buzzerColor': 'Phone Only', 'displayName': name,
                                         'team_id': team}))
        token = await self.read_until(client, 'TOKEN')
        state = json.loads(await self.read_until(client, 'TEAM_STATE'))
        return client, token, state

    def test_phone_page_contains_team_controls(self):
        response = self.fetch('/')
        self.assertEqual(response.code, 200)
        self.assertIn(b'id="join-team"', response.body)
        self.assertIn(b'id="team-banner"', response.body)

    @gen_test
    async def test_multiple_sessions_team_switch_shared_score_and_reconnect(self):
        ada, token, state = await self.join('Ada', 'team-1')
        ben, _, _ = await self.join('Ben', 'team-1')
        cal, _, _ = await self.join('Cal', 'team-2')
        self.assertTrue(state['is_representative'])
        self.game.set_score(self.game.players[0], 600)
        # Drain queued earlier roster snapshots until the shared score arrives.
        for client in [ada, ben]:
            while True:
                state = json.loads(await self.read_until(client, 'TEAM_STATE'))
                if state['score'] == 600:
                    break
            self.assertEqual(state['team_name'], 'Red')
        ben.write_message(json.dumps({'message': 'CHANGE_TEAM', 'text': 'team-2'}))
        while True:
            state = json.loads(await self.read_until(ben, 'TEAM_STATE'))
            if state['team_id'] == 'team-2':
                break
        self.assertEqual(state['score'], 0)
        ada.close()
        reconnected = await self.connect()
        reconnected.write_message(json.dumps({'message': 'CHECK_IF_EXISTS', 'text': token}))
        state = json.loads(await self.read_until(reconnected, 'EXISTS'))
        self.assertEqual(state['score'], 600)
        self.assertEqual(state['team_id'], 'team-1')
        self.assertTrue(state['is_representative'])
        self.assertEqual(len(self.game.players), 3)

    @gen_test
    async def test_32_live_phone_sessions_and_capacity_rejection(self):
        for i in range(32):
            _, _, state = await self.join(f'Player {i+1}', f'team-{1 + i % 2}')
            self.assertTrue(state['joined'])
        self.assertEqual(len(self.game.players), 32)
        extra = await self.connect()
        extra.write_message(json.dumps({'message': 'NAME', 'text': 'Extra',
                                        'buzzerColor': 'Phone Only', 'team_id': 'team-1'}))
        await self.read_until(extra, 'FULL')
        self.assertEqual(len(self.game.players), 32)

    @gen_test
    async def test_unregistered_sessions_receive_setup_changes(self):
        client = await self.connect()
        client.write_message(json.dumps({'message': 'CHECK_IF_EXISTS', 'text': ''}))
        state = json.loads(await self.read_until(client, 'NEW'))
        self.assertTrue(state['team_mode'])
        self.game.configure_teams(True, ['New Red', 'New Blue'])
        state = json.loads(await self.read_until(client, 'TEAM_STATE'))
        self.assertEqual(state['teams'][0]['name'], 'New Red')
        self.assertFalse(state['joined'])

    @gen_test
    async def test_running_game_rejects_joins_team_changes_and_forged_final_actions(self):
        ada, _, _ = await self.join('Ada', 'team-1')
        ben, _, _ = await self.join('Ben', 'team-1')
        cal, _, _ = await self.join('Cal', 'team-2')
        self.game.current_round = FinalBoard('Final', SimpleNamespace())
        self.controller.accepting_players = False
        self.game.start_final()
        await self.read_until(ada, 'PROMPTWAGER')
        ben.write_message(json.dumps({'message': 'WAGER', 'text': '500'}))
        ben.write_message(json.dumps({'message': 'CHANGE_TEAM', 'text': 'team-2'}))
        await self.read_until(ben, 'TEAM_ERROR')
        self.assertIsNone(self.game.players[0].wager)
        self.assertIs(self.game.players[1].team, self.game.teams[0])
        late = await self.connect()
        late.write_message(json.dumps({'message': 'NAME', 'text': 'Late', 'buzzerColor': 'Phone Only', 'team_id': 'team-1'}))
        await self.read_until(late, 'GAMESTARTED')
        self.assertEqual(len(self.game.players), 3)

    @gen_test
    async def test_auto_host_selection_is_sent_only_to_representative(self):
        ada, _, _ = await self.join('Ada', 'team-1')
        ben, _, _ = await self.join('Ben', 'team-1')
        cal, _, _ = await self.join('Cal', 'team-2')
        self.game.config['auto_host']['enabled'] = True
        self.game.auto_host.player_in_control = self.game.players[0]
        self.game.auto_host.board_payload = lambda: {'categories': ['Test'], 'clues': []}
        self.game.auto_host.prompt_clue_selection()
        payload = json.loads(await self.read_until(ada, 'PROMPT_SELECT_CLUE'))
        self.assertIn('categories', payload)
        self.assertEqual(self.game.players[1].page, 'buzz')
        self.assertEqual(self.game.players[2].page, 'buzz')
        self.game.transfer_representative(self.game.players[1])
        await self.read_until(ben, 'PROMPT_SELECT_CLUE')
        self.assertEqual(self.game.players[0].page, 'buzz')

    @gen_test
    async def test_phone_creates_team_atomically_and_waiting_phones_can_join_it(self):
        self.game.configure_teams(True)
        waiting = await self.connect()
        creator = await self.connect()
        creator.write_message(json.dumps({'message': 'NAME', 'text': 'Ada signature',
            'displayName': 'Ada', 'buzzerColor': 'Phone Only',
            'new_team': {'name': 'BUZZ Rockets', 'signature': test_teams.team_drawing()}}))
        token = await self.read_until(creator, 'TOKEN')
        state = json.loads(await self.read_until(creator, 'TEAM_STATE'))
        available = json.loads(await self.read_until(waiting, 'TEAM_STATE'))
        self.assertEqual(available['teams'][0]['name'], 'BUZZ Rockets')
        self.assertTrue(state['is_representative'])
        teammate, _, teammate_state = await self.join('Ben', state['team_id'])
        self.assertEqual(teammate_state['team_name'], 'BUZZ Rockets')
        self.assertEqual(len(self.game.players), 2)
        self.assertEqual(self.game.players[0].name, 'Ada signature')
        self.assertEqual(self.game.teams[0].signature, test_teams.team_drawing())
        creator.close()
        returning = await self.connect()
        returning.write_message(json.dumps({'message': 'CHECK_IF_EXISTS', 'text': token}))
        restored = json.loads(await self.read_until(returning, 'EXISTS'))
        self.assertEqual(restored['team_id'], state['team_id'])
        self.assertTrue(restored['is_representative'])

    @gen_test
    async def test_two_creators_with_same_name_get_one_team_and_can_retry_as_teammates(self):
        self.game.configure_teams(True)
        first, second = await self.connect(), await self.connect()
        for client, name in [(first, 'Ada'), (second, 'Ben')]:
            client.write_message(json.dumps({'message': 'NAME', 'text': name, 'displayName': name,
                'new_team': {'name': 'Same Team', 'signature': test_teams.team_drawing()}}))
        await self.read_until(first, 'TOKEN')
        error = await self.read_until(second, 'TEAM_ERROR')
        self.assertIn('already exists', error)
        self.assertEqual(len(self.game.teams), 1)
        self.assertEqual(len(self.game.players), 1)
        second.write_message(json.dumps({'message': 'NAME', 'text': 'Ben', 'displayName': 'Ben',
                                        'team_id': self.game.teams[0].id}))
        await self.read_until(second, 'TOKEN')
        self.assertEqual(len(self.game.players), 2)
        self.assertIs(self.game.players[0].team, self.game.players[1].team)
