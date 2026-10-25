"""A team podium keeps team identity while showing the current person's signature."""
import os
from types import SimpleNamespace
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import QApplication, QWidget
from jparty.game import Player
from jparty.scoreboard import ScoreBoard
from jparty.teams import Team
from jparty.utils import resource_path
from test_teams import team_drawing


class TeamPodiumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        QFontDatabase.addApplicationFont(resource_path('board_font.ttf'))

    def test_team_identity_and_answering_signature_are_separate_and_clear(self):
        ada = Player(team_drawing(), 'Phone Only', None, 'Ada')
        team = Team('red', 'Red Rockets', members=[ada], representative=ada, signature=team_drawing())
        ada.team = team
        game = SimpleNamespace(answering_player=None, contestants=lambda: [team])
        window = QWidget()
        window.host = lambda: False
        container = QWidget(window)
        board = ScoreBoard(game, container)
        board.resize(800, 400)
        board.refresh_players()
        podium = board.player_widgets[0]
        self.assertEqual(podium.team_caption.text(), 'Red Rockets')
        self.assertIsNotNone(podium.name_label.signature)
        self.assertIsNone(podium.member_signature.signature)
        game.answering_player = ada
        board.refresh_players()
        self.assertEqual(podium.member_label.text(), 'Answering: Ada')
        self.assertIsNotNone(podium.member_signature.signature)
        game.answering_player = None
        board.refresh_players()
        self.assertIsNone(podium.member_signature.signature)
        self.assertEqual(podium.member_signature.text(), '')
        self.assertEqual(podium.team_caption.text(), 'Red Rockets')
        window.close()
        window.deleteLater()
