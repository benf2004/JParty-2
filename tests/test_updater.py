"""Release trust, archive safety, consent, and real replacement/rollback behavior."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import zipfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from jparty import updater
from jparty.update_widgets import UpdatePanel


def release_payload(system='linux', arch='x64', number='9.0.0'):
    name = f'JParty-{number}-{system}-{arch}' + ('.tar.gz' if system == 'linux' else '.zip')
    return {'tag_name': f'v{number}', 'assets': [{
        'name': name, 'size': 5, 'digest': 'sha256:' + hashlib.sha256(b'hello').hexdigest(),
        'browser_download_url': f'https://github.com/{updater.REPOSITORY}/releases/download/v{number}/{name}'}]}


class ReleaseTests(unittest.TestCase):
    def test_exact_platform_and_new_stable_version(self):
        for system, arch in [('macos', 'arm64'), ('macos', 'x64'), ('windows', 'x64'), ('linux', 'x64')]:
            payload = release_payload(system, arch)
            selected = updater.select_release(payload, current='2.9.9', key=(system, arch))
            self.assertEqual(selected['version'], '9.0.0')
            self.assertEqual(selected['system'], system)
        self.assertIsNone(updater.select_release(release_payload(number='2.9.9'), '2.10.0'))
        self.assertIsNone(updater.select_release(release_payload(number='2.10.0'), '2.10.0'))
        for flag in ('draft', 'prerelease'):
            self.assertIsNone(updater.select_release(dict(release_payload(), **{flag: True})))

    def test_rejects_untrusted_or_incomplete_release(self):
        for field, value in [('digest', None), ('digest', 'sha256:bad'), ('size', 0),
                             ('size', updater.MAX_DOWNLOAD + 1), ('browser_download_url', 'https://evil.test/update.zip')]:
            payload = release_payload()
            payload['assets'][0][field] = value
            with self.assertRaises(ValueError):
                updater.select_release(payload, key=('linux', 'x64'))
        with self.assertRaises(ValueError):
            updater.select_release(release_payload(), key=('macos', 'arm64'))
        with self.assertRaises(ValueError):
            updater.version_tuple('v2.5.0/../bad')

    def test_stream_download_integrity_and_progress(self):
        release = updater.select_release(release_payload(), key=('linux', 'x64'))
        response = Mock(status_code=200)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.iter_content.return_value = [b'he', b'', b'llo']
        session, progress = Mock(), Mock()
        session.get.return_value = response
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / 'update'
            updater.download_release(release, dest, progress, session)
            self.assertEqual(dest.read_bytes(), b'hello')
            self.assertEqual(progress.call_args.args, (100,))
            response.iter_content.return_value = [b'wrong']
            with self.assertRaisesRegex(ValueError, 'integrity'):
                updater.download_release(release, dest, progress, session)
            self.assertFalse(dest.exists())
            response.iter_content.return_value = [b'too long']
            with self.assertRaises(ValueError):
                updater.download_release(release, dest, progress, session)

    def test_redirect_must_stay_on_https_github(self):
        release = updater.select_release(release_payload(), key=('linux', 'x64'))
        session = Mock()
        session.get.return_value = Mock(status_code=302, headers={'Location': 'http://github.com/update'})
        with tempfile.TemporaryDirectory() as directory:
            for url in ('http://github.com/update', 'https://evil.test/update', 'https://github.com:444/update'):
                session.get.return_value.headers['Location'] = url
                with self.assertRaises(ValueError):
                    updater.download_release(release, Path(directory) / 'file', Mock(), session)

    def test_mac_requires_same_developer_and_gatekeeper(self):
        good = Mock(stdout='', stderr='Identifier=us.stuartthomas.jparty\nAuthority=Developer ID Application: Developer\nTeamIdentifier=ABCDE12345\n')
        other = Mock(stdout='', stderr='Identifier=us.stuartthomas.jparty\nAuthority=Developer ID Application: Other\nTeamIdentifier=OTHER12345\n')
        with patch.object(updater.subprocess, 'run', side_effect=[good, other]) as run:
            with self.assertRaisesRegex(ValueError, 'different developer'):
                updater.verify_mac_app(Path('/staged'), Path('/current'))
            self.assertEqual(run.call_count, 2)
        with patch.object(updater.subprocess, 'run', return_value=good) as run:
            updater.verify_mac_app(Path('/staged'), Path('/current'))
            self.assertIn('--strict', run.call_args_list[2].args[0])
            self.assertIn('--assess', run.call_args_list[3].args[0])


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def tar(self, entries):
        path = self.base / 'update.tar.gz'
        with tarfile.open(path, 'w:gz') as bundle:
            for name, content, kind in entries:
                item = tarfile.TarInfo(name)
                item.mode = 0o755
                if kind == 'link':
                    item.type, item.linkname = tarfile.SYMTYPE, content
                    bundle.addfile(item)
                elif kind == 'device':
                    item.type = tarfile.CHRTYPE
                    bundle.addfile(item)
                else:
                    data = content.encode()
                    item.size = len(data)
                    bundle.addfile(item, io.BytesIO(data))
        return path

    def test_linux_executable_and_internal_symlink(self):
        path = self.tar([('JParty/JParty', 'binary', 'file'), ('JParty/lib/real', 'library', 'file'),
                         ('JParty/lib/current', 'real', 'link')])
        app = updater.extract_release(path, self.base / 'extract', 'linux')
        self.assertTrue(os.access(app / 'JParty', os.X_OK))
        self.assertEqual((app / 'lib/current').read_text(), 'library')

    def test_path_traversal_and_special_files_rejected(self):
        for name, kind in [('../escape', 'file'), ('/tmp/escape', 'file'), ('JParty/../escape', 'file'),
                           ('JParty\\escape', 'file'), ('JParty/C:escape', 'file'), ('JParty/device', 'device')]:
            with self.subTest(name=name):
                path = self.tar([(name, '', kind)])
                with self.assertRaises(ValueError):
                    updater.extract_release(path, self.base / 'extract', 'linux')
        self.assertFalse((self.base / 'escape').exists())

    def test_symlink_escape_writes_through_links_and_duplicates_rejected(self):
        unsafe = [ [('JParty/escape', '../../escape', 'link')],
                   [('JParty/link', '.', 'link'), ('JParty/link/file', 'bad', 'file')],
                   [('JParty/JParty', 'one', 'file'), ('JParty/JParty', 'two', 'file')],
                   [('JParty/JParty', 'binary', 'file'), ('JParty/a', '.', 'link'),
                    ('JParty/sub/link', '../a/..', 'link')] ]
        for index, entries in enumerate(unsafe):
            with self.subTest(entries=entries):
                with self.assertRaises(ValueError):
                    updater.extract_release(self.tar(entries), self.base / str(index), 'linux')

    def test_windows_archive_and_missing_executable(self):
        path = self.base / 'update.zip'
        with zipfile.ZipFile(path, 'w') as bundle:
            bundle.writestr('JParty/JParty.exe', 'binary')
            bundle.writestr('JParty/_internal/data', 'data')
        app = updater.extract_release(path, self.base / 'extract', 'windows')
        self.assertTrue((app / 'JParty.exe').exists())
        with zipfile.ZipFile(path, 'w') as bundle:
            bundle.writestr('JParty/readme', 'no executable')
        with self.assertRaisesRegex(ValueError, 'missing'):
            updater.extract_release(path, self.base / 'missing', 'windows')

    def test_expanded_size_limit(self):
        path = self.tar([('JParty/JParty', 'too much', 'file')])
        with patch.object(updater, 'MAX_EXPANDED', 2), self.assertRaises(ValueError):
            updater.extract_release(path, self.base / 'extract', 'linux')


class UpdateManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.game = Mock(config={'updates': {'automatic_check': True}}, current_round=None)
        self.game.local_services.busy = False
        self.manager = updater.UpdateManager(self.game, self.base / 'updates')
        self.target = self.base / 'JParty'
        self.target.mkdir()
        self.stage = self.base / '.jparty-update-test' / 'JParty'
        self.stage.mkdir(parents=True)
        self.ready = dict(target=str(self.target), staged=str(self.stage), version='9.0.0')
        self.manager.staged = self.ready
        self.addCleanup(self.manager.deleteLater)

    def test_check_never_downloads_or_installs(self):
        with patch.object(self.manager, 'download') as download, patch.object(self.manager, 'install') as install:
            self.manager._complete('checked', updater.select_release(release_payload(), key=('linux', 'x64')))
            self.assertEqual(self.manager.status, 'available')
            download.assert_not_called()
            install.assert_not_called()
        panel = UpdatePanel(self.manager)
        self.addCleanup(panel.deleteLater)
        with patch.object(self.manager, 'download') as download:
            panel.action_button.click()
            download.assert_called_once()

    def test_automatic_checks_obey_preference_and_throttle(self):
        with patch.object(sys, 'frozen', True, create=True), patch.object(self.manager, 'check') as check:
            self.manager.automatic_check = False
            self.manager.automatic()
            check.assert_not_called()
            self.manager.automatic_check = True
            self.manager._write('state.json', {'last_check': time.time()})
            self.manager.automatic()
            check.assert_not_called()
            self.manager._write('state.json', {'last_check': 0})
            self.manager.automatic()
            check.assert_called_once()

    def test_startup_source_checkout_does_not_network(self):
        with patch.object(self.manager, 'check') as check, patch.object(sys, 'frozen', False, create=True):
            self.manager.start()
            check.assert_not_called()
        self.manager.timer.stop()

    def test_install_guard_checks_live_game_and_services(self):
        self.manager.status = 'ready'
        for current_round, busy in [(object(), False), (None, True)]:
            self.game.current_round, self.game.local_services.busy = current_round, busy
            with patch.object(updater.subprocess, 'Popen') as launch:
                self.manager.install()
                launch.assert_not_called()
                self.game.close.assert_not_called()
        self.game.current_round, self.game.local_services.busy = None, False
        self.assertTrue(self.manager.can_install())

    def test_install_launches_external_helper_then_exits_and_cancels_countdown(self):
        self.manager.status = 'ready'
        with patch.object(updater, 'installed_app', return_value=self.target), \
                patch.object(updater, 'platform_key', return_value=('linux', 'x64')), \
                patch.object(updater.subprocess, 'Popen') as launch:
            self.manager.install()
        command = launch.call_args.args[0]
        self.assertEqual(command[0], '/bin/sh')
        self.assertTrue(Path(command[1]).is_file())
        self.assertEqual(launch.call_args.kwargs['env']['PYINSTALLER_RESET_ENVIRONMENT'], '1')
        self.assertEqual(json.loads((self.manager.directory / 'pending.json').read_text())['staged'], str(self.stage))
        self.game.cancel_start_game.assert_called_once()
        self.game.close.assert_called_once()

    def test_staging_must_be_sibling_and_not_symlink(self):
        self.assertTrue(self.manager._valid_stage(self.ready, self.target))
        self.assertFalse(self.manager._valid_stage(dict(self.ready, staged=str(self.base)), self.target))
        self.stage.rmdir()
        self.stage.symlink_to(self.target, target_is_directory=True)
        self.assertFalse(self.manager._valid_stage(self.ready, self.target))

    def test_restores_download_after_reopening(self):
        self.manager._write('ready.json', self.ready)
        with patch.object(updater, 'installed_app', return_value=self.target):
            self.manager.restore_download()
        self.assertEqual(self.manager.status, 'ready')

    def test_background_prepare_verifies_then_stages_without_exiting(self):
        archive = self.base / 'release.tar.gz'
        with tarfile.open(archive, 'w:gz') as bundle:
            data = b'#!/bin/sh\nexit 0\n'
            item = tarfile.TarInfo('JParty/JParty')
            item.size, item.mode = len(data), 0o755
            bundle.addfile(item, io.BytesIO(data))
        self.manager.release = updater.select_release(release_payload(), key=('linux', 'x64'))
        self.manager.status = 'available'
        def download(release, destination, progress):
            import shutil
            shutil.copy2(archive, destination)
            progress(100)
        with patch.object(updater, 'installed_app', return_value=self.target), \
                patch.object(updater, 'download_release', side_effect=download):
            self.manager.download()
            deadline = time.monotonic() + 5
            while self.manager.status == 'downloading' and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(.01)
        self.assertEqual(self.manager.status, 'ready')
        self.assertEqual(self.manager.progress, 100)
        stage = Path(self.manager.staged['staged'])
        self.assertEqual(stage.parent.parent, self.target.parent)
        self.assertTrue((stage / 'JParty').is_file())
        self.game.close.assert_not_called()
        self.assertEqual(json.loads((self.manager.directory / 'ready.json').read_text())['staged'], str(stage))

    def test_failed_download_does_not_leave_ready_state_or_replace_app(self):
        self.manager.release = updater.select_release(release_payload(), key=('linux', 'x64'))
        self.manager.status = 'available'
        with patch.object(updater, 'installed_app', return_value=self.target), \
                patch.object(updater, 'download_release', side_effect=ValueError('integrity failure')):
            self.manager.download()
            deadline = time.monotonic() + 3
            while self.manager.status == 'downloading' and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(.01)
        self.assertEqual(self.manager.status, 'error')
        self.assertFalse((self.manager.directory / 'ready.json').exists())
        self.assertTrue(self.target.exists())
        self.game.close.assert_not_called()

    def test_failed_helper_launch_keeps_app_running(self):
        self.manager.status = 'ready'
        with patch.object(updater, 'installed_app', return_value=self.target), \
                patch.object(updater, 'platform_key', return_value=('linux', 'x64')), \
                patch.object(updater.subprocess, 'Popen', side_effect=OSError('Cannot start helper')):
            self.manager.install()
        self.assertEqual(self.manager.status, 'error')
        self.game.close.assert_not_called()
        self.assertTrue(self.target.exists())

    def test_confirm_removes_only_expected_backup_after_successful_gui_start(self):
        backup = self.base / ('.jparty-previous-' + 'a' * 32)
        backup.mkdir()
        (backup / 'old').write_text('previous app')
        self.manager._write('pending.json', dict(self.ready, version=updater.version, backup=str(backup)))
        with patch.object(updater, 'installed_app', return_value=self.target):
            self.manager.confirm_install()
        self.assertFalse(backup.exists())
        self.assertTrue(self.target.exists())
        self.assertFalse(self.stage.parent.exists())
        self.assertFalse((self.manager.directory / 'pending.json').exists())
        self.manager._write('pending.json', dict(self.ready, version=updater.version, backup=str(self.target)))
        with patch.object(updater, 'installed_app', return_value=self.target):
            self.manager.confirm_install()
        self.assertTrue(self.target.exists())




if __name__ == '__main__':
    unittest.main()
