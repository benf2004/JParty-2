#!/usr/bin/env python3
"""Prepare shared theme audio from a directory containing theme/*.wav sources.

Only intro/final music is encoded (192 kbps MP3). Short effects stay lossless.
Requires ffmpeg on the maintainer's machine, never on an end user's machine.
Original recordings remain available in Git history before the audio migration.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def prepare(source, destination, ffmpeg='ffmpeg'):
    sources = sorted(source.glob('*/*.wav'))
    if not sources:
        raise ValueError('No theme/*.wav recordings found in the source directory.')
    directory = destination / 'audio'
    directory.mkdir(parents=True, exist_ok=True)
    files, converted = {}, {}
    with tempfile.TemporaryDirectory(prefix='jparty-audio-') as temporary:
        for original in sources:
            digest = hashlib.sha256(original.read_bytes()).hexdigest()
            music = original.name in ('intro.wav', 'final.wav')
            key = (digest, music)
            if key not in converted:
                if music:
                    output = Path(temporary) / (digest + '.mp3')
                    subprocess.run([ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error',
                                    '-i', str(original), '-map_metadata', '-1',
                                    '-codec:a', 'libmp3lame', '-b:a', '192k', str(output)], check=True)
                else:
                    output = original
                target = directory / (hashlib.sha256(output.read_bytes()).hexdigest() + output.suffix)
                if not target.exists():
                    shutil.copyfile(output, target)
                converted[key] = target.relative_to(destination).as_posix()
            files[original.relative_to(source).as_posix()] = converted[key]
    manifest = {'version': 1, 'files': files}
    (destination / 'audio-manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    print(f'{len(sources)} theme recordings → {len(converted)} shared audio files.')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--ffmpeg', default='ffmpeg')
    arguments = parser.parse_args()
    prepare(arguments.source, arguments.destination, arguments.ffmpeg)
