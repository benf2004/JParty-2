#!/usr/bin/env python3
"""Finish a pinned, locally built Mac release using CI's notarization profile."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from jparty.version import version


def digest(path):
    checksum = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(chunk)
    return checksum.hexdigest()


def gh(*args, json_result=False):
    result = subprocess.check_output(['gh', *map(str, args)], text=True)
    return json.loads(result) if json_result else result


def validate_input(archive, manifest):
    if manifest['version'] != version:
        raise ValueError('Local build version does not match the release.')
    smoke = manifest['smoke']
    if not (smoke.get('status') == 'ok' and smoke.get('version') == version
            and smoke.get('platform') == 'Darwin' and smoke.get('architecture') == 'arm64'
            and smoke.get('frozen') is True):
        raise ValueError('A successful packaged Apple Silicon smoke test is required.')
    if archive.name != manifest['archive_name'] or digest(archive) != manifest['archive_sha256']:
        raise ValueError('Local archive does not match the pinned build checksum.')


def check_source(manifest):
    repository = os.environ['GITHUB_REPOSITORY']
    run = gh('api', f'repos/{repository}/actions/runs/{manifest["source_run"]}', json_result=True)
    if run['head_sha'] != manifest['source_commit'] or run['path'] != '.github/workflows/main.yml':
        raise ValueError('The platform artifacts must come from the pinned source revision.')
    jobs = gh('api', f'repos/{repository}/actions/runs/{manifest["source_run"]}/jobs?per_page=100', json_result=True)['jobs']
    expected = {'test', 'build (macos-15-intel, macos-x64)',
                'build (windows-2022, windows-x64)', 'build (ubuntu-22.04, linux-x64)'}
    successful = {job['name'] for job in jobs if job['conclusion'] == 'success'}
    if not expected <= successful:
        raise ValueError('Tests and all three reused platform builds must have passed.')
    # The handoff commit may add release infrastructure, but cannot change app sources.
    changed = subprocess.check_output(['git', 'diff', '--name-only', manifest['source_commit'], 'HEAD'], text=True).splitlines()
    allowed = {'.github/workflows/local-mac-release.yml', '.github/local-mac-build.json',
               'scripts/release_local_mac.py', 'tests/test_local_mac_release.py'}
    if not set(changed) <= allowed:
        raise ValueError('Application sources changed after the local and hosted builds.')


def draft():
    repository, revision = os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_SHA']
    tag = 'v' + version
    result = subprocess.run(['gh', 'release', 'view', tag, '--repo', repository,
                             '--json', 'isDraft,targetCommitish'], capture_output=True, text=True)
    if result.returncode:
        gh('release', 'create', tag, '--repo', repository, '--target', revision,
           '--draft', '--title', 'JParty ' + tag, '--notes-file', PROJECT / 'RELEASE_NOTES.md')
    else:
        release = json.loads(result.stdout)
        if release != {'isDraft': True, 'targetCommitish': revision}:
            raise ValueError('Refusing to replace a published release or another revision’s draft.')


def finalize(archive, manifest, output):
    validate_input(archive, manifest)
    from macos_signing import command, notarize
    output.mkdir(parents=True, exist_ok=True)
    stem = output / f'JParty-{version}-macos-arm64'
    with tempfile.TemporaryDirectory(prefix='jparty-local-arm-') as directory:
        command(['ditto', '-x', '-k', archive, directory], 'Extract pinned local app', timeout=300)
        app = Path(directory) / 'JParty.app'
        info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
        if info.get('CFBundleIdentifier') != 'us.stuartthomas.jparty' or info.get('CFBundleShortVersionString') != version:
            raise ValueError('The local app has an unexpected bundle identity or version.')
        architectures = command(['lipo', '-archs', app / 'Contents/MacOS/JParty'], 'Verify local app architecture').strip()
        if architectures != 'arm64':
            raise ValueError('The local app must contain an Apple Silicon executable.')
        command(['codesign', '--verify', '--deep', '--strict', app], 'Verify local app signature', timeout=180)
        certificates = str(Path(directory) / 'signing-certificate-')
        command(['codesign', '-d', '--extract-certificates', certificates, app], 'Read local signing certificate')
        expected = PROJECT / 'resources/signing/developer-id-application.cer'
        if Path(certificates + '0').read_bytes() != expected.read_bytes():
            raise ValueError('The local app must use the repository’s release signing identity.')
        notarize(app, Path(str(stem) + '.notarization.json'))
        final_archive = Path(str(stem) + '.zip')
        command(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', app, final_archive],
                'Archive notarized local app', timeout=300)
    Path(str(stem) + '.smoke.json').write_text(json.dumps(manifest['smoke'], indent=2))
    Path(str(stem) + '.zip.sha256').write_bytes(f'{digest(final_archive)}  {final_archive.name}\n'.encode('ascii'))


def validate_assets(output):
    checksums = []
    for platform in ('macos-arm64', 'macos-x64', 'windows-x64', 'linux-x64'):
        stem = output / f'JParty-{version}-{platform}'
        archive = Path(str(stem) + ('.tar.gz' if platform == 'linux-x64' else '.zip'))
        expected = f'{digest(archive)}  {archive.name}\n'
        if Path(str(archive) + '.sha256').read_text() != expected:
            raise ValueError(f'Checksum verification failed for {platform}.')
        checksums.append(expected)
        smoke = json.loads(Path(str(stem) + '.smoke.json').read_text())
        if smoke.get('status') != 'ok' or smoke.get('version') != version:
            raise ValueError(f'Packaged app checks failed for {platform}.')
        if platform.startswith('macos-'):
            report = json.loads(Path(str(stem) + '.notarization.json').read_text())
            if not (report.get('status') == 'Accepted' and report.get('stapled') is True
                    and report.get('gatekeeper') == 'accepted'):
                raise ValueError(f'Apple verification failed for {platform}.')
    (output / 'SHA256SUMS.txt').write_bytes(''.join(checksums).encode('ascii'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'finalize', 'publish'))
    parser.add_argument('--manifest', type=Path, default=PROJECT / '.github/local-mac-build.json')
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--assets', type=Path, default=Path('release-assets'))
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    if args.action == 'prepare':
        check_source(manifest)
        draft()
    elif args.action == 'finalize':
        finalize(args.archive, manifest, args.assets)
    else:
        validate_assets(args.assets)
        draft()  # Verify ownership of this still-unpublished draft immediately before mutation.
        repository, tag = os.environ['GITHUB_REPOSITORY'], 'v' + version
        gh('release', 'upload', tag, *sorted(args.assets.iterdir()), '--repo', repository, '--clobber')
        gh('release', 'delete-asset', tag, manifest['archive_name'], '--repo', repository, '--yes')
        gh('release', 'edit', tag, '--repo', repository, '--draft=false', '--latest')


if __name__ == '__main__':
    main()
