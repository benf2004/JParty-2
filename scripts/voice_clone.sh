#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VOICE_DIR="${SCRIPT_DIR}/voice_clone"

usage() {
  cat <<EOF
Voice-clone helpers for local Auto Host.

Usage:
  scripts/voice_clone.sh setup
  scripts/voice_clone.sh start
  scripts/voice_clone.sh stop
  scripts/voice_clone.sh setup-kokoclone
  scripts/voice_clone.sh start-kokoclone
  scripts/voice_clone.sh stop-kokoclone

KokoClone is the local cloned-voice path.
EOF
}

case "${1:-}" in
  setup|setup-kokoclone)
    exec "${VOICE_DIR}/setup_kokoclone_auto_host_macos.sh"
    ;;
  start|start-kokoclone)
    exec "${VOICE_DIR}/start_kokoclone_auto_host_macos.sh"
    ;;
  stop|stop-kokoclone)
    exec "${VOICE_DIR}/stop_kokoclone_auto_host_macos.sh"
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    echo "Unknown voice-clone command: $1"
    echo
    usage
    exit 1
    ;;
esac
