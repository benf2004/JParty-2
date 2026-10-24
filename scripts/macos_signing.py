#!/usr/bin/env python3
"""Install a CI signing identity and notarize the finished macOS app."""
import argparse
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

PROFILE = 'jparty-notary'
PUBLIC_CERTIFICATES = Path(__file__).resolve().parents[1] / 'resources' / 'signing'
SECRETS = ('BUILD_CERTIFICATE_BASE64', 'P12_PASSWORD', 'KEYCHAIN_PASSWORD',
           'APPLE_ID', 'APPLE_TEAM_ID', 'APPLE_APP_SPECIFIC_PASSWORD')


def command(args, label, *, timeout=120):
    # Never let CalledProcessError print a command containing a password.
    try:
        result = subprocess.run([str(a) for a in args], capture_output=True,
                                text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        raise RuntimeError(f'{label} could not finish.') from None
    if result.returncode:
        raise RuntimeError(f'{label} failed. Check the signing/notarization credentials and Apple account access.')
    return result.stdout


def signing_directory():
    return Path(os.environ['RUNNER_TEMP']) / 'jparty-signing'


def developer_identity(output, expected_fingerprint=None):
    identities = re.findall(r'\b([A-Fa-f0-9]{40}) "Developer ID Application: [^"\n]+"', output)
    if expected_fingerprint:
        if expected_fingerprint.upper() not in [value.upper() for value in identities]:
            raise RuntimeError('The .p12 must contain the private key matching the public Developer ID '
                               'release certificate, and that certificate must be valid.')
        return expected_fingerprint.upper()
    if len(identities) != 1:
        raise RuntimeError('The .p12 must contain exactly one valid Developer ID Application certificate '
                           'with its private key. Apple Development and Apple Distribution certificates do not work here.')
    return identities[0]


def import_public_certificates(keychain):
    leaf = PUBLIC_CERTIFICATES / 'developer-id-application.cer'
    if not leaf.exists():
        return None
    # The .p12 secret supplies the private key. Public certificates can be
    # renewed separately and paired with that key without exporting it again.
    existing = command(['security', 'find-certificate', '-a', '-p', keychain], 'Read public certificates in build keychain')
    installed = {hashlib.sha256(base64.b64decode(pem)).digest() for pem in
                 re.findall(r'-----BEGIN CERTIFICATE-----\s*(.*?)\s*-----END CERTIFICATE-----', existing, re.S)}
    for certificate in sorted(PUBLIC_CERTIFICATES.glob('*.cer')):
        if hashlib.sha256(certificate.read_bytes()).digest() not in installed:
            command(['security', 'add-certificates', '-k', keychain, certificate], 'Import public Developer ID certificate chain')
    # macOS identifies signing identities using the certificate's SHA-1 fingerprint.
    return hashlib.sha1(leaf.read_bytes()).hexdigest().upper()


def identity_diagnostics(output):
    # Report certificate categories and trust errors, never names or key data.
    categories = ('Developer ID Application', 'Developer ID Installer', 'Apple Development',
                  'Apple Distribution', 'Mac Developer', '3rd Party Mac Developer Application',
                  '3rd Party Mac Developer Installer')
    present = [name for name in categories if f'"{name}:' in output]
    errors = sorted(set(re.findall(r'CSSMERR_[A-Z_]+', output)))
    return ('Imported signing identity types: ' + (', '.join(present) or 'none') +
            ('. Certificate validation errors: ' + ', '.join(errors) if errors else ''))


def install():
    missing = [name for name in SECRETS if not os.environ.get(name, '').strip()]
    if missing:
        raise RuntimeError('Add these GitHub Actions secrets before building a signed release: ' + ', '.join(missing))
    try:
        certificate = base64.b64decode(''.join(os.environ['BUILD_CERTIFICATE_BASE64'].split()), validate=True)
    except (ValueError, binascii.Error):
        raise RuntimeError('BUILD_CERTIFICATE_BASE64 must be the Base64-encoded .p12 file.') from None
    directory = signing_directory()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    keychain = directory / 'signing.keychain-db'
    original = command(['security', 'list-keychains', '-d', 'user'], 'Read keychain search list')
    # Paths are quoted, one per line, in security's output.
    keychains = re.findall(r'"([^"\n]+)"', original)
    (directory / 'original-keychains.json').write_text(json.dumps(keychains))
    password = os.environ['KEYCHAIN_PASSWORD']
    command(['security', 'create-keychain', '-p', password, keychain], 'Create temporary signing keychain')
    command(['security', 'set-keychain-settings', '-lut', '21600', keychain], 'Configure temporary signing keychain')
    command(['security', 'unlock-keychain', '-p', password, keychain], 'Unlock temporary signing keychain')
    certificate_path = directory / 'certificate.p12'
    try:
        certificate_path.write_bytes(certificate)
        certificate_path.chmod(0o600)
        command(['security', 'import', certificate_path, '-P', os.environ['P12_PASSWORD'],
                 '-t', 'cert', '-f', 'pkcs12', '-k', keychain, '-T', '/usr/bin/codesign'],
                'Import .p12 certificate (P12_PASSWORD must match its export password)')
    finally:
        certificate_path.unlink(missing_ok=True)
    expected_fingerprint = import_public_certificates(keychain)
    command(['security', 'set-key-partition-list', '-S', 'apple-tool:,apple:,codesign:',
             '-k', password, keychain], 'Allow codesign access to the private key')
    command(['security', 'list-keychains', '-d', 'user', '-s', keychain, *keychains],
            'Add temporary signing keychain to search list')
    identities = command(['security', 'find-identity', '-v', '-p', 'codesigning', keychain],
                         'Find Developer ID Application identity')
    try:
        identity = developer_identity(identities, expected_fingerprint)
    except RuntimeError:
        diagnostic = command(['security', 'find-identity', '-p', 'codesigning', keychain],
                             'Inspect signing identity types')
        print(identity_diagnostics(diagnostic), flush=True)
        raise
    command(['xcrun', 'notarytool', 'store-credentials', PROFILE, '--keychain', keychain,
             '--apple-id', os.environ['APPLE_ID'], '--team-id', os.environ['APPLE_TEAM_ID'],
             '--password', os.environ['APPLE_APP_SPECIFIC_PASSWORD']], 'Validate Apple notarization credentials')
    with open(os.environ['GITHUB_ENV'], 'a') as stream:
        stream.write(f'JPARTY_CODESIGN_IDENTITY={identity}\nJPARTY_SIGNING_KEYCHAIN={keychain}\n')
    print('Developer ID signing identity and notarization credentials installed in the temporary keychain.')


def cleanup():
    directory = signing_directory()
    keychain = directory / 'signing.keychain-db'
    original = directory / 'original-keychains.json'
    if original.exists():
        command(['security', 'list-keychains', '-d', 'user', '-s', *json.loads(original.read_text())],
                'Restore keychain search list')
    if keychain.exists():
        command(['security', 'delete-keychain', keychain], 'Delete temporary signing keychain')
    (directory / 'certificate.p12').unlink(missing_ok=True)


def notarize(app, report):
    keychain = os.environ.get('JPARTY_SIGNING_KEYCHAIN')
    if not os.environ.get('JPARTY_CODESIGN_IDENTITY') or not keychain:
        raise RuntimeError('A Developer ID identity and notarization keychain are required for Mac releases.')
    command(['codesign', '--verify', '--deep', '--strict', app], 'Verify Developer ID signature', timeout=180)
    details = subprocess.run(['codesign', '-d', '--verbose=4', str(app)], capture_output=True, text=True, check=True)
    if 'Authority=Developer ID Application:' not in details.stderr or 'runtime' not in details.stderr:
        raise RuntimeError('The app must have a Developer ID Application signature with hardened runtime.')
    credentials = ['--keychain-profile', PROFILE, '--keychain', keychain]
    with tempfile.TemporaryDirectory(prefix='jparty-notary-') as directory:
        archive = Path(directory) / 'JParty.zip'
        command(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', app, archive],
                'Archive signed app for Apple', timeout=300)
        print('Submitting signed app to Apple notarization; waiting for a result.', flush=True)
        result = subprocess.run(['xcrun', 'notarytool', 'submit', str(archive), *credentials,
                                 '--output-format', 'json', '--wait', '--timeout', '20m'],
                                capture_output=True, text=True, timeout=1500)
    try:
        submission = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError('Apple notarization did not return a submission result. Check credentials and service availability.') from None
    report.write_text(json.dumps({k: submission[k] for k in ('id', 'status', 'message') if k in submission}, indent=2))
    if result.returncode or submission.get('status') != 'Accepted':
        submission_id = submission.get('id', '')
        if re.fullmatch(r'[a-fA-F0-9-]{36}', submission_id):
            log = command(['xcrun', 'notarytool', 'log', submission_id, *credentials], 'Retrieve Apple notarization issues')
            # The log contains paths/validation issues, never authentication secrets.
            issues = json.loads(log).get('issues', [])
            print(json.dumps(issues, indent=2), flush=True)
        raise RuntimeError('Apple has not accepted this app for notarization. The release will not be published.')
    command(['xcrun', 'stapler', 'staple', app], 'Staple Apple notarization ticket', timeout=300)
    command(['xcrun', 'stapler', 'validate', app], 'Validate stapled notarization ticket')
    command(['codesign', '--verify', '--deep', '--strict', app], 'Verify final app signature', timeout=180)
    command(['spctl', '--assess', '--type', 'execute', '--verbose=4', app], 'Verify Gatekeeper acceptance', timeout=180)
    submission_report = json.loads(report.read_text())
    submission_report.update(stapled=True, gatekeeper='accepted', signing='Developer ID Application')
    report.write_text(json.dumps(submission_report, indent=2))
    print('Apple notarization accepted; ticket stapled and Gatekeeper verification passed.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'cleanup'))
    try:
        {'install': install, 'cleanup': cleanup}[parser.parse_args().action]()
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
