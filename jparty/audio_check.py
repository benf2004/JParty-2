"""Verify packaged theme audio without playing sound or needing an output device."""
import hashlib
import json
from pathlib import Path
import wave


def verify_theme_audio(data_directory):
    from PyQt6.QtCore import QEventLoop, QTimer, QUrl
    from PyQt6.QtMultimedia import QAudioDecoder

    data_directory = Path(data_directory)
    manifest = json.loads((data_directory / 'audio-manifest.json').read_text())
    if manifest.get('version') != 1 or not manifest.get('files'):
        raise RuntimeError('Missing or unsupported theme audio manifest')
    decoded = 0
    targets = sorted(set(manifest['files'].values()))
    for target in targets:
        path = data_directory / target
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != path.stem:
            raise RuntimeError(f'Missing or corrupt theme audio: {target}')
        if path.suffix == '.wav':
            with wave.open(str(path)) as recording:
                if not recording.getnframes():
                    raise RuntimeError(f'Empty theme sound effect: {target}')
            continue
        if path.suffix != '.mp3':
            raise RuntimeError(f'Unsupported theme audio: {target}')
        decoder = QAudioDecoder()
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        samples = []

        def read_sample():
            buffer = decoder.read()
            if buffer.isValid() and buffer.byteCount() > 0:
                samples.append(buffer.byteCount())
                loop.quit()

        decoder.bufferReady.connect(read_sample)
        decoder.error.connect(lambda *_: loop.quit())
        decoder.finished.connect(loop.quit)
        timer.timeout.connect(loop.quit)
        decoder.setSource(QUrl.fromLocalFile(str(path.resolve())))
        timer.start(10000)
        QTimer.singleShot(0, decoder.start)
        loop.exec()
        timer.stop()
        decoder.stop()
        if not samples:
            raise RuntimeError(f'Could not decode bundled music {target}: {decoder.errorString() or "no audio samples"}')
        decoded += 1
    return {'theme_recordings': len(manifest['files']), 'shared_files': len(targets),
            'mp3_tracks_decoded': decoded, 'effects': 'lossless WAV'}
