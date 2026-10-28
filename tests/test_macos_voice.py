import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyQt6.QtCore import QCoreApplication
from jparty.macos_voice import PersonalVoiceAccess, request_personal_voice_access


class PersonalVoiceTests(unittest.TestCase):
    def framework(self, status):
        def request(callback):
            callback(status)
        return SimpleNamespace(
            AVSpeechSynthesizer=SimpleNamespace(
                requestPersonalVoiceAuthorizationWithCompletionHandler_=Mock(side_effect=request)),
            AVSpeechSynthesisVoiceTraitIsPersonalVoice=2,
            AVSpeechSynthesisVoice=SimpleNamespace(speechVoices=lambda: [
                SimpleNamespace(name=lambda: 'My Voice', voiceTraits=lambda: 2),
                SimpleNamespace(name=lambda: 'Samantha', voiceTraits=lambda: 0)]))

    def test_authorization_requests_native_api_and_lists_only_personal_voices(self):
        framework = self.framework(3)
        completed = Mock()
        with patch('jparty.macos_voice.sys.platform', 'darwin'), patch.dict(sys.modules, AVFoundation=framework):
            request_personal_voice_access(completed)
        framework.AVSpeechSynthesizer.requestPersonalVoiceAuthorizationWithCompletionHandler_.assert_called_once()
        self.assertEqual(completed.call_args.args[0], {'status': 'authorized', 'voices': ['My Voice']})

    def test_denied_or_unsupported_does_not_enumerate_voices(self):
        for code, status in [(1, 'denied'), (2, 'unsupported')]:
            framework = self.framework(code)
            framework.AVSpeechSynthesisVoice.speechVoices = Mock(side_effect=AssertionError('must not enumerate'))
            completed = Mock()
            with patch('jparty.macos_voice.sys.platform', 'darwin'), patch.dict(sys.modules, AVFoundation=framework):
                request_personal_voice_access(completed)
            self.assertEqual(completed.call_args.args[0]['status'], status)

    def test_other_platforms_and_missing_framework_report_unavailable(self):
        for platform, status in [('linux', 'unsupported'), ('darwin', 'unavailable')]:
            completed = Mock()
            with patch('jparty.macos_voice.sys.platform', platform), patch.dict(sys.modules, AVFoundation=None):
                request_personal_voice_access(completed)
            self.assertEqual(completed.call_args.args[0]['status'], status)

    def test_callback_returns_to_qt_thread_and_duplicate_requests_are_ignored(self):
        app = QCoreApplication.instance() or QCoreApplication([])
        access = PersonalVoiceAccess()
        received = Mock()
        access.changed.connect(received)
        with patch('jparty.macos_voice.request_personal_voice_access') as request:
            access.request()
            access.request()
            request.assert_called_once()
            worker = threading.Thread(target=request.call_args.args[0], args=({'status': 'denied'},))
            worker.start()
            worker.join()
            received.assert_not_called()
            app.processEvents()
        received.assert_called_once_with({'status': 'denied'})
        self.assertFalse(access.pending)


if __name__ == '__main__':
    unittest.main()
