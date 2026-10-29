"""Keep build selection and required release verification in sync."""
import json
from pathlib import Path
import sys


def release_platforms(version):
    platforms = [
        {'os': 'macos-15', 'platform': 'macos-arm64'},
        {'os': 'macos-15-intel', 'platform': 'macos-x64'},
        {'os': 'windows-2022', 'platform': 'windows-x64'},
        {'os': 'ubuntu-22.04', 'platform': 'linux-x64'},
    ]
    # Intel notarization blocks 2.5.0. Omit it only for this release.
    if version == '2.5.0':
        platforms = [item for item in platforms if item['platform'] != 'macos-x64']
    # Try the supported macOS 14 image while the macOS 15 arm64 pool is constrained.
    if version == '2.5.1':
        platforms[0]['os'] = 'macos-14'
    return platforms


if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from jparty.version import version
    print('matrix=' + json.dumps({'include': release_platforms(version)}))
