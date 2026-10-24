"""Release signing must fail closed and keep credentials out of diagnostics."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('macos_signing', Path(__file__).resolve().parents[1] / 'scripts' / 'macos_signing.py')
signing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(signing)


class MacSigningTests(unittest.TestCase):
    def test_missing_secrets_fail_before_importing(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(signing, 'command') as command:
            with self.assertRaisesRegex(RuntimeError, 'APPLE_APP_SPECIFIC_PASSWORD'):
                signing.install()
            command.assert_not_called()

    def test_requires_developer_id_not_development_certificate(self):
        digest = 'A' * 40
        with self.assertRaisesRegex(RuntimeError, 'Developer ID Application'):
            signing.developer_identity(f'1) {digest} "Apple Development: Test"')
        self.assertEqual(signing.developer_identity(f'1) {digest} "Developer ID Application: Test (1234567890)"'), digest)

    def test_refuses_ambiguous_signing_identity(self):
        with self.assertRaises(RuntimeError):
            signing.developer_identity('\n'.join(f'1) {c * 40} "Developer ID Application: Test"' for c in 'AB'))

    def test_command_errors_never_include_password_arguments(self):
        password = 'sensitive-example-password'
        with patch.object(signing.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', password)):
            with self.assertRaises(RuntimeError) as error:
                signing.command(['security', 'import', '-P', password], 'Import certificate')
        self.assertNotIn(password, str(error.exception))

    def test_command_timeout_never_includes_password_arguments(self):
        password = 'sensitive-example-password'
        with patch.object(signing.subprocess, 'run', side_effect=subprocess.TimeoutExpired(['security', password], 10)):
            with self.assertRaises(RuntimeError) as error:
                signing.command(['security', password], 'Import certificate')
        self.assertNotIn(password, str(error.exception))
        self.assertTrue(error.exception.__suppress_context__)

    def test_removes_exported_private_key_when_import_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            secrets = {name: 'example' for name in signing.SECRETS}
            secrets.update(RUNNER_TEMP=directory, BUILD_CERTIFICATE_BASE64=base64.b64encode(b'private-p12').decode())
            def fail_import(args, label, **kwargs):
                if args[:2] == ['security', 'import']:
                    self.assertEqual(Path(args[2]).read_bytes(), b'private-p12')
                    raise RuntimeError('Import rejected')
                return ''
            with patch.dict(os.environ, secrets, clear=True), patch.object(signing, 'command', side_effect=fail_import):
                with self.assertRaisesRegex(RuntimeError, 'Import rejected'):
                    signing.install()
            self.assertFalse((Path(directory) / 'jparty-signing' / 'certificate.p12').exists())

    def test_notarization_rejection_never_staples(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'notarization.json'
            env = {'JPARTY_CODESIGN_IDENTITY': 'A' * 40, 'JPARTY_SIGNING_KEYCHAIN': '/temporary/keychain'}
            details = subprocess.CompletedProcess([], 0, '', 'Authority=Developer ID Application: Test\nflags=runtime')
            rejected = subprocess.CompletedProcess([], 0, json.dumps({'status': 'Invalid'}), '')
            with patch.dict(os.environ, env), patch.object(signing, 'command') as command, \
                    patch.object(signing.subprocess, 'run', side_effect=[details, rejected]):
                with self.assertRaisesRegex(RuntimeError, 'not accepted'):
                    signing.notarize(Path(directory) / 'JParty.app', report)
            self.assertEqual(json.loads(report.read_text())['status'], 'Invalid')
            self.assertFalse(any('stapler' in call.args[0] for call in command.call_args_list))

    def test_acceptance_requires_stapling_and_gatekeeper_before_success_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'notarization.json'
            env = {'JPARTY_CODESIGN_IDENTITY': 'A' * 40, 'JPARTY_SIGNING_KEYCHAIN': '/temporary/keychain'}
            details = subprocess.CompletedProcess([], 0, '', 'Authority=Developer ID Application: Test\nflags=runtime')
            accepted = subprocess.CompletedProcess([], 0, json.dumps({'status': 'Accepted', 'id': 'test-id'}), '')
            with patch.dict(os.environ, env), patch.object(signing, 'command') as command, \
                    patch.object(signing.subprocess, 'run', side_effect=[details, accepted]):
                signing.notarize(Path(directory) / 'JParty.app', report)
            commands = [call.args[0] for call in command.call_args_list]
            self.assertTrue(any(args[:3] == ['xcrun', 'stapler', 'validate'] for args in commands))
            self.assertTrue(any(args[:2] == ['spctl', '--assess'] for args in commands))
            self.assertEqual(json.loads(report.read_text())['gatekeeper'], 'accepted')

    def test_gatekeeper_failure_cannot_report_publication_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'notarization.json'
            env = {'JPARTY_CODESIGN_IDENTITY': 'A' * 40, 'JPARTY_SIGNING_KEYCHAIN': '/temporary/keychain'}
            details = subprocess.CompletedProcess([], 0, '', 'Authority=Developer ID Application: Test\nflags=runtime')
            accepted = subprocess.CompletedProcess([], 0, json.dumps({'status': 'Accepted'}), '')
            def gatekeeper_error(args, label, **kwargs):
                if args[0] == 'spctl':
                    raise RuntimeError('Gatekeeper rejected the app')
            with patch.dict(os.environ, env), patch.object(signing, 'command', side_effect=gatekeeper_error), \
                    patch.object(signing.subprocess, 'run', side_effect=[details, accepted]):
                with self.assertRaisesRegex(RuntimeError, 'Gatekeeper'):
                    signing.notarize(Path(directory) / 'JParty.app', report)
            self.assertNotIn('gatekeeper', json.loads(report.read_text()))


if __name__ == '__main__':
    unittest.main()
