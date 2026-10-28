"""Exercise the real asynchronous Ollama protocol against a local fixture server."""
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget

from jparty.constants import DEFAULT_CONFIG
from jparty.local_models import OllamaManager, canonical_model, manager_for, parse_inventory
from jparty.model_widgets import LocalModelsPanel
from jparty.local_services import LocalServiceManager
from jparty.welcome_widget import SettingsMenu


class Services(QObject):
    changed = pyqtSignal()
    busy = False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def send_json(self, body, status=200):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.send_json(self.server.inventory, self.server.inventory_status)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append((self.path, body))
        if self.path == '/api/show':
            self.send_json({'capabilities': self.server.capabilities})
            return
        # A partially streamed pull lets tests close Settings and cancel in flight.
        self.send_response(200)
        self.send_header('Content-Type', 'application/x-ndjson')
        self.end_headers()
        try:
            for line in self.server.lines:
                self.wfile.write(line + b'\n')
                self.wfile.flush()
            self.server.started.set()
            if self.server.hold:
                self.server.release.wait(3)
            if self.server.finish_success:
                name = canonical_model(body['model'])
                self.server.inventory = {'models': [{'name': name, 'size': 1900000000}]}
                self.wfile.write(b'{"status":"success"}')
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.inventory = {'models': [
            {'name': 'qwen2.5:7b', 'size': 4700000000},
            {'name': 'qwen2.5:0.5b', 'size': 398000000},
        ]}
        self.server.inventory_status = 200
        self.server.capabilities = ['completion']
        self.server.lines = [b'{"status":"pulling layer","total":100,"completed":25}']
        self.server.hold = False
        self.server.finish_success = True
        self.server.requests = []
        self.server.started = threading.Event()
        self.server.release = threading.Event()
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url_patch = patch('jparty.local_models.OLLAMA_URL', f'http://127.0.0.1:{self.server.server_port}')
        self.url_patch.start()
        self.services = Services()
        self.manager = manager_for(self.services)
        self.manager.timer.stop()
        self.widgets = []
        self.spin(lambda: self.manager.online and not self.manager.checking)

    def tearDown(self):
        self.server.release.set()
        self.manager.cancel()
        for widget in self.widgets:
            widget.close()
            widget.deleteLater()
        self.services.deleteLater()
        self.app.processEvents()
        self.server.shutdown()
        self.server.server_close()
        self.url_patch.stop()

    def spin(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate())

    def panel(self, selected='qwen2.5:7b'):
        panel = LocalModelsPanel(self.manager, selected)
        self.widgets.append(panel)
        return panel

    def test_inventory_preserves_selection_and_sizes(self):
        panel = self.panel()
        self.spin(lambda: self.manager.selected_ready('qwen2.5:7b'))
        self.assertEqual(panel.model_combo.count(), 2)
        self.assertIn('4.7 GB', panel.model_combo.currentText())
        self.assertEqual(panel.selected_model, 'qwen2.5:7b')
        panel.model_combo.setFocus()
        QTest.keyClick(panel.model_combo, Qt.Key.Key_Up)
        self.assertEqual(panel.selected_model, 'qwen2.5:0.5b')
        self.manager.refresh()
        self.spin(lambda: not self.manager.checking)
        self.assertEqual(panel.selected_model, 'qwen2.5:0.5b')

    def test_missing_offline_and_empty_do_not_select_another_model(self):
        panel = self.panel('missing:latest')
        self.assertIn('not installed', panel.model_combo.currentText())
        self.server.inventory = {'models': []}
        self.manager.refresh()
        self.spin(lambda: not self.manager.checking)
        self.assertEqual(panel.selected_model, 'missing:latest')
        self.server.inventory_status = 503
        self.manager.refresh()
        self.spin(lambda: not self.manager.checking)
        self.assertFalse(self.manager.online)
        self.assertIn('offline', panel.model_combo.currentText())
        self.assertEqual(panel.selected_model, 'missing:latest')

    def test_invalid_inventory_and_cloud_aliases(self):
        for payload in ({}, {'models': None}, {'models': [{}]}, {'models': [{'name': 'x', 'size': 'bad'}]}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                parse_inventory(payload)
        self.assertEqual(parse_inventory({'models': [{'name': 'cloud', 'remote_host': 'ollama.com'}]}), [])

    def test_embedding_model_is_not_ready(self):
        self.server.capabilities = ['embedding']
        self.panel()
        self.spin(lambda: 'qwen2.5:7b' in self.manager.capabilities)
        self.assertFalse(self.manager.selected_ready('qwen2.5:7b'))

    def test_success_refreshes_inventory_and_selects_download(self):
        panel = self.panel()
        self.manager.download('qwen2.5:3b')
        self.assertTrue(self.manager.busy)
        self.spin(lambda: not self.manager.busy and any(m['name'] == 'qwen2.5:3b' for m in self.manager.models))
        self.assertEqual(panel.selected_model, 'qwen2.5:3b')
        self.assertEqual(self.manager.progress, 100)
        self.assertIn('Save changes', self.manager.download_message)
        self.assertIn(('/api/pull', {'model': 'qwen2.5:3b', 'stream': True}), self.server.requests)

    def test_cancellation_and_reopening_preserve_progress_then_retry(self):
        self.server.hold = True
        panel = self.panel()
        self.manager.download('qwen2.5:3b')
        self.spin(lambda: self.manager.progress == 25)
        panel.close()
        panel.deleteLater()
        self.widgets.remove(panel)
        panel = self.panel()
        self.assertTrue(panel.download_toggle.isChecked())
        self.assertEqual(panel.progress_bar.value(), 25)
        self.assertEqual(panel.suggestions.currentData(), 'qwen2.5:3b')
        self.assertIs(manager_for(self.services), self.manager)
        self.manager.cancel()
        self.spin(lambda: not self.manager.busy)
        self.assertIn('cancelled', self.manager.download_message)
        self.assertEqual(panel.selected_model, 'qwen2.5:7b')
        self.server.hold = False
        self.server.release.set()
        self.manager.download('qwen2.5:3b')
        self.spin(lambda: not self.manager.busy)
        self.assertIn('downloaded', self.manager.download_message)

    def test_malformed_or_failed_download_does_not_change_selection(self):
        panel = self.panel()
        for line in (b'not json', b'{"error":"model not found"}', b'{"status":"pulling","total":"invalid"}'):
            self.server.lines = [line]
            self.server.finish_success = False
            self.manager.download('bad-model')
            self.spin(lambda: not self.manager.busy)
            self.assertIn('retry', self.manager.download_message.lower())
            self.assertEqual(panel.selected_model, 'qwen2.5:7b')

    def test_connection_failure_and_timeout(self):
        self.server.lines = []
        self.server.finish_success = False
        with patch('jparty.local_models.OLLAMA_URL', 'http://127.0.0.1:1'):
            self.manager.download('qwen2.5:3b')
        self.spin(lambda: not self.manager.busy)
        self.assertIn('failed', self.manager.download_message)
        self.server.hold = True
        self.manager.download('qwen2.5:3b')
        self.manager._download_timed_out()
        self.spin(lambda: not self.manager.busy)
        self.assertIn('stopped responding', self.manager.download_message)

    def test_service_commands_and_launches_cannot_overlap_downloads(self):
        self.services.busy = True
        self.manager.download('qwen2.5:3b')
        self.manager.start()
        self.assertFalse(self.manager.busy)
        with patch('jparty.local_services.check_services', return_value=[]):
            service = LocalServiceManager({})
            service.timer.stop()
            service.models = self.manager
            self.manager.launching = True
            with self.assertRaisesRegex(ValueError, 'Wait for the model'):
                service.run('stop', {})
            self.manager.launching = False
            service.deleteLater()

    def test_late_completion_from_cancelled_download_cannot_finish_a_retry(self):
        self.server.hold = True
        self.manager.download('qwen2.5:3b')
        self.spin(lambda: self.manager.progress == 25)
        old_reply = self.manager.download_reply
        self.manager.cancel()
        self.manager.download('qwen2.5:3b')
        retry = self.manager.download_reply
        self.manager._download_finished(old_reply)
        self.manager._read_download(old_reply)
        self.assertIs(self.manager.download_reply, retry)
        self.assertTrue(self.manager.busy)

    def test_official_installer_links_and_cli_launch(self):
        panel = self.panel()
        with patch('jparty.model_widgets.webbrowser.open') as browser, patch('jparty.model_widgets.sys.platform', 'win32'):
            panel.install()
            browser.assert_called_once_with('https://ollama.com/download/windows')
        self.manager.online = False
        with patch('jparty.local_models.Path.exists', return_value=False), patch(
                'jparty.local_models.shutil.which', return_value='/opt/homebrew/bin/ollama'), patch.object(
                self.manager.launcher, 'startDetached', return_value=(True, 123)):
            self.manager.start()
            self.assertEqual(self.manager.launcher.program(), '/opt/homebrew/bin/ollama')
            self.assertEqual(self.manager.launcher.arguments(), ['serve'])
        self.manager.launching = False

    def test_settings_save_migration_and_pexels_pause_resume(self):
        from jparty import welcome_widget as module
        with tempfile.TemporaryDirectory() as directory, patch('jparty.local_services.check_services', return_value=[]):
            path = Path(directory) / 'config.json'
            config = copy.deepcopy(DEFAULT_CONFIG)
            config['auto_host'].update(ai_provider='openai', judge_provider='default', openai_api_key='test-cloud-key',
                                       local_llm_base_url='http://localhost:1234/v1')
            path.write_text(json.dumps(config))
            services = LocalServiceManager(config['auto_host'])
            services.timer.stop()
            services.models = self.manager
            self.widgets.append(QWidget())
            parent = self.widgets[-1]
            parent.game = Mock(config=config, local_services=services)
            with patch.object(module, 'config_path', str(path)), patch.object(module.os, 'execv') as restart, patch.dict(os.environ, {'PEXELS_API_KEY': ''}):
                dialog = SettingsMenu(parent)
                self.widgets.append(dialog)
                self.assertFalse(dialog.llm_group.isHidden())
                self.assertFalse(dialog.model_migration_notice.isHidden())
                self.assertEqual(json.loads(path.read_text())['auto_host']['local_llm_base_url'], 'http://localhost:1234/v1')
                self.spin(lambda: self.manager.selected_ready('qwen2.5:7b'))
                self.assertFalse(dialog.use_pexels_checkbox.isEnabled())
                dialog.pexels_api_key_input.setText('test-key')
                self.assertTrue(dialog.use_pexels_checkbox.isEnabled())
                dialog.use_pexels_checkbox.setChecked(True)
                self.manager.online = False
                self.manager.changed.emit()
                self.assertTrue(dialog.use_pexels_checkbox.isChecked())
                self.assertTrue(dialog.use_pexels_checkbox.isEnabled())
                self.assertIn('Paused', dialog.pexels_status_label.text())
                dialog.use_pexels_checkbox.setChecked(False)
                self.assertFalse(dialog.use_pexels_checkbox.isEnabled())
                self.manager.online = True
                self.manager.changed.emit()
                dialog.use_pexels_checkbox.setChecked(True)
                dialog.model_panel.select_model('missing:latest')
                self.assertIn('Paused', dialog.pexels_status_label.text())
                dialog.model_panel.select_model('qwen2.5:7b')
                self.assertIn('Ready', dialog.pexels_status_label.text())
                dialog.save_settings(close=False)
                saved = json.loads(path.read_text())
                self.assertTrue(saved['image_fallback']['use_pexels'])
                self.assertEqual(saved['auto_host']['local_llm_base_url'], 'http://localhost:11434/v1')
                self.assertTrue(dialog.model_migration_notice.isHidden())
                restart.assert_not_called()
            services.deleteLater()


if __name__ == '__main__':
    unittest.main()
