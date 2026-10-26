"""Opt-in downloads from JParty's stable GitHub releases, installed at lobby restart."""
import hashlib
import json
import logging
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from urllib.parse import urlparse
import uuid
import zipfile

import requests
from PyQt6.QtCore import QObject, pyqtSignal

from jparty.paths import user_data_dir
from jparty.version import version

REPOSITORY = 'benf2004/JParty-2'
LATEST_URL = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
MAX_DOWNLOAD = 2 * 1024 ** 3
MAX_EXPANDED = 4 * 1024 ** 3
DOWNLOAD_HOSTS = {'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}


def version_tuple(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', str(value))
    if not match:
        raise ValueError('The release has an unsupported version number.')
    return tuple(map(int, match.groups()))


def platform_key():
    system = {'Darwin': 'macos', 'Windows': 'windows', 'Linux': 'linux'}[platform.system()]
    machine = platform.machine().lower()
    if machine not in ('arm64', 'aarch64', 'x86_64', 'amd64'):
        raise ValueError('In-app updates are unavailable on this processor.')
    arch = 'arm64' if machine in ('arm64', 'aarch64') else 'x64'
    return system, arch


def select_release(payload, current=version, key=None):
    """Use only a newer stable release and its exact platform archive + digest."""
    if payload.get('draft') or payload.get('prerelease'):
        return None
    tag = payload.get('tag_name', '')
    if version_tuple(tag) <= version_tuple(current):
        return None
    number = tag.removeprefix('v')
    system, arch = key or platform_key()
    suffix = '.tar.gz' if system == 'linux' else '.zip'
    name = f'JParty-{number}-{system}-{arch}{suffix}'
    for asset in payload.get('assets', []):
        if asset.get('name') != name:
            continue
        url = f'https://github.com/{REPOSITORY}/releases/download/{tag}/{name}'
        digest = asset.get('digest', '')
        size = asset.get('size', 0)
        if (asset.get('browser_download_url') != url or not isinstance(digest, str)
                or not re.fullmatch(r'sha256:[0-9a-f]{64}', digest)
                or not isinstance(size, int) or not 0 < size <= MAX_DOWNLOAD):
            raise ValueError('The release is missing verified download information.')
        return dict(version=number, url=url, digest=digest[7:], size=size, system=system, name=name)
    raise ValueError('This release has no download for your computer. Please check again later.')


def download_release(release, destination, progress, session=requests):
    """Follow only HTTPS GitHub redirects and verify bytes before unpacking."""
    url = release['url']
    digest = hashlib.sha256()
    received = 0
    try:
        for _ in range(6):
            parsed = urlparse(url)
            if parsed.scheme != 'https' or parsed.hostname not in DOWNLOAD_HOSTS or parsed.username or parsed.port:
                raise ValueError('The download redirected outside GitHub.')
            response = session.get(url, stream=True, timeout=(10, 45), allow_redirects=False,
                                   headers={'User-Agent': f'JParty/{version}'})
            if response.status_code in (301, 302, 303, 307, 308):
                url = response.headers.get('Location', '')
                response.close()
                continue
            with response:
                response.raise_for_status()
                with Path(destination).open('wb') as output:
                    for chunk in response.iter_content(512 * 1024):
                        if not chunk:
                            continue
                        received += len(chunk)
                        if received > release['size'] or received > MAX_DOWNLOAD:
                            raise ValueError('The download is larger than expected.')
                        output.write(chunk)
                        digest.update(chunk)
                        progress(int(received * 100 / release['size']))
            break
        else:
            raise ValueError('Too many download redirects.')
        if received != release['size'] or digest.hexdigest() != release['digest']:
            raise ValueError('The update did not pass its integrity check. Please download it again.')
    except Exception:
        Path(destination).unlink(missing_ok=True)
        raise


def archive_path(name, root):
    if '\\' in name or ':' in name or '\x00' in name:
        raise ValueError('Unsafe path in update archive.')
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != root:
        raise ValueError('Unsafe path in update archive.')
    return path


def safe_link(path, target, root):
    if not target or target.startswith('/') or '\\' in target or ':' in target or '\x00' in target:
        raise ValueError('Unsafe link in update archive.')
    parts = list(path.parent.parts)
    for part in PurePosixPath(target).parts:
        if part == '..':
            if len(parts) <= 1:
                raise ValueError('Update link leaves the app folder.')
            parts.pop()
        elif part != '.':
            parts.append(part)
    if parts[0] != root:
        raise ValueError('Update link leaves the app folder.')


def extract_release(archive, directory, system):
    """Preflight all entries; never extract through a link or accept device files."""
    root = 'JParty.app' if system == 'macos' else 'JParty'
    directory = Path(directory)
    links, entries, total = set(), [], 0
    if system == 'linux':
        bundle = tarfile.open(archive, 'r:gz')
        for item in bundle.getmembers():
            path = archive_path(item.name, root)
            if not (item.isdir() or item.isfile() or item.issym()):
                bundle.close()
                raise ValueError('Unsupported entry in update archive.')
            if item.issym():
                safe_link(path, item.linkname, root)
                links.add(path)
            total += item.size
            entries.append((path, item))
    else:
        bundle = zipfile.ZipFile(archive)
        for item in bundle.infolist():
            if system == 'macos' and item.filename.startswith('__MACOSX/'):
                # ditto emits harmless resource metadata; still validate its path.
                archive_path(item.filename, '__MACOSX')
                total += item.file_size
                if stat.S_ISLNK(item.external_attr >> 16):
                    raise ValueError('Unsupported metadata link in update archive.')
                continue
            path = archive_path(item.filename, root)
            mode = item.external_attr >> 16
            if stat.S_ISLNK(mode):
                if system != 'macos' or item.file_size > 4096:
                    raise ValueError('Unsupported link in update archive.')
                safe_link(path, bundle.read(item).decode('utf-8'), root)
                links.add(path)
            elif stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError('Unsupported entry in update archive.')
            total += item.file_size
            entries.append((path, item))
    try:
        if total > MAX_EXPANDED or not entries or len(entries) > 100000:
            raise ValueError('The update archive is too large or empty.')
        if len({path for path, _ in entries}) != len(entries):
            raise ValueError('Duplicate paths in update archive.')
        for path, _ in entries:
            if any(parent in links for parent in path.parents):
                raise ValueError('Update archive writes through a link.')
        directory.mkdir(parents=True, exist_ok=True)
        if system == 'macos':
            subprocess.run(['/usr/bin/ditto', '-x', '-k', str(archive), str(directory)],
                           check=True, timeout=180, capture_output=True)
        else:
            for path, item in entries:
                dest = directory.joinpath(*path.parts)
                is_dir = item.isdir() if system == 'linux' else item.is_dir()
                if is_dir:
                    dest.mkdir(parents=True, exist_ok=True)
                elif path not in links:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    source = bundle.extractfile(item) if system == 'linux' else bundle.open(item)
                    with source, dest.open('wb') as output:
                        shutil.copyfileobj(source, output)
                    if system == 'linux':
                        dest.chmod(item.mode & 0o777)
            for path, item in entries:
                if path in links:
                    dest = directory.joinpath(*path.parts)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.symlink_to(item.linkname)
    finally:
        bundle.close()
    app = directory / root
    executable = app / ('Contents/MacOS/JParty' if system == 'macos' else
                        'JParty.exe' if system == 'windows' else 'JParty')
    for link in app.rglob('*'):
        if link.is_symlink():
            try:
                link.resolve(strict=True).relative_to(app.resolve())
            except (ValueError, OSError, RuntimeError):
                raise ValueError('Update link leaves the app folder or has no target.')
    if not executable.is_file():
        raise ValueError('The update is missing its executable.')
    return app


def installed_app():
    if not getattr(sys, 'frozen', False):
        raise ValueError('Install a packaged JParty release to use in-app updates.')
    executable = Path(sys.executable).resolve()
    system, _ = platform_key()
    if system == 'macos':
        app = executable.parents[2]
        if app.suffix != '.app' or executable.parent.name != 'MacOS':
            raise ValueError('The running app bundle could not be identified.')
    else:
        app = executable.parent
        if not (app / '_internal').is_dir() or app.name != 'JParty':
            raise ValueError('Keep JParty in its extracted application folder to install updates.')
    if not os.access(app.parent, os.W_OK) or 'AppTranslocation' in str(app):
        raise ValueError('Move JParty to a writable folder, such as Applications, before updating.')
    return app


def verify_mac_app(candidate, current):
    def identity(app):
        result = subprocess.run(['/usr/bin/codesign', '-dv', '--verbose=4', str(app)],
                                capture_output=True, text=True, check=True, timeout=30)
        details = result.stdout + result.stderr
        team = re.search(r'^TeamIdentifier=([A-Z0-9]+)$', details, re.M)
        identifier = re.search(r'^Identifier=(.+)$', details, re.M)
        if not team or not identifier or 'Authority=Developer ID Application:' not in details:
            raise ValueError('The update needs a valid Developer ID signature.')
        return team[1], identifier[1]
    original = identity(current)
    if original[1] != 'us.stuartthomas.jparty' or identity(candidate) != original:
        raise ValueError('The update was signed by a different developer.')
    subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(candidate)],
                   check=True, capture_output=True, timeout=90)
    subprocess.run(['/usr/sbin/spctl', '--assess', '--type', 'execute', str(candidate)],
                   check=True, capture_output=True, timeout=90)


class UpdateManager(QObject):
    changed = pyqtSignal()
    _finished = pyqtSignal(str, object)
    _progress = pyqtSignal(int)

    def __init__(self, game=None, directory=None):
        super().__init__()
        self.game = game
        self.directory = Path(directory or user_data_dir / 'updates')
        self.status = 'idle'
        self.message = f'JParty {version} · Downloads always ask first.'
        self.progress = 0
        self.release = None
        self.staged = None
        self.automatic_check = bool((getattr(game, 'config', {}) or {}).get('updates', {}).get('automatic_check', True))
        self._finished.connect(self._complete)
        self._progress.connect(self._set_progress)
        self.timer = None

    @property
    def busy(self):
        return self.status in ('checking', 'downloading')

    def _set(self, status, message):
        self.status, self.message = status, message
        self.changed.emit()

    def _set_progress(self, amount):
        self.progress = amount
        self.changed.emit()

    def _read(self, name):
        try:
            value = json.loads((self.directory / name).read_text())
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, name, value):
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.directory / (name + '.tmp')
        temporary.write_text(json.dumps(value))
        temporary.replace(self.directory / name)

    def start(self):
        from PyQt6.QtCore import QTimer
        self.confirm_install()
        self.restore_download()
        self.timer = QTimer(self)
        self.timer.setInterval(6 * 60 * 60 * 1000)
        self.timer.timeout.connect(self.automatic)
        self.timer.start()
        self.automatic()

    def automatic(self):
        if self.automatic_check and getattr(sys, 'frozen', False) and self.status != 'ready':
            last_check = self._read('state.json').get('last_check', 0)
            if not isinstance(last_check, (int, float)) or time.time() - last_check > 6 * 60 * 60:
                self.check()

    def _worker(self, action, operation):
        def run():
            try:
                result = operation()
            except Exception as exc:
                logging.exception('Update %s failed', action)
                try:
                    self._finished.emit('error', str(exc))
                except RuntimeError:
                    pass  # The application closed while the worker was finishing.
            else:
                try:
                    self._finished.emit(action, result)
                except RuntimeError:
                    pass
        threading.Thread(target=run, daemon=True, name=f'jparty-update-{action}').start()

    def check(self):
        if self.busy or self.status == 'ready':
            return
        self._set('checking', 'Checking for updates…')
        def fetch():
            with requests.get(LATEST_URL, timeout=(10, 25),
                              headers={'Accept': 'application/vnd.github+json', 'User-Agent': f'JParty/{version}'}) as response:
                response.raise_for_status()
                release = select_release(response.json())
            self._write('state.json', {'last_check': time.time()})
            return release
        self._worker('checked', fetch)

    def download(self):
        """Called only by the user's Download action; never by a check."""
        if self.busy or not self.release or self.status == 'ready':
            return
        try:
            target = installed_app()
        except ValueError as exc:
            self._set('error', str(exc))
            return
        release = self.release.copy()
        self.progress = 0
        self._set('downloading', f'Downloading JParty {release["version"]}…')
        def prepare():
            self.directory.mkdir(parents=True, exist_ok=True)
            staging = None
            try:
                with tempfile.TemporaryDirectory(prefix='download-', dir=self.directory) as cache:
                    archive = Path(cache) / release['name']
                    download_release(release, archive, self._progress.emit)
                    staging = Path(tempfile.mkdtemp(prefix='.jparty-update-', dir=target.parent))
                    candidate = extract_release(archive, staging, release['system'])
                    if candidate.name != target.name:
                        candidate = candidate.rename(candidate.with_name(target.name))
                    if release['system'] == 'macos':
                        verify_mac_app(candidate, target)
                    ready = dict(version=release['version'], target=str(target), staged=str(candidate))
                    self._write('ready.json', ready)
                    return ready
            except Exception:
                if staging:
                    shutil.rmtree(staging, ignore_errors=True)
                raise
        self._worker('downloaded', prepare)

    def _complete(self, action, result):
        if action == 'checked':
            self.release = result
            if result:
                mb = round(result['size'] / 1024 ** 2)
                self._set('available', f'JParty {result["version"]} is available · {mb} MB. Download when you’re ready.')
            else:
                self._set('current', f'You’re up to date · JParty {version}.')
        elif action == 'downloaded':
            self.staged = result
            self._set('ready', f'JParty {result["version"]} is ready. Restart from the lobby to update.')
        else:
            self._set('error', f'Update unavailable: {result}')

    def _valid_stage(self, ready, target):
        stage = Path(ready['staged'])
        return (Path(ready['target']) == target and stage.name == target.name
                and stage.parent.parent == target.parent and stage.parent.name.startswith('.jparty-update-')
                and not stage.parent.is_symlink() and not stage.is_symlink() and stage.is_dir())

    def restore_download(self):
        try:
            ready = self._read('ready.json')
            if ready and version_tuple(ready['version']) > version_tuple(version) and self._valid_stage(ready, installed_app()):
                self._complete('downloaded', ready)
        except (OSError, KeyError, ValueError):
            logging.info('No usable staged update to restore.')

    def can_install(self):
        return (self.game is not None and self.game.current_round is None
                and not getattr(self.game.local_services, 'busy', False))

    def install(self):
        if self.status != 'ready' or not self.staged:
            return
        if not self.can_install():
            self.message = 'Finish your game and any local service setup, then restart from the lobby.'
            self.changed.emit()
            return
        self._set('installing', 'Restarting JParty to install the update…')
        try:
            target = installed_app()
            if not self._valid_stage(self.staged, target):
                raise ValueError('The downloaded update moved. Please download it again.')
            system, _ = platform_key()
            if system == 'macos':
                verify_mac_app(Path(self.staged['staged']), target)
            backup = target.parent / ('.jparty-previous-' + uuid.uuid4().hex)
            pending = dict(self.staged, backup=str(backup))
            self._write('pending.json', pending)
            # Copy the helper out of the application before replacing it, especially
            # on Windows where a running executable locks its containing folder.
            base = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
            script_name = 'install_update.ps1' if system == 'windows' else 'install_update.sh'
            helper = self.directory / script_name
            shutil.copy2(base / 'scripts' / script_name, helper)
            args = [str(os.getpid()), str(target), self.staged['staged'], str(backup), system]
            env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT='1')
            if system == 'linux':
                env.pop('LD_LIBRARY_PATH', None)
                if 'LD_LIBRARY_PATH_ORIG' in env:
                    env['LD_LIBRARY_PATH'] = env.pop('LD_LIBRARY_PATH_ORIG')
            log = (self.directory / 'install.log').open('ab')
            try:
                if system == 'windows':
                    command = ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(helper)] + args
                    subprocess.Popen(command, stdout=log, stderr=log, cwd=self.directory,
                                     env=env, creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                                     close_fds=True)
                else:
                    subprocess.Popen(['/bin/sh', str(helper)] + args, stdout=log, stderr=log,
                                     cwd=self.directory, env=env, start_new_session=True, close_fds=True)
            finally:
                log.close()
            self.game.cancel_start_game()
            self.game.close()
        except Exception as exc:
            logging.exception('Could not restart to update')
            self._set('error', f'Could not install the update: {exc}')

    def confirm_install(self):
        """Remove the prior copy only after the new version reaches a working GUI."""
        pending = self._read('pending.json')
        if not pending:
            return
        try:
            target = installed_app()
            backup = Path(pending['backup'])
            if (pending['version'] == version and Path(pending['target']) == target
                    and backup.parent == target.parent and re.fullmatch(r'\.jparty-previous-[0-9a-f]{32}', backup.name)
                    and not backup.is_symlink()):
                shutil.rmtree(backup, ignore_errors=True)
                stage = Path(pending['staged']).parent
                if stage.parent == target.parent and stage.name.startswith('.jparty-update-') and not stage.is_symlink():
                    shutil.rmtree(stage, ignore_errors=True)
                (self.directory / 'pending.json').unlink(missing_ok=True)
                (self.directory / 'ready.json').unlink(missing_ok=True)
        except (OSError, ValueError, KeyError):
            logging.exception('Could not clean up the previous app copy')
