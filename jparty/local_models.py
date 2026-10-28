"""Ollama discovery and downloads, owned by the app rather than a settings dialog."""
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time

from PyQt6.QtCore import QByteArray, QObject, QProcess, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


OLLAMA_URL = 'http://localhost:11434'
OLLAMA_BASE_URL = OLLAMA_URL + '/v1'
SUGGESTED_MODELS = [
    ('qwen2.5:7b', 'Qwen 2.5 · Standard · about 4.7 GB',
     'JParty’s existing default for hosting and answer judging.'),
    ('qwen2.5:3b', 'Qwen 2.5 · Smaller · about 1.9 GB',
     'A smaller download that uses less memory. Answer quality may vary.'),
]


def canonical_model(name):
    return name if ':' in name.rsplit('/', 1)[-1] else name + ':latest'


def model_size(size):
    return f'{size / 1_000_000_000:.1f} GB' if size >= 1_000_000_000 else f'{size / 1_000_000:.0f} MB'


def parse_inventory(body):
    if not isinstance(body, dict) or not isinstance(body.get('models'), list):
        raise ValueError('Ollama returned an invalid model list. Update Ollama and try Refresh.')
    models = {}
    for item in body['models']:
        if not isinstance(item, dict) or not isinstance(item.get('name'), str):
            raise ValueError('Ollama returned an invalid model list. Update Ollama and try Refresh.')
        # Cloud aliases do not provide a downloaded local model.
        if item.get('remote_host') or item.get('remote_model'):
            continue
        size = item.get('size', 0)
        if not isinstance(size, (int, float)) or size < 0:
            raise ValueError('Ollama returned an invalid model size. Try Refresh.')
        models[item['name']] = {'name': item['name'], 'size': size}
    return sorted(models.values(), key=lambda item: item['name'].lower())


class OllamaManager(QObject):
    changed = pyqtSignal()
    downloaded = pyqtSignal(str)

    def __init__(self, services, parent=None):
        super().__init__(parent or services)
        self.services = services
        self.network = QNetworkAccessManager(self)
        self.models = []
        self.online = False
        self.checking = False
        self.checked_at = 0
        self.message = 'Checking Ollama…'
        self.capabilities = {}
        self._capability_replies = {}
        self._inventory_generation = 0
        self._inventory_reply = None
        self.download_reply = None
        self._finishing_reply = None
        self.download_model = ''
        self.download_message = ''
        self.progress = None
        self._buffer = b''
        self._pull_error = ''
        self._success = False
        self._cancelled = False
        self.launching = False
        self._launch_deadline = 0
        self.launcher = QProcess(self)
        self.download_timeout = QTimer(self)
        self.download_timeout.setSingleShot(True)
        self.download_timeout.setInterval(60000)
        self.download_timeout.timeout.connect(self._download_timed_out)
        self.timer = QTimer(self)
        self.timer.setInterval(4000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        QTimer.singleShot(0, self.refresh)

    @property
    def busy(self):
        return self.download_reply is not None or self.launching

    def _request(self, path, timeout=2500):
        request = QNetworkRequest(QUrl(OLLAMA_URL + path))
        request.setTransferTimeout(timeout)
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, 'application/json')
        return request

    def selected_ready(self, name):
        key = canonical_model(name)
        return (self.online and time.monotonic() - self.checked_at < 10
                and any(canonical_model(item['name']) == key for item in self.models)
                and self.capabilities.get(key) is True and not self.services.busy)

    def check_model(self, name):
        key = canonical_model(name)
        if (not self.online or key in self.capabilities or key in self._capability_replies
                or not any(canonical_model(item['name']) == key for item in self.models)):
            return
        generation = self._inventory_generation
        reply = self.network.post(self._request('/api/show'), QByteArray(json.dumps({'model': name}).encode()))
        self._capability_replies[key] = reply

        def finished():
            if self._capability_replies.get(key) is not reply:
                return
            self._capability_replies.pop(key, None)
            if generation == self._inventory_generation:
                try:
                    body = json.loads(bytes(reply.readAll()))
                    if reply.error() != QNetworkReply.NetworkError.NoError or not isinstance(body, dict) or 'error' in body:
                        raise ValueError()
                    # Older Ollama releases omit capabilities.
                    self.capabilities[key] = 'completion' in body.get('capabilities', ['completion'])
                except (ValueError, TypeError):
                    self.capabilities[key] = None
                self.changed.emit()
            reply.deleteLater()
        reply.finished.connect(finished)

    def refresh(self):
        if self.checking:
            return
        self.checking = True
        reply = self.network.get(self._request('/api/tags'))
        self._inventory_reply = reply

        def finished():
            if self._inventory_reply is not reply:
                return
            self.checking = False
            self._inventory_reply = None
            try:
                if reply.error() != QNetworkReply.NetworkError.NoError:
                    raise ConnectionError()
                models = parse_inventory(json.loads(bytes(reply.readAll())))
                if models != self.models or not self.online:
                    self._inventory_generation += 1
                    self.capabilities.clear()
                self.models = models
                self.capabilities = {key: value for key, value in self.capabilities.items() if value is not None}
                self.online = True
                self.message = 'Ollama is running.' if models else 'Ollama is running. Download your first model below.'
                self.launching = False
            except (ValueError, TypeError) as exc:
                self._offline(str(exc) or 'Ollama returned an invalid response. Update it and try Refresh.')
            except ConnectionError:
                self._offline('Ollama is not running. Install it or choose Open/Start Ollama.')
            self.checked_at = time.monotonic()
            if self.launching and time.monotonic() > self._launch_deadline:
                self.launching = False
                self.message = 'Ollama did not start. Open the Ollama app, then choose Refresh.'
            self.changed.emit()
            reply.deleteLater()
        reply.finished.connect(finished)
        self.changed.emit()

    def _offline(self, message):
        self.online = False
        self.models = []
        self.capabilities.clear()
        self._inventory_generation += 1
        self.message = 'Opening Ollama…' if self.launching else message

    def start(self):
        if self.busy or self.services.busy:
            return
        if self.online:
            self.refresh()
            return
        app_paths = [Path('/Applications/Ollama.app'), Path.home() / 'Applications/Ollama.app']
        if sys.platform == 'darwin' and any(path.exists() for path in app_paths):
            program, arguments = '/usr/bin/open', ['-a', 'Ollama']
        else:
            search_path = os.pathsep.join(filter(None, [
                os.environ.get('PATH'), '/opt/homebrew/bin', '/usr/local/bin',
                str(Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'Ollama'),
            ]))
            program = shutil.which('ollama', path=search_path)
            arguments = ['serve']
            if not program:
                self.message = 'Install Ollama first, then open it and choose Refresh.'
                self.changed.emit()
                return
        self.launching = True
        self._launch_deadline = time.monotonic() + 30
        self.message = 'Opening Ollama…'
        self.changed.emit()
        # The server must outlive the settings dialog and JParty process.
        self.launcher.setProgram(program)
        self.launcher.setArguments(arguments)
        if not self.launcher.startDetached()[0]:
            self._launch_error()
        else:
            self.refresh()

    def _launch_error(self, *_args):
        self.launching = False
        self.message = 'Could not open Ollama. Install it, then open the Ollama app and choose Refresh.'
        self.changed.emit()

    def download(self, name):
        if self.busy or self.services.busy:
            return
        name = name.strip()
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}', name):
            self.download_message = 'Enter an Ollama model name, such as qwen2.5:3b.'
            self.changed.emit()
            return
        name = canonical_model(name)
        if not self.online:
            self.download_message = 'Start Ollama before downloading a model.'
            self.changed.emit()
            return
        self.download_model = name
        self.download_message = f'Downloading {name}…'
        self.progress = None
        self._buffer = b''
        self._pull_error = ''
        self._success = False
        self._cancelled = False
        reply = self.network.post(self._request('/api/pull', 60000),
                                  QByteArray(json.dumps({'model': name, 'stream': True}).encode()))
        self.download_reply = reply
        reply.readyRead.connect(lambda: self._read_download(reply))
        reply.finished.connect(lambda: self._download_finished(reply))
        self.download_timeout.start()
        self.changed.emit()

    def _read_download(self, reply):
        if reply is not self.download_reply:
            return
        self.download_timeout.start()
        if reply.isOpen():
            self._buffer += bytes(reply.readAll())
        while b'\n' in self._buffer:
            line, self._buffer = self._buffer.split(b'\n', 1)
            if line.strip():
                self._download_line(line)
        if len(self._buffer) > 1_000_000:
            self._pull_error = 'Ollama returned an invalid download response. Update Ollama and retry.'
            reply.abort()

    def _download_line(self, line):
        try:
            body = json.loads(line)
            if not isinstance(body, dict):
                raise ValueError()
            if body.get('error'):
                self._pull_error = f"Download failed: {str(body['error'])[:300]}. Check the model name, free space, or update Ollama, then retry."
                return
            status = body['status']
            if not isinstance(status, str):
                raise ValueError()
            self._success = status == 'success'
            total, completed = body.get('total', 0), body.get('completed', 0)
            self.progress = max(0, min(100, int(100 * completed / total))) if total else None
            if status == 'pulling manifest':
                detail = 'Looking up model…'
            elif status.startswith('pulling'):
                detail = 'Downloading model files…'
            elif status.startswith('verifying'):
                detail = 'Verifying model files…'
            else:
                detail = 'Finishing installation…'
            self.download_message = f'{self.download_model}: {detail}'
            if total:
                self.download_message += f' {model_size(completed)} of {model_size(total)}'
        except (ValueError, TypeError, KeyError, OverflowError):
            self._pull_error = 'Ollama returned an invalid download response. Update Ollama and retry.'
        self.changed.emit()

    def cancel(self):
        if self.download_reply is not None:
            self._cancelled = True
            self.download_reply.abort()

    def _download_timed_out(self):
        if self.download_reply is not None:
            self._pull_error = 'Download stopped responding. Check your connection and retry.'
            self.download_reply.abort()

    def _download_finished(self, reply):
        # Aborting a just-created reply can emit finished twice on Qt 6.6.
        # Late signals from an old transfer must not touch a new download.
        if reply is not self.download_reply or self._finishing_reply is reply:
            return
        self._finishing_reply = reply
        self._read_download(reply)
        if self._buffer.strip():
            self._download_line(self._buffer)
        self.download_timeout.stop()
        self.download_reply = None
        self._finishing_reply = None
        success = self._success and not self._pull_error and not self._cancelled and reply.error() == QNetworkReply.NetworkError.NoError
        if self._cancelled:
            self.download_message = 'Download cancelled. Choose Download & select to resume later.'
        elif self._pull_error:
            self.download_message = self._pull_error
        elif success:
            self.download_message = f'{self.download_model} downloaded. Save changes to use it.'
        else:
            self.download_message = 'Download failed. Check your connection, free disk space, and model name, then retry.'
        self.progress = 100 if success else None
        reply.deleteLater()
        if success:
            self.capabilities.pop(canonical_model(self.download_model), None)
            self.refresh()
            self.downloaded.emit(self.download_model)
        self.changed.emit()


def manager_for(services):
    if not hasattr(services, 'models'):
        services.models = OllamaManager(services)
    return services.models
