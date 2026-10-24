#!/usr/bin/env python3
"""Build, smoke-test, and archive one executable for the current platform."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from jparty.version import version


def platform_name():
    machine = platform.machine().lower()
    architecture = 'arm64' if machine in ('arm64', 'aarch64') else 'x64'
    return {'Darwin': 'macos', 'Windows': 'windows', 'Linux': 'linux'}[platform.system()], architecture


def smoke_test(executable, report):
    # Prove the installed app does not depend on a checkout, Python, saved user
    # settings, AI servers, or files relative to its working directory.
    with tempfile.TemporaryDirectory(prefix='jparty-smoke-') as directory:
        env = dict(os.environ, JPARTY_DATA_DIR=str(Path(directory) / 'user-data'),
                   QT_QPA_PLATFORM='offscreen')
        completed = subprocess.run([str(executable), '--smoke-test', str(report)], cwd=directory,
                                   env=env, timeout=90)
        if completed.returncode != 0:
            detail = report.read_text() if report.exists() else 'No smoke-test report was written.'
            raise RuntimeError(f'Installed executable exited {completed.returncode}: {detail}')
    result = json.loads(report.read_text())
    if result.get('status') != 'ok' or result.get('version') != version:
        raise RuntimeError(f'Packaged app smoke test failed: {result}')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=PROJECT / 'dist' / 'releases')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    system, arch = platform_name()
    require_notarization = os.environ.get('JPARTY_REQUIRE_NOTARIZATION') == '1'
    if system == 'macos' and require_notarization and not os.environ.get('JPARTY_CODESIGN_IDENTITY'):
        raise RuntimeError('Mac releases require a Developer ID signing identity. Run the signing setup first.')
    build = PROJECT / 'build' / 'release' / f'{system}-{arch}'
    dist = PROJECT / 'dist' / 'release' / f'{system}-{arch}'
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                    '--distpath', str(dist), '--workpath', str(build),
                    str(PROJECT / 'JParty.spec')], cwd=PROJECT, check=True)
    app = dist / ('JParty.app' if system == 'macos' else 'JParty')
    executable = (app / 'Contents' / 'MacOS' / 'JParty' if system == 'macos'
                  else app / ('JParty.exe' if system == 'windows' else 'JParty'))
    report = output / f'JParty-{version}-{system}-{arch}.smoke.json'
    smoke_test(executable, report)
    stem = output / f'JParty-{version}-{system}-{arch}'
    if system == 'macos':
        if require_notarization:
            from macos_signing import notarize
            notarize(app, Path(str(stem) + '.notarization.json'))
        # ditto preserves symlinks and the app's executable modes/code signature.
        archive = Path(str(stem) + '.zip')
        subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent',
                        str(app), str(archive)], check=True)
    else:
        for name in ('LICENSE', 'RELEASE_NOTES.md', 'FULL_LOCAL_AUTOHOST.md', 'AUTOHOST.md'):
            shutil.copy2(PROJECT / name, app / name)
        if system == 'windows':
            archive = Path(shutil.make_archive(str(stem), 'zip', root_dir=dist, base_dir=app.name))
        else:
            archive = Path(str(stem) + '.tar.gz')
            with tarfile.open(archive, 'w:gz') as bundle:
                bundle.add(app, arcname=app.name)
    digest = hashlib.sha256()
    with archive.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    checksum = digest.hexdigest()
    Path(str(archive) + '.sha256').write_bytes(f'{checksum}  {archive.name}\n'.encode('ascii'))
    print(f'Built and verified: {archive}', flush=True)


if __name__ == '__main__':
    main()
