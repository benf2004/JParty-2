#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<EOF
Stop full local Auto Host services.

Usage:
  scripts/stop_full_local_auto_host_macos.sh

This stops game-night services but does not uninstall packages, models, Docker,
or JParty settings.
EOF
}

stop_process() {
  local pattern="$1"
  local label="$2"
  if pgrep -f "$pattern" >/dev/null 2>&1; then
    echo "Stopping $label..."
    pkill -f "$pattern" || true
  else
    echo "$label is not running."
  fi
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This helper is for macOS."
  exit 1
fi

stop_process "whisper-server" "whisper.cpp"
stop_process "ollama serve" "Ollama"
stop_process "local_macos_tts_server.py" "fallback macOS TTS"

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  if docker ps --format '{{.Names}}' | grep -qx 'jparty-voice-clone-tts'; then
    echo "Stopping voice-clone TTS..."
    docker stop jparty-voice-clone-tts >/dev/null || true
  else
    echo "Voice-clone TTS is not running."
  fi
  if docker ps --format '{{.Names}}' | grep -qx 'jparty-kokoro-tts'; then
    echo "Stopping Kokoro TTS..."
    docker stop jparty-kokoro-tts >/dev/null || true
  else
    echo "Kokoro TTS is not running."
  fi
else
  echo "Docker is not available or not running; skipping Kokoro stop."
fi

echo
echo "Full local Auto Host services are stopped."
