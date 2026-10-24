"""Team settings draft/save behavior and usable controls during a live game."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton

import test_teams
from jparty.constants import DEFAULT_CONFIG
from jparty.local_services import LocalServiceManager
from jparty.welcome_widget import SettingsMenu


class TeamSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.fixture = test_teams.TeamGameTests()
        self.fixture.setUp()
        self.game = self.fixture.game
        self.fixture.roster()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'config.json'
        self.path.write_text(json.dumps(DEFAULT_CONFIG))
        self.game.config = copy.deepcopy(DEFAULT_CONFIG)
        self.game.main_display = Mock()
        self.game.buzzer_controller.player_url = Mock(return_value='http://localhost:8080')
        self.probe = patch('jparty.local_services.check_services', return_value=[])
        self.probe.start()
        self.addCleanup(self.probe.stop)
        self.manager = LocalServiceManager(DEFAULT_CONFIG['auto_host'])
        self.manager.timer.stop()
        self.game.local_services = self.manager
        self.parent = QWidget()
        self.parent.game = self.game
        self.config_patch = patch('jparty.welcome_widget.config_path', str(self.path))
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.dialog = SettingsMenu(self.parent)
        self.panel = self.dialog.team_panel
        self.dialog.tabs.setCurrentIndex(self.dialog.team_tab_index)
        self.dialog.show()
        self.app.processEvents()

    def tearDown(self):
        self.dialog.close()
        self.parent.close()
        self.manager.deleteLater()
        self.app.processEvents()

    def test_own_tab_keeps_local_service_navigation_correct(self):
        titles = [self.dialog.tabs.tabText(i) for i in range(self.dialog.tabs.count())]
        self.assertEqual(titles, ['Game', 'Team mode', 'Auto Host', 'Local Services', 'Images'])
        shortcut = next(b for b in self.dialog.findChildren(QPushButton)
                        if b.text() == 'Manage local services →')
        shortcut.click()
        self.assertEqual(self.dialog.tabs.tabText(self.dialog.tabs.currentIndex()), 'Local Services')

    def test_names_and_toggle_stay_drafts_until_save(self):
        self.panel.names[0].setText('Red Rockets')
        self.panel.enabled.setChecked(False)
        self.assertTrue(self.game.team_mode)
        self.assertEqual(self.game.teams[0].name, 'Red')
        self.assertFalse(self.panel.names[0].isEnabled())
        self.dialog.reject()
        self.assertTrue(self.game.team_mode)
        self.assertEqual(self.game.teams[0].name, 'Red')

    def test_save_applies_team_names_and_broadcasts_new_lobby_state(self):
        self.panel.names[0].setText('Red Rockets')
        before = self.game.roster_version
        self.dialog.save_settings(close=False)
        self.assertEqual(self.game.teams[0].name, 'Red Rockets')
        self.assertGreater(self.game.roster_version, before)
        sent = self.game.players[0].waiter.send.call_args_list
        states = [json.loads(c.args[1]) for c in sent if c.args[0] == 'TEAM_STATE']
        self.assertEqual(states[-1]['team_name'], 'Red Rockets')
        self.assertEqual(self.dialog.settings_feedback.text(), 'Settings saved.')

    def test_invalid_team_names_prevent_partial_settings_save(self):
        before = self.path.read_text()
        self.panel.names[0].setText('Blue')
        self.dialog.save_settings(close=False)
        self.assertIn('different name', self.dialog.settings_feedback.text())
        self.assertEqual(self.dialog.tabs.currentIndex(), self.dialog.team_tab_index)
        self.assertEqual(self.path.read_text(), before)
        self.assertEqual(self.game.teams[0].name, 'Red')
        self.panel.names[0].setText(' ')
        self.assertIn('every team', self.panel.validation_error())

    def test_live_roster_updates_preserve_unsaved_names(self):
        self.panel.names[0].setText('Draft name')
        self.fixture.join('Dee', 'team-2')
        self.assertIn('4 players joined', self.panel.roster_summary.text())
        self.assertEqual(self.panel.names[0].text(), 'Draft name')
        self.assertEqual(self.game.teams[0].name, 'Red')

    def test_controls_lock_during_play_while_roster_remains_available(self):
        self.game.current_round = object()
        self.game.teams_changed.emit()
        self.assertFalse(self.panel.enabled.isEnabled())
        self.assertFalse(self.panel.count.isEnabled())
        self.assertFalse(self.panel.names[0].isEnabled())
        self.assertTrue(self.panel.roster_button.isEnabled())
        self.assertIn('locked during play', self.panel.lock_notice.text())
        self.assertEqual(self.panel.validation_error(), '')

    def test_team_count_limits_keyboard_toggle_and_compact_layout(self):
        self.assertFalse(self.panel.minus.isEnabled())
        self.panel.count.setValue(8)
        self.assertFalse(self.panel.plus.isEnabled())
        self.assertTrue(all(row.isVisible() for row in self.panel.team_rows))
        self.dialog.resize(720, 570)
        self.app.processEvents()
        scroll = self.dialog.tabs.currentWidget()
        self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
        self.panel.enabled.setFocus()
        QTest.keyClick(self.panel.enabled, Qt.Key.Key_Space)
        self.assertFalse(self.panel.enabled.isChecked())
        self.assertTrue(self.game.team_mode)


if __name__ == '__main__':
    unittest.main()
