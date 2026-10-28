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
        self.path.write_text(json.dumps({**DEFAULT_CONFIG, 'team_mode': True}))
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

    def test_auto_host_defaults_off_and_keyboard_toggle_saves_with_restart(self):
        self.assertFalse(self.dialog.auto_host_toggle.isChecked())
        self.assertIn('Off', self.dialog.auto_host_toggle_status.text())
        self.dialog.tabs.setCurrentIndex(2)
        self.dialog.auto_host_toggle.setFocus()
        QTest.keyClick(self.dialog.auto_host_toggle, Qt.Key.Key_Space)
        self.assertTrue(self.dialog.auto_host_toggle.isChecked())
        self.assertIn('On', self.dialog.auto_host_toggle_status.text())
        with patch('jparty.welcome_widget.os.execv') as restart:
            self.dialog.save_settings(close=False)
        restart.assert_called_once()
        self.assertTrue(json.loads(self.path.read_text())['auto_host']['enabled'])

    def test_auto_host_keeps_existing_enabled_preference(self):
        self.dialog.close()
        config = copy.deepcopy(DEFAULT_CONFIG)
        config['team_mode'] = True
        config['auto_host']['enabled'] = True
        self.path.write_text(json.dumps(config))
        self.dialog = SettingsMenu(self.parent)
        self.assertTrue(self.dialog.auto_host_toggle.isChecked())

    def test_personal_voice_selection_requests_access_and_reports_native_result(self):
        dialog = self.dialog
        dialog.auto_host_provider_combobox.setCurrentIndex(dialog.auto_host_provider_combobox.findData('local'))
        dialog.local_tts_preset_combobox.setCurrentIndex(dialog.local_tts_preset_combobox.findData('macos_say'))
        dialog.macos_tts_voice_combobox.setCurrentIndex(dialog.macos_tts_voice_combobox.findData('__custom__'))
        with patch('jparty.welcome_widget.sys.platform', 'darwin'), \
                patch.object(dialog.personal_voice_access, 'request') as request:
            dialog.macos_tts_voice_combobox.activated.emit(dialog.macos_tts_voice_combobox.currentIndex())
            request.assert_called_once()
            self.assertFalse(dialog.personal_voice_button.isEnabled())
            dialog.personal_voice_access.changed.emit({'status': 'authorized', 'voices': ['My Voice']})
            self.assertTrue(dialog.personal_voice_button.isEnabled())
            self.assertIn('My Voice', dialog.personal_voice_status.text())
            dialog.personal_voice_access.changed.emit({'status': 'denied', 'voices': []})
            self.assertIn('Accessibility → Personal Voice', dialog.personal_voice_status.text())
        dialog.local_tts_preset_combobox.setCurrentIndex(dialog.local_tts_preset_combobox.findData('kokoro'))
        self.assertTrue(dialog.personal_voice_button.isHidden())

    def test_update_preference_is_draft_then_persisted_without_restart(self):
        self.assertTrue(self.dialog.update_check_toggle.isChecked())
        self.dialog.update_check_toggle.setChecked(False)
        self.assertTrue(self.dialog.update_manager.automatic_check)
        with patch('jparty.welcome_widget.os.execv') as restart:
            self.dialog.save_settings(close=False)
        restart.assert_not_called()
        self.assertFalse(json.loads(self.path.read_text())['updates']['automatic_check'])
        self.assertFalse(self.dialog.update_manager.automatic_check)

    def test_restart_settings_wait_for_active_download(self):
        self.dialog.update_manager.status = 'downloading'
        self.dialog.auto_host_toggle.setChecked(True)
        with patch('jparty.welcome_widget.os.execv') as restart:
            self.dialog.save_settings(close=False)
        restart.assert_not_called()
        self.assertFalse(json.loads(self.path.read_text())['auto_host']['enabled'])
        self.assertIn('download', self.dialog.settings_feedback.text())

    def test_own_tab_keeps_local_service_navigation_correct(self):
        titles = [self.dialog.tabs.tabText(i) for i in range(self.dialog.tabs.count())]
        self.assertEqual(titles, ['Game', 'Team mode', 'Auto Host', 'Local Services', 'Images'])
        shortcut = next(b for b in self.dialog.findChildren(QPushButton)
                        if b.text() == 'Manage local services →')
        shortcut.click()
        self.assertEqual(self.dialog.tabs.tabText(self.dialog.tabs.currentIndex()), 'Local Services')

    def test_toggle_stays_a_draft_and_host_cannot_edit_team_names(self):
        self.panel.enabled.setChecked(False)
        self.assertTrue(self.game.team_mode)
        self.assertEqual(self.game.teams[0].name, 'Red')
        self.assertFalse(hasattr(self.panel, 'names'))
        self.dialog.reject()
        self.assertTrue(self.game.team_mode)

    def test_mode_save_persists_and_restarts_clearing_lobby_teams(self):
        self.panel.enabled.setChecked(False)
        with patch('jparty.welcome_widget.os.execv') as restart:
            self.dialog.save_settings(close=False)
        restart.assert_called_once()
        self.assertFalse(json.loads(self.path.read_text())['team_mode'])
        self.assertFalse(self.game.team_mode)
        self.assertEqual(self.game.teams, [])

    def test_unchanged_mode_saves_without_restarting_or_rewriting_teams(self):
        with patch('jparty.welcome_widget.os.execv') as restart:
            self.dialog.save_settings(close=False)
        restart.assert_not_called()
        self.assertTrue(json.loads(self.path.read_text())['team_mode'])
        self.assertEqual(self.game.teams[0].name, 'Red')
        self.assertEqual(self.dialog.settings_feedback.text(), 'Settings saved.')

    def test_enabling_team_mode_restarts_and_is_loaded_by_next_game(self):
        from PyQt6.QtCore import QObject
        from jparty.game import Game
        self.dialog.close()
        self.game.configure_teams(False)
        self.path.write_text(json.dumps({**DEFAULT_CONFIG, 'team_mode': False}))
        self.dialog = SettingsMenu(self.parent)
        self.panel = self.dialog.team_panel
        self.panel.enabled.setChecked(True)
        with patch('jparty.welcome_widget.os.execv') as restart:
            self.dialog.save_settings(close=False)
        restart.assert_called_once()
        next_game = Game.__new__(Game)
        QObject.__init__(next_game)
        next_game.config = json.loads(self.path.read_text())
        next_game.init_teams()
        self.assertTrue(next_game.team_mode)
        self.assertEqual(next_game.teams, [])

    def test_live_game_prevents_partial_mode_save(self):
        before = self.path.read_text()
        self.game.current_round = object()
        self.panel.enabled.setChecked(False)
        self.dialog.save_settings(close=False)
        self.assertIn('locked during play', self.dialog.settings_feedback.text())
        self.assertEqual(self.path.read_text(), before)
        self.assertTrue(self.game.team_mode)

    def test_live_roster_updates_preserve_unsaved_toggle(self):
        self.panel.enabled.setChecked(False)
        self.fixture.join('Dee', 'team-2')
        self.assertIn('4 players joined', self.panel.roster_summary.text())
        self.assertFalse(self.panel.enabled.isChecked())
        self.assertTrue(self.game.team_mode)

    def test_controls_lock_during_play_while_roster_remains_available(self):
        self.game.current_round = object()
        self.game.teams_changed.emit()
        self.assertFalse(self.panel.enabled.isEnabled())
        self.assertTrue(self.panel.roster_button.isEnabled())
        self.assertIn('locked during play', self.panel.lock_notice.text())
        self.assertEqual(self.panel.validation_error(), '')

    def test_compact_layout_and_keyboard_toggle(self):
        self.dialog.resize(720, 570)
        self.app.processEvents()
        self.assertEqual(self.dialog.tabs.currentWidget().horizontalScrollBar().maximum(), 0)
        self.panel.enabled.setFocus()
        QTest.keyClick(self.panel.enabled, Qt.Key.Key_Space)
        self.assertFalse(self.panel.enabled.isChecked())
        self.assertTrue(self.game.team_mode)
        self.assertIn('restarts JParty', self.panel.lock_notice.text())

    def test_frozen_restart_does_not_repeat_executable_argument(self):
        import sys
        self.panel.enabled.setChecked(False)
        with patch('jparty.welcome_widget.sys.frozen', True, create=True), \
                patch('jparty.welcome_widget.sys.argv', ['/Applications/JParty.app/Contents/MacOS/JParty']), \
                patch('jparty.welcome_widget.os.execv') as restart:
            self.dialog.save_settings(close=False)
        restart.assert_called_once_with(sys.executable, [sys.executable])


if __name__ == '__main__':
    unittest.main()
