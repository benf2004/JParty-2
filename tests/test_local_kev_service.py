import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest


HELPER = Path(__file__).resolve().parents[1] / "scripts/local_kev_service.sh"
FAKE_SERVER = '''
import argparse, json, os
from http.server import BaseHTTPRequestHandler, HTTPServer
p = argparse.ArgumentParser()
p.add_argument('--run'); p.add_argument('--host'); p.add_argument('--port', type=int)
a = p.parse_args()
with open('environment.json', 'w') as f:
    json.dump({k: os.environ.get(k) for k in ['HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE']}, f)
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(json.dumps({'models': [{'name': 'kev-latest', 'run': a.run}]}).encode())
HTTPServer((a.host, a.port), Handler).serve_forever()
'''


class LocalKevServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.kev = self.home / 'Library/Application Support/JParty/local-auto-host/kev'
        (self.kev / '.venv/bin').mkdir(parents=True)
        (self.kev / '.venv/bin/python').symlink_to(Path(sys.executable).resolve())
        (self.kev / 'kev').mkdir()
        (self.kev / 'kev/__init__.py').write_text('')
        (self.kev / 'kev/serve.py').write_text(FAKE_SERVER)
        (self.kev / 'jparty_kev_server.py').write_text('import runpy; runpy.run_module("kev.serve", run_name="__main__")')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        self.env = dict(os.environ, HOME=str(self.home), JPARTY_LOCAL_KEV_PORT=str(port),
                        JPARTY_KEV_START_TIMEOUT='5', JPARTY_LOCAL_KEV_ENABLED='1')

    def shell(self, command, **env):
        result = subprocess.run(['bash', '-c', 'set -euo pipefail; source "$1"; ' + command,
                               'test', str(HELPER)], env=dict(self.env, **env),
                              text=True, capture_output=True, timeout=25)
        log = self.kev.parent / 'kev-server.log'
        if result.returncode and log.exists():
            result.stderr += log.read_text()
            for host in ('127.0.0.1', 'localhost'):
                probe = subprocess.run(['curl', '--noproxy', '*', '--connect-timeout', '1',
                                        '--max-time', '2', '-v',
                                        f'http://{host}:{self.env["JPARTY_LOCAL_KEV_PORT"]}/v1/models'],
                                       text=True, capture_output=True, timeout=5)
                result.stderr += f'\nLoopback diagnostic ({host}):\n' + probe.stdout + probe.stderr
        return result

    def tearDown(self):
        self.shell('stop_kev')
        self.temp.cleanup()

    def test_start_reuse_stop_and_offline_mode(self):
        started = self.shell('start_kev')
        self.assertEqual(started.returncode, 0, started.stdout + started.stderr)
        pid = (self.kev / 'server.pid').read_text()
        restarted = self.shell('start_kev')
        self.assertEqual(restarted.returncode, 0, restarted.stdout + restarted.stderr)
        self.assertEqual((self.kev / 'server.pid').read_text(), pid)
        self.assertEqual(json.loads((self.kev / 'environment.json').read_text()),
                         {'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1'})
        stopped = self.shell('stop_kev', JPARTY_LOCAL_KEV_ENABLED='0')
        self.assertEqual(stopped.returncode, 0, stopped.stdout + stopped.stderr)
        self.assertFalse((self.kev / 'server.pid').exists())

    def test_setup_start_allows_downloads(self):
        started = self.shell('start_kev setup')
        self.assertEqual(started.returncode, 0, started.stdout + started.stderr)
        self.assertEqual(json.loads((self.kev / 'environment.json').read_text())['HF_HUB_OFFLINE'], '0')

    def test_loopback_health_checks_bypass_configured_proxies(self):
        started = self.shell('start_kev', http_proxy='http://127.0.0.1:1',
                             HTTP_PROXY='http://127.0.0.1:1', ALL_PROXY='http://127.0.0.1:1',
                             no_proxy='', NO_PROXY='')
        self.assertEqual(started.returncode, 0, started.stdout + started.stderr)

    def test_disabled_skips_install_and_start(self):
        result = self.shell('setup_kev; start_kev', JPARTY_LOCAL_KEV_ENABLED='0')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.kev / 'server.pid').exists())

    def test_stop_ignores_unrelated_pid(self):
        (self.kev / 'server.pid').write_text(str(os.getpid()) + '\n')
        self.assertEqual(self.shell('stop_kev').returncode, 0)
        os.kill(os.getpid(), 0)
        self.assertFalse((self.kev / 'server.pid').exists())

    def test_missing_install_has_setup_hint(self):
        (self.kev / '.venv/bin/python').unlink()
        result = self.shell('start_kev')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('setup_full_local_auto_host_macos.sh', result.stdout)

    def test_server_exit_fails_without_waiting_for_timeout(self):
        (self.kev / 'kev/serve.py').write_text('raise SystemExit(1)')
        result = self.shell('start_kev')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('exited before becoming ready', result.stdout)
        self.assertFalse((self.kev / 'server.pid').exists())

    def test_unmanaged_port_is_not_adopted(self):
        self.assertEqual(self.shell('start_kev').returncode, 0)
        pid_file = self.kev / 'server.pid'
        pid = pid_file.read_text()
        pid_file.unlink()
        try:
            result = self.shell('start_kev')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('unmanaged service', result.stdout)
            self.assertFalse(pid_file.exists())
        finally:
            pid_file.write_text(pid)

    def test_changed_checkpoint_reports_timeout_and_preserves_pid(self):
        self.assertEqual(self.shell('start_kev').returncode, 0)
        result = self.shell('start_kev', JPARTY_LOCAL_KEV_CHECKPOINT='different/checkpoint',
                            JPARTY_KEV_START_TIMEOUT='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('checkpoint/port differs', result.stdout)
        self.assertTrue((self.kev / 'server.pid').exists())

    def test_setup_installs_in_separate_environment(self):
        result = self.shell('''
git() { echo "git $*"; mkdir -p "$KEV_DIR/.git"; }
uv() { echo "uv $*"; }
setup_kev
''')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('git clone --branch kev-1.0 --depth 1', result.stdout)
        self.assertIn('--python 3.13 --extra serve --frozen', result.stdout)


if __name__ == '__main__':
    unittest.main()
