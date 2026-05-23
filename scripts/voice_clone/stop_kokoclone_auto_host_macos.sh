#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<EOF
Stop the optional KokoClone TTS addon.

Usage:
  scripts/stop_kokoclone_auto_host_macos.sh
EOF
  exit 0
fi

if pgrep -f "kokoclone_openai_tts_adapter.py" >/dev/null 2>&1; then
  echo "Stopping KokoClone adapter..."
  pkill -f "kokoclone_openai_tts_adapter.py" || true
else
  echo "KokoClone adapter is not running."
fi
rm -f /tmp/jparty-kokoclone-adapter.pid
