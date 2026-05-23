#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="jparty-voice-clone-tts"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<EOF
Stop the optional voice-clone TTS addon.

Usage:
  scripts/stop_voice_clone_auto_host_macos.sh
EOF
  exit 0
fi

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
    echo "Stopping voice-clone TTS..."
    docker stop "$CONTAINER_NAME" >/dev/null || true
  else
    echo "Voice-clone TTS is not running."
  fi
else
  echo "Docker is not available or not running; skipping voice-clone stop."
fi
