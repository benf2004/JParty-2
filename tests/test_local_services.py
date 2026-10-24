import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtTest import QTest

from jparty.constants import DEFAULT_CONFIG
from jparty.local_services import LocalServiceManager, check_services, script_environment
from jparty.welcome_widget import SettingsMenu


READY = [{'name': 'Text generation', 'endpoint': 'http://localhost:11434/v1', 'ready': True, 'detail': 'Ready'}]


class ServiceProbeTests(unittest.TestCase):
    def test_checks_local_stack_and_selected_kev_model(self):
        def get(url, **kwargs):
            payload = {'models': [{'name': 'kev-latest'}]} if ':8009/' in url else {'data': [{'id': 'qwen2.5:7b'}]}
            return Mock(json=Mock(return_value=payload))
        with patch('jparty.local_services.requests.get', side_effect=get) as request:
            rows = check_services({'ai_provider': 'local', 'judge_provider': 'kev'})
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(row['ready'] for row in rows))
        self.assertEqual({call.args[0] for call in request.call_args_list}, {
            'http://localhost:11434/v1/models', 'http://localhost:8082/',
            'http://localhost:8880/v1/audio/voices', 'http://localhost:8009/v1/models',
        })

    def test_reachable_server_without_selected_model_is_not_ready(self):
        with patch('jparty.local_services.requests.get', return_value=Mock(json=Mock(return_value={'data': []}))):
            rows = check_services({'ai_provider': 'local'})
        self.assertFalse(rows[0]['ready'])
        self.assertIn('not loaded', rows[0]['detail'])

    def test_failures_are_reported_per_component(self):
        with patch('jparty.local_services.requests.get', side_effect=TimeoutError):
            rows = check_services({'ai_provider': 'local'})
        self.assertFalse(any(row['ready'] for row in rows))

    def test_manual_or_cloud_provider_does_not_require_local_servers(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': ''}), patch('jparty.local_services.requests.get') as request:
            self.assertFalse(check_services({'ai_provider': 'openai', 'judge_provider': 'default'})[0]['ready'])
            self.assertTrue(check_services({'ai_provider': 'openai', 'judge_provider': 'default', 'openai_api_key': 'test'})[0]['ready'])
            request.assert_not_called()

    def test_environment_is_noninteractive_and_matches_settings(self):
        env = script_environment({'ai_provider': 'local', 'judge_provider': 'kev',
                                  'local_stt_base_url': 'http://127.0.0.1:9002/v1',
                                  'local_tts_voice': 'A personal voice'})
        self.assertEqual(env['JPARTY_LOCAL_STT_PORT'], '9002')
        self.assertEqual(env['JPARTY_LOCAL_KEV_ENABLED'], '1')
        self.assertEqual(env['JPARTY_LOCAL_TTS_ENGINE'], 'macos')
        self.assertEqual(env['JPARTY_NONINTERACTIVE'], '1')
        self.assertEqual(env['JPARTY_MACOS_TTS_VOICE'], 'A personal voice')

    def test_custom_servers_are_not_silently_reconfigured(self):
        for config in [{'local_stt_base_url': 'https://example.com/v1'},
                       {'local_llm_base_url': 'http://localhost:9000/v1'},
                       {'local_tts_preset': 'custom'}]:
            with self.subTest(config=config), self.assertRaises(ValueError):
                script_environment(config)


class ServiceGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.probe_patch = patch('jparty.local_services.check_services', return_value=copy.deepcopy(READY))
        self.probe_patch.start()
        self.addCleanup(self.probe_patch.stop)
        self.manager = LocalServiceManager({'ai_provider': 'local'})
        self.manager.timer.stop()

    def tearDown(self):
        if self.manager.process.state() != self.manager.process.ProcessState.NotRunning:
            self.manager.process.kill()
            self.manager.process.waitForFinished(1000)
        self.manager.deleteLater()
        self.app.processEvents()

    def spin(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate())

    def test_initial_unknown_blocks_until_live_probe_finishes_and_status_expires(self):
        self.assertFalse(self.manager.ready)
        self.manager.refresh()
        self.spin(lambda: self.manager.ready)
        self.manager.checked_at = time.monotonic() - 11
        self.assertFalse(self.manager.ready)

    def test_config_changes_invalidate_previous_readiness(self):
        self.manager.results = copy.deepcopy(READY)
        self.manager.checked_at = time.monotonic()
        self.assertTrue(self.manager.ready)
        self.manager.configure({'ai_provider': 'local', 'local_llm_model': 'another-model'})
        self.assertFalse(self.manager.ready)
        self.spin(lambda: self.manager.ready)

    def test_script_runs_asynchronously_and_retains_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            scripts = Path(directory) / 'scripts'
            scripts.mkdir()
            (scripts / 'start_full_local_auto_host_macos.sh').write_text(
                'echo "launch:$JPARTY_LOCAL_KEV_ENABLED:$JPARTY_LOCAL_TTS_ENGINE"\nsleep 0.1\necho finished\n')
            with patch('jparty.local_services.root', directory), patch('jparty.local_services.sys.platform', 'darwin'):
                self.manager.run('start', {'ai_provider': 'local', 'judge_provider': 'kev'})
                self.assertTrue(self.manager.busy)
                self.assertFalse(self.manager.ready)
                self.spin(lambda: not self.manager.busy)
                self.assertIn('launch:1:macos', self.manager.log)
                self.assertIn('finished', self.manager.log)

    def test_script_failure_stays_visible_after_status_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            scripts = Path(directory) / 'scripts'
            scripts.mkdir()
            (scripts / 'setup_full_local_auto_host_macos.sh').write_text('echo "installation failed"\nexit 2\n')
            with patch('jparty.local_services.root', directory), patch('jparty.local_services.sys.platform', 'darwin'):
                self.manager.run('setup', {'ai_provider': 'local'})
                self.spin(lambda: not self.manager.busy and not self.manager.checking)
                self.assertIn('exit 2', self.manager.message)
                self.assertIn('installation failed', self.manager.log)

    def test_tabs_settings_persistence_and_unsaved_action_guard(self):
        from jparty import welcome_widget as module
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            config = copy.deepcopy(DEFAULT_CONFIG)
            config['auto_host'].update(ai_provider='local', judge_provider='kev')
            config['image_fallback']['use_pexels'] = True
            path.write_text(json.dumps(config))
            parent = QWidget()
            parent.game = Mock(config=config, local_services=self.manager)
            with patch.object(module, 'config_path', str(path)), patch.object(module.os, 'execv') as restart:
                dialog = SettingsMenu(parent)
                dialog.show()
                self.app.processEvents()
                self.assertEqual(dialog.tabs.count(), 5)
                self.assertIs(dialog.services_panel.manager, self.manager)
                self.assertEqual(dialog.service_action_config()['judge_provider'], 'kev')
                dialog.auto_host_provider_combobox.setCurrentIndex(dialog.auto_host_provider_combobox.findData("openai"))
                dialog.judge_provider_combobox.setCurrentIndex(dialog.judge_provider_combobox.findData("local_binary"))
                self.assertFalse(dialog.llm_group.isHidden())
                self.assertFalse(dialog.local_llm_model_input.isHidden())
                self.assertTrue(dialog.stt_group.isHidden())
                dialog.local_llm_model_input.setText('another-model')
                with self.assertRaises(ValueError):
                    dialog.service_action_config()
                dialog.save_settings(close=False)
                self.assertEqual(dialog.service_action_config()['local_llm_model'], 'another-model')
                self.assertEqual(json.loads(path.read_text())['auto_host']['local_llm_model'], 'another-model')
                self.assertTrue(json.loads(path.read_text())['image_fallback']['use_pexels'])
                restart.assert_not_called()
                dialog.close()

    def test_invalid_timeout_does_not_crash_save(self):
        from jparty import welcome_widget as module
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            path.write_text(json.dumps(DEFAULT_CONFIG))
            parent = QWidget()
            parent.game = Mock(local_services=self.manager)
            with patch.object(module, 'config_path', str(path)):
                dialog = SettingsMenu(parent)
                dialog.earlybuzztimeout_combobox.setText('invalid')
                dialog.save_settings(close=False)
                self.assertIn('must be a number', dialog.settings_feedback.text())
                dialog.close()


if __name__ == '__main__':
    unittest.main()
