"""Installed-bundle verification, deliberately independent of AI services."""
import json
from pathlib import Path
import platform
import sys
import traceback


def run(report_path):
    report = Path(report_path).resolve()
    try:
        from PyQt6.QtGui import QFontDatabase
        from PyQt6.QtWidgets import QApplication
        from tornado.template import Loader
        from jparty.paths import config_path
        from jparty.environ import root
        from jparty.utils import resource_path, get_base_path
        from jparty.audio_check import verify_theme_audio
        from jparty.version import version
        config = json.loads(Path(config_path).read_text())
        config['auto_host']['enabled'] = False
        config['mute_sound'] = True
        Path(config_path).write_text(json.dumps(config))
        from jparty.game import Game
        from jparty.controller import BuzzerController
        from jparty.main_display import DisplayWindow, HostDisplayWindow
        from jparty.welcome_widget import SettingsMenu
        app = QApplication([])
        for name in ('board_font.ttf', 'question_font.ttf'):
            if QFontDatabase.addApplicationFont(resource_path(name)) < 0:
                raise RuntimeError(f'Missing bundled font: {name}')
        for name in ('icon.png', 'player.png', 'podium.png', 'intro.wav', 'final.wav'):
            if not Path(resource_path(name)).is_file():
                raise RuntimeError(f'Missing bundled resource: {name}')
        audio_report = verify_theme_audio(Path(get_base_path()) / 'data')
        base = Path(root)
        if not (base / 'buzzer').is_dir():
            base = base / 'jparty'
        html = Loader(str(base / 'buzzer' / 'templates')).load('index.html').generate(
            messages=[], theme={}, theme_json='{}', static_url=lambda p: '/static/' + p)
        if b'join-team' not in html:
            raise RuntimeError('Team phone controls are missing')
        for name in ('jquery-3.1.0.min.js', 'signature_pad-4.0.0.min.js', 'Anton-Regular.ttf'):
            if not (base / 'buzzer' / 'static' / 'vendor' / name).is_file():
                raise RuntimeError(f'Missing offline phone resource: {name}')
        for name in ('setup_full_local_auto_host_macos.sh', 'start_full_local_auto_host_macos.sh',
                     'stop_full_local_auto_host_macos.sh', 'local_kev_service.sh', 'local_macos_tts_server.py',
                     'install_update.sh', 'install_update.ps1'):
            if not (Path(root) / 'scripts' / name).is_file():
                raise RuntimeError(f'Missing optional local AI setup helper: {name}')
        game = Game()
        controller = BuzzerController(game)
        controller.player_url = lambda **_kwargs: 'http://127.0.0.1:8080'
        game.setBuzzerController(controller)
        board = DisplayWindow(game)
        host = HostDisplayWindow(game)
        game.setDisplays(host, board)
        settings = SettingsMenu(host.welcome_widget)
        app.processEvents()
        tabs = [settings.tabs.tabText(i) for i in range(settings.tabs.count())]
        if 'Team mode' not in tabs or 'Local Services' not in tabs:
            raise RuntimeError(f'Missing desktop settings: {tabs}')
        if settings.auto_host_toggle.isChecked():
            raise RuntimeError('Auto Host must default to off')
        if not settings.update_check_toggle.isChecked():
            raise RuntimeError('Automatic update checks must default to on')
        if settings.update_manager.status != 'idle':
            raise RuntimeError('Creating settings must not start update downloads or checks')
        settings.hide()
        board.hide()
        host.hide()
        report.write_text(json.dumps({'status': 'ok', 'version': version,
            'platform': platform.system(), 'architecture': platform.machine(),
            'frozen': bool(getattr(sys, 'frozen', False)), 'settings_tabs': tabs,
            'phone_assets': 'bundled', 'models': 'optional first-run downloads',
            'updates': 'ask before download; lobby restart; bundled installers',
            'auto_host_control': 'toggle; default off', 'audio': audio_report}, indent=2))
        return 0
    except Exception:
        report.write_text(json.dumps({'status': 'failed', 'error': traceback.format_exc()}, indent=2))
        return 1
