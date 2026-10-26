"""Shared theme resources and music controls, including calls from game workers."""
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, call, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QApplication
from jparty import utils
from jparty.audio_check import verify_theme_audio

DATA = Path(__file__).resolve().parents[1] / 'jparty' / 'data'


class ThemeAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_all_packaged_tracks_are_intact_and_mp3s_decode_with_qt(self):
        report = verify_theme_audio(DATA)
        self.assertEqual(report['theme_recordings'], 27)
        self.assertEqual(report['shared_files'], 22)
        self.assertEqual(report['mp3_tracks_decoded'], 7)

    def test_theme_music_and_default_fallback_resolve_to_shared_files(self):
        resolved = {}
        for theme in ('default', 'christmas', 'eightiessynthwave', 'halloween', 'biblebonkers', 'birthday'):
            with patch.object(utils, '_cached_theme', theme):
                resolved[theme] = Path(utils.resource_path('intro.wav'))
                self.assertTrue(resolved[theme].is_file())
                self.assertEqual(resolved[theme].suffix, '.mp3')
                self.assertEqual(Path(utils.resource_path('board_fill.wav')).suffix, '.wav')
        self.assertEqual(resolved['default'], resolved['christmas'])
        self.assertEqual(resolved['default'], resolved['eightiessynthwave'])
        self.assertEqual(resolved['default'], resolved['birthday'])
        self.assertNotEqual(resolved['default'], resolved['halloween'])
        self.assertNotEqual(resolved['default'], resolved['biblebonkers'])

    def test_legacy_theme_wav_override_wins_and_missing_theme_falls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            theme = root / 'data' / 'custom'
            theme.mkdir(parents=True)
            override = theme / 'intro.wav'
            override.write_bytes(b'legacy custom recording')
            shared = root / 'data' / 'audio'
            shared.mkdir()
            fallback = shared / 'default.mp3'
            fallback.write_bytes(b'fallback music')
            (root / 'data' / 'audio-manifest.json').write_text(json.dumps({'files': {
                'default/intro.wav': 'audio/default.mp3', 'custom/intro.wav': 'audio/default.mp3'}}))
            with patch.object(utils, 'get_base_path', return_value=directory), patch.object(utils, '_cached_theme', 'custom'):
                self.assertEqual(Path(utils.resource_path('intro.wav')), override)
            with patch.object(utils, 'get_base_path', return_value=directory), patch.object(utils, '_cached_theme', 'missing'):
                self.assertEqual(Path(utils.resource_path('intro.wav')), fallback)

    def test_audio_budget_and_no_duplicate_payloads(self):
        files = list((DATA / 'audio').iterdir())
        self.assertLess(sum(path.stat().st_size for path in files), 30 * 1024**2)
        manifest = json.loads((DATA / 'audio-manifest.json').read_text())['files']
        self.assertEqual({path.relative_to(DATA).as_posix() for path in files}, set(manifest.values()))
        self.assertFalse([path for path in DATA.glob('*/*.wav') if path.parent.name != 'audio'])


class MusicControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.output = Mock()
        self.media = Mock()
        with patch.object(utils, 'QAudioOutput', return_value=self.output), \
                patch.object(utils, 'QMediaPlayer', return_value=self.media):
            self.music = utils.SongPlayer()
        self.media.reset_mock()
        self.resolve = patch.object(utils, 'resource_path', side_effect=lambda name: '/audio/' + name.replace('.wav', '.mp3'))
        self.resolve.start()
        self.addCleanup(self.resolve.stop)

    def tearDown(self):
        self.music.stop()
        self.music.deleteLater()
        self.app.processEvents()

    def test_intro_repeats_and_final_switches_to_a_single_play(self):
        self.music.play(repeat=True)
        self.music.final()
        self.assertEqual(self.media.mock_calls, [
            call.stop(), call.setLoops(-1), call.setSource(QUrl.fromLocalFile('/audio/intro.mp3')), call.play(),
            call.stop(), call.setLoops(1), call.setSource(QUrl.fromLocalFile('/audio/final.mp3')), call.play()])

    def test_mute_stops_music_and_blocks_restarts_until_unmuted(self):
        self.music.play(True)
        self.music.set_muted(True)
        self.media.reset_mock()
        self.music.final()
        self.media.play.assert_not_called()
        self.output.setMuted.assert_called_with(True)
        self.music.set_muted(False)
        self.music.final()
        self.media.play.assert_called_once()
        self.media.setLoops.assert_called_with(1)

    def test_worker_requests_run_in_order_on_the_qt_thread(self):
        handled_threads = []
        self.media.play.side_effect = lambda: handled_threads.append(threading.current_thread())
        worker = threading.Thread(target=lambda: (self.music.play(True), self.music.stop(), self.music.final()))
        worker.start()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.media.play.assert_not_called()
        self.app.processEvents()
        self.assertEqual(handled_threads, [threading.current_thread()] * 2)
        self.assertEqual([item for item in self.media.mock_calls if item in (call.stop(), call.play())],
                         [call.stop(), call.play(), call.stop(), call.stop(), call.play()])


if __name__ == '__main__':
    unittest.main()
