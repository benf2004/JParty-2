"""Portable desktop bundle. AI services/models are optional first-run downloads."""
import platform
import sys
from pathlib import Path

project = Path(SPECPATH).resolve()
sys.path.insert(0, str(project))
from jparty.version import version

system = platform.system()
iconfile = str(project / 'resources' / ('icon.icns' if system == 'Darwin' else 'icon.ico'))
data_files = []
for asset in (project / 'jparty' / 'data').rglob('*'):
    if asset.is_file() and asset.suffix.lower() not in {'.pdn', '.psd'} and asset.name != '.DS_Store':
        data_files.append((str(asset), str(Path('data') / asset.parent.relative_to(project / 'jparty' / 'data'))))
data_files += [
    (str(project / 'jparty' / 'buzzer'), 'buzzer'),
    (str(project / 'jparty' / 'video.html'), 'jparty'),
    (str(project / 'designer_site'), 'designer_site'),
    (str(project / 'scripts' / '*.sh'), 'scripts'),
    (str(project / 'scripts' / 'local_macos_tts_server.py'), 'scripts'),
    (str(project / 'LICENSE'), 'licenses'),
    (str(project / 'RELEASE_NOTES.md'), 'docs'),
    (str(project / 'FULL_LOCAL_AUTOHOST.md'), 'docs'),
]

a = Analysis(
    [str(project / 'run.py')], pathex=[str(project)], binaries=[], datas=data_files,
    hiddenimports=['PyQt6.QtWebEngineCore', 'PyQt6.QtWebEngineWidgets',
                   'PyQt6.QtMultimedia', 'PyQt6.QtMultimediaWidgets',
                   'physicalbuzzers.physicalbuzzers'],
    hookspath=[], runtime_hooks=[],
    excludes=['tkinter', 'PyQt5', 'PySide2', 'PySide6'], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='JParty', debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, icon=iconfile,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='JParty')
if system == 'Darwin':
    app = BUNDLE(
        coll, name='JParty.app', version=version, icon=iconfile,
        bundle_identifier='us.stuartthomas.jparty',
        info_plist={
            'NSHighResolutionCapable': True,
            'NSMicrophoneUsageDescription': 'JParty uses microphone audio for optional Auto Host responses.',
            'LSMinimumSystemVersion': '11.0',
        },
    )
