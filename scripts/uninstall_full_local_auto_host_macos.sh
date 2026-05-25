#!/usr/bin/env bash
set -euo pipefail

APP_SUPPORT="${HOME}/Library/Application Support/JParty/local-auto-host"
REMOVE_PACKAGES="${JPARTY_UNINSTALL_PACKAGES:-ask}"

usage() {
  cat <<EOF
Uninstall the full local Auto Host setup for macOS.

This removes/stops:
  - Ollama service process used by the setup script
  - whisper.cpp server process
  - macOS TTS bridge process
  - downloaded JParty Whisper model files
  - optional Homebrew packages installed for local Auto Host

It does NOT uninstall Homebrew.
It does NOT edit your JParty config file.

Usage:
  scripts/uninstall_full_local_auto_host_macos.sh

Optional non-interactive flags:
  JPARTY_UNINSTALL_PACKAGES=yes scripts/uninstall_full_local_auto_host_macos.sh
  JPARTY_UNINSTALL_PACKAGES=no scripts/uninstall_full_local_auto_host_macos.sh
EOF
}

confirm() {
  local prompt="$1"
  read -r -p "$prompt [y/N] " answer
  [[ "$answer" =~ ^[Yy]$ ]]
}

should_remove_packages() {
  case "$REMOVE_PACKAGES" in
    yes|true|1) return 0 ;;
    no|false|0) return 1 ;;
    *) confirm "Uninstall Homebrew packages ollama, whisper-cpp, and ffmpeg if present?" ;;
  esac
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

stop_process "ollama serve" "Ollama"
stop_process "whisper-server" "whisper.cpp server"
stop_process "local_macos_tts_server.py" "macOS TTS server"

if [[ -d "$APP_SUPPORT" ]]; then
  if confirm "Remove downloaded local Auto Host model files at ${APP_SUPPORT}?"; then
    rm -rf "$APP_SUPPORT"
    echo "Removed $APP_SUPPORT."
  else
    echo "Kept $APP_SUPPORT."
  fi
else
  echo "No downloaded local Auto Host model directory found."
fi

if command -v brew >/dev/null 2>&1; then
  if should_remove_packages; then
    for package in whisper-cpp ollama ffmpeg; do
      if brew list --formula "$package" >/dev/null 2>&1; then
        echo "Uninstalling $package..."
        brew uninstall "$package" || true
      else
        echo "$package is not installed with Homebrew."
      fi
    done
  else
    echo "Kept Homebrew packages."
  fi

else
  echo "Homebrew was not found; skipping package cleanup."
fi

echo
echo "Full local Auto Host cleanup is complete."
echo "Homebrew was not uninstalled."
echo "JParty settings were not changed."
