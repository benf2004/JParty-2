"""Local Auto Host readiness and non-blocking script management."""
import copy
import os
from pathlib import Path
import sys
import threading
import time
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor

import requests
from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, pyqtSignal

from jparty.auto_host import DEFAULT_AUTO_HOST_CONFIG
from jparty.environ import root


def merged_config(config):
    return {**DEFAULT_AUTO_HOST_CONFIG, **(config or {})}


def check_services(config):
    """Probe configured endpoints, including the selected model; never generate text/audio."""
    config = merged_config(config)
    checks = []

    def get(url):
        response = requests.get(url, timeout=(0.7, 1.2))
        response.raise_for_status()
        return response

    def models(base, model, kev=False):
        body = get(base.rstrip('/') + '/models').json()
        items = body.get('models' if kev else 'data', [])
        key = 'name' if kev else 'id'
        names = [item.get(key) for item in items]
        if model not in names:
            raise ValueError(f'Model {model} is not loaded')

    if config['ai_provider'] == 'local':
        checks.extend([
            ('Text generation', config['local_llm_base_url'],
             lambda: models(config['local_llm_base_url'], config['local_llm_model'])),
            ('Speech recognition', config['local_stt_base_url'],
             lambda: get(config['local_stt_base_url'].rstrip('/').removesuffix('/v1') + '/')),
            ('Host voice', config['local_tts_base_url'],
             lambda: get(config['local_tts_base_url'].rstrip('/') + '/audio/voices')),
        ])
    else:
        def api_key():
            if not (os.environ.get('OPENAI_API_KEY') or config.get('openai_api_key')):
                raise ValueError('Add an OpenAI API key in Auto Host settings')
        checks.append(('OpenAI', 'Cloud provider', api_key))
    if config.get('judge_provider') == 'local_binary' and config['ai_provider'] != 'local':
        checks.append(('Answer judge · local LLM', config['local_llm_base_url'],
                       lambda: models(config['local_llm_base_url'], config['local_llm_model'])))
    if config.get('judge_provider') == 'kev':
        checks.append(('Answer judge · Kev', config['kev_base_url'],
                       lambda: models(config['kev_base_url'], config['kev_model'], kev=True)))

    def run(check):
        name, endpoint, probe = check
        try:
            probe()
            return {'name': name, 'endpoint': endpoint, 'ready': True,
                    'detail': 'Key configured' if name == 'OpenAI' else 'Ready'}
        except ValueError as exc:
            detail = str(exc)
        except Exception:
            detail = 'Not reachable — start the service or check its address'
        return {'name': name, 'endpoint': endpoint, 'ready': False, 'detail': detail}

    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(run, checks))


def script_environment(config):
    """Translate GUI settings into the existing non-interactive script options."""
    config = merged_config(config)
    env = {'JPARTY_NONINTERACTIVE': '1', 'NONINTERACTIVE': '1',
           'JPARTY_LOCAL_KEV_ENABLED': '1' if config.get('judge_provider') == 'kev' else '0',
           'JPARTY_LOCAL_LLM_MODEL': config['local_llm_model']}
    for field, variable, default_port in [
        ('local_llm_base_url', 'JPARTY_LOCAL_LLM_BASE_URL', 11434),
        ('local_stt_base_url', 'JPARTY_LOCAL_STT_PORT', 8082),
        ('local_tts_base_url', 'JPARTY_LOCAL_TTS_PORT', 8880),
        ('kev_base_url', 'JPARTY_LOCAL_KEV_PORT', 8009),
    ]:
        if field == 'kev_base_url' and config.get('judge_provider') != 'kev':
            continue
        parsed = urlparse(config[field])
        if (parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1')
                or parsed.path.rstrip('/') != '/v1' or parsed.username or parsed.query or parsed.fragment):
            raise ValueError('Setup and Start manage local HTTP services only. Use http://localhost:PORT/v1, or manage your custom server externally and check status.')
        port = parsed.port or 80
        if field == 'local_llm_base_url':
            if port != default_port:
                raise ValueError('Managed Ollama uses port 11434. Manage custom Ollama servers externally.')
            env[variable] = config[field].rstrip('/')
        else:
            env[variable] = str(port)
    preset = config.get('local_tts_preset', 'macos_say')
    if preset not in ('macos_say', 'macos_personal_voice', 'kokoro'):
        raise ValueError('Custom voice servers are managed externally. Choose macOS or Kokoro to use Setup and Start.')
    env['JPARTY_LOCAL_TTS_ENGINE'] = 'kokoro' if preset == 'kokoro' else 'macos'
    env['JPARTY_MACOS_TTS_VOICE'] = config.get('local_tts_voice', '')
    env['JPARTY_KOKORO_TTS_VOICE'] = config.get('local_tts_voice') or 'af_heart'
    return env


class LocalServiceManager(QObject):
    changed = pyqtSignal()
    output = pyqtSignal(str)
    _probe_result = pyqtSignal(int, object)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = merged_config(config)
        self.results = []
        self.checked_at = 0
        self.checking = False
        self.busy = False
        self.message = 'Checking Auto Host services…'
        self.log = ''
        self.last_error = ''
        self._generation = 0
        self._callbacks = []
        self._probe_result.connect(self._receive_probe)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._process_error)
        self.timer = QTimer(self)
        self.timer.setInterval(4000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        QTimer.singleShot(0, self.refresh)

    @property
    def ready(self):
        return (not self.busy and bool(self.results) and time.monotonic() - self.checked_at < 10
                and all(row['ready'] for row in self.results))

    def configure(self, config):
        config = merged_config(config)
        if config != self.config:
            self.config = copy.deepcopy(config)
            self._generation += 1
            self.results = []
            self.checked_at = 0
            self._callbacks = []
            self.checking = False
            self.changed.emit()
        self.refresh()

    def refresh(self, callback=None):
        if callback is not None:
            self._callbacks.append(callback)
        if self.checking:
            return
        self.checking = True
        generation, config = self._generation, copy.deepcopy(self.config)
        def work():
            try:
                result = check_services(config)
            except Exception:
                result = [{'name': 'Auto Host', 'endpoint': '', 'ready': False,
                           'detail': 'Could not check services. Check your provider settings.'}]
            try:
                self._probe_result.emit(generation, result)
            except RuntimeError:
                pass  # App closed while the bounded HTTP checks were finishing.
        threading.Thread(target=work, daemon=True).start()

    def _receive_probe(self, generation, results):
        if generation != self._generation:
            return
        self.checking = False
        self.results = results
        self.checked_at = time.monotonic()
        if not self.busy:
            missing = [row['name'] for row in results if not row['ready']]
            self.message = 'All services ready' if not missing else 'Needs attention: ' + ', '.join(missing)
            if self.last_error:
                self.message = self.last_error + ' ' + self.message
        self.changed.emit()
        callbacks, self._callbacks = self._callbacks, []
        for callback in callbacks:
            callback()

    def run(self, action, config):
        if self.busy:
            return
        if sys.platform != 'darwin':
            raise ValueError('Automatic service management is available on macOS. Start your servers externally, then check status.')
        if action not in ('setup', 'start', 'stop'):
            raise ValueError('Unknown service action')
        options = script_environment(config) if action != 'stop' else {}
        script = Path(root) / 'scripts' / f'{action}_full_local_auto_host_macos.sh'
        if not script.is_file():
            raise ValueError('Local service scripts are missing from this JParty installation.')
        env = QProcessEnvironment.systemEnvironment()
        for key in ('PYTHONHOME', 'PYTHONPATH', 'DYLD_LIBRARY_PATH'):
            env.remove(key)
        env.insert('PATH', '/opt/homebrew/bin:/usr/local/bin:' + os.environ.get('PATH', '/usr/bin:/bin'))
        for key, value in options.items():
            env.insert(key, value)
        self.process.setProcessEnvironment(env)
        self._generation += 1
        self.checking = False
        self._callbacks = []
        self.results = []
        self.busy = True
        self.last_error = ''
        self.checked_at = 0
        self.message = {'setup': 'Setting up local Auto Host…', 'start': 'Starting local Auto Host…',
                        'stop': 'Stopping local Auto Host…'}[action]
        self.log = self.message + '\n'
        self.output.emit(self.log)
        self.changed.emit()
        self.process.start('/bin/bash', [str(script)])
        self.process.closeWriteChannel()

    def _read_output(self):
        chunk = bytes(self.process.readAllStandardOutput()).decode('utf-8', errors='replace')
        self.log = (self.log + chunk)[-60000:]
        self.output.emit(chunk)

    def _finished(self, code, _status):
        self._read_output()
        self.busy = False
        self._generation += 1
        self.checking = False
        self.checked_at = 0
        self.results = []
        self.last_error = '' if code == 0 else f'Command failed (exit {code}). See the activity log.'
        self.message = self.last_error or 'Command finished. Checking services…'
        line = '\n' + (self.last_error or 'Command completed.') + '\n'
        self.log = (self.log + line)[-60000:]
        self.output.emit(line)
        self.changed.emit()
        self.refresh()

    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.busy = False
            self.message = 'Could not launch the service script.'
            self.last_error = self.message
            self.log += self.message + '\n'
            self.output.emit(self.message + '\n')
            self.changed.emit()
