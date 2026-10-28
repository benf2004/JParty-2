"""Request Personal Voice access in the desktop app, never in a shell helper."""
import sys

from PyQt6.QtCore import QObject, pyqtSignal


def request_personal_voice_access(completion):
    """Return immediately; Apple may complete its authorization on another thread."""
    if sys.platform != 'darwin':
        completion({'status': 'unsupported', 'voices': [],
                    'message': 'Personal Voice is available only on supported Macs.'})
        return
    try:
        import AVFoundation
        synthesizer = AVFoundation.AVSpeechSynthesizer
        request = synthesizer.requestPersonalVoiceAuthorizationWithCompletionHandler_
    except (ImportError, AttributeError):
        completion({'status': 'unavailable', 'voices': [],
                    'message': 'Personal Voice requires macOS 14 or later and the JParty macOS voice component. Install an updated JParty build.'})
        return

    def authorized(status):
        statuses = {0: 'not_determined', 1: 'denied', 2: 'unsupported', 3: 'authorized'}
        result = {'status': statuses.get(int(status), 'unavailable'), 'voices': []}
        if result['status'] == 'authorized':
            try:
                trait = AVFoundation.AVSpeechSynthesisVoiceTraitIsPersonalVoice
                result['voices'] = sorted({str(voice.name()) for voice in
                    AVFoundation.AVSpeechSynthesisVoice.speechVoices()
                    if voice.voiceTraits() & trait})
            except Exception:
                result['message'] = 'Access granted, but the voice list could not be read. Try again.'
        completion(result)

    try:
        request(authorized)
    except Exception:
        completion({'status': 'unavailable', 'voices': [],
                    'message': 'macOS could not request Personal Voice access. Try again from the JParty app.'})


class PersonalVoiceAccess(QObject):
    changed = pyqtSignal(object)
    _completed = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pending = False
        self._completed.connect(self._finish)

    def request(self):
        if self.pending:
            return
        self.pending = True

        def completed(result):
            # The settings window may have closed while Apple's dialog was open.
            try:
                self._completed.emit(result)
            except RuntimeError:
                pass

        request_personal_voice_access(completed)

    def _finish(self, result):
        self.pending = False
        self.changed.emit(result)
