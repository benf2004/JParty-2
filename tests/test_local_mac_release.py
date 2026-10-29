"""Local-build handoff integrity and combined release verification."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from jparty.version import version
from scripts.release_local_mac import check_source, digest, draft, validate_assets, validate_input


class LocalMacReleaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.archive = self.root / 'local-arm.zip'
        self.archive.write_bytes(b'the locally built, signed app')
        self.manifest = {
            'version': version, 'archive_name': self.archive.name,
            'archive_sha256': digest(self.archive), 'source_run': 123, 'source_commit': 'verified-source',
            'smoke': {'status': 'ok', 'version': version, 'platform': 'Darwin',
                      'architecture': 'arm64', 'frozen': True},
        }

    def test_tampered_or_wrong_local_build_cannot_be_notarized(self):
        validate_input(self.archive, self.manifest)
        self.archive.write_bytes(b'changed after testing')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            validate_input(self.archive, self.manifest)

    def test_native_packaged_smoke_test_and_matching_version_are_required(self):
        for field, value in [('status', 'failed'), ('architecture', 'x86_64'),
                             ('frozen', False), ('version', '0.0.0'), ('platform', 'Linux')]:
            manifest = copy.deepcopy(self.manifest)
            manifest['smoke'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_input(self.archive, manifest)
        manifest = dict(self.manifest, version='0.0.0')
        with self.assertRaises(ValueError):
            validate_input(self.archive, manifest)

    @patch.dict(os.environ, {'GITHUB_REPOSITORY': 'owner/JParty', 'GITHUB_SHA': 'current'})
    def test_only_the_explicit_previous_handoff_draft_can_be_updated(self):
        manifest = dict(self.manifest, previous_handoff_revisions=['our-previous-handoff'])
        for state in ({'isDraft': False, 'targetCommitish': 'our-previous-handoff'},
                      {'isDraft': True, 'targetCommitish': 'someone-elses-draft'}):
            with patch('scripts.release_local_mac.subprocess.run', return_value=Mock(
                    returncode=0, stdout=json.dumps(state))), self.assertRaises(ValueError):
                draft(manifest)
        with patch('scripts.release_local_mac.subprocess.run', return_value=Mock(returncode=0,
                stdout=json.dumps({'isDraft': True, 'targetCommitish': 'our-previous-handoff'}))), patch(
                    'scripts.release_local_mac.gh') as request:
            draft(manifest)
            request.assert_called_once_with('release', 'edit', 'v' + version, '--repo', 'owner/JParty', '--target', 'current')

    @patch.dict(os.environ, {'GITHUB_REPOSITORY': 'owner/JParty'})
    def test_reused_packages_must_have_passed_at_the_exact_source_revision(self):
        run = {'head_sha': 'verified-source', 'path': '.github/workflows/main.yml'}
        jobs = {'jobs': [{'name': name, 'conclusion': 'success'} for name in (
            'test', 'build (macos-15-intel, macos-x64)',
            'build (windows-2022, windows-x64)', 'build (ubuntu-22.04, linux-x64)')]}
        with patch('scripts.release_local_mac.gh', side_effect=[run, jobs]), patch(
                'scripts.release_local_mac.subprocess.check_output', return_value='.github/local-mac-build.json\n'):
            check_source(self.manifest)
        with patch('scripts.release_local_mac.gh', return_value=dict(run, head_sha='different')):
            with self.assertRaisesRegex(ValueError, 'pinned source'):
                check_source(self.manifest)
        jobs['jobs'][2]['conclusion'] = 'failure'
        with patch('scripts.release_local_mac.gh', side_effect=[run, jobs]):
            with self.assertRaisesRegex(ValueError, 'must have passed'):
                check_source(self.manifest)

    @patch.dict(os.environ, {'GITHUB_REPOSITORY': 'owner/JParty'})
    def test_app_changes_after_the_build_block_the_handoff(self):
        jobs = {'jobs': [{'name': name, 'conclusion': 'success'} for name in (
            'test', 'build (macos-15-intel, macos-x64)',
            'build (windows-2022, windows-x64)', 'build (ubuntu-22.04, linux-x64)')]}
        with patch('scripts.release_local_mac.gh', side_effect=[
                {'head_sha': 'verified-source', 'path': '.github/workflows/main.yml'}, jobs]), patch(
                'scripts.release_local_mac.subprocess.check_output', return_value='jparty/welcome_widget.py\n'):
            with self.assertRaisesRegex(ValueError, 'sources changed'):
                check_source(self.manifest)

    def assets(self):
        for platform in ('macos-arm64', 'macos-x64', 'windows-x64', 'linux-x64'):
            stem = self.root / f'JParty-{version}-{platform}'
            archive = Path(str(stem) + ('.tar.gz' if platform == 'linux-x64' else '.zip'))
            archive.write_bytes(platform.encode())
            Path(str(archive) + '.sha256').write_text(f'{digest(archive)}  {archive.name}\n')
            Path(str(stem) + '.smoke.json').write_text(json.dumps({'status': 'ok', 'version': version}))
            if platform.startswith('macos-'):
                Path(str(stem) + '.notarization.json').write_text(json.dumps(
                    {'status': 'Accepted', 'stapled': True, 'gatekeeper': 'accepted'}))

    def test_publish_requires_all_checksums_and_both_apple_verifications(self):
        self.assets()
        validate_assets(self.root)
        self.assertEqual(len((self.root / 'SHA256SUMS.txt').read_text().splitlines()), 4)
        report = self.root / f'JParty-{version}-macos-arm64.notarization.json'
        report.write_text(json.dumps({'status': 'Accepted', 'stapled': False, 'gatekeeper': 'accepted'}))
        with self.assertRaisesRegex(ValueError, 'Apple verification'):
            validate_assets(self.root)
        self.assets()
        (self.root / f'JParty-{version}-windows-x64.zip').write_bytes(b'corrupt download')
        with self.assertRaisesRegex(ValueError, 'Checksum'):
            validate_assets(self.root)


if __name__ == '__main__':
    unittest.main()
