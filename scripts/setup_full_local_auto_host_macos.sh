#!/usr/bin/env bash
set -euo pipefail

LLM_MODEL="${JPARTY_LOCAL_LLM_MODEL:-qwen2.5:7b}"
LLM_URL="${JPARTY_LOCAL_LLM_BASE_URL:-http://localhost:11434/v1}"
STT_PORT="${JPARTY_LOCAL_STT_PORT:-8082}"
STT_URL="http://localhost:${STT_PORT}/v1"
TTS_PORT="${JPARTY_LOCAL_TTS_PORT:-8880}"
TTS_URL="http://localhost:${TTS_PORT}/v1"
TTS_MODEL="macos-say"
TTS_VOICE="${JPARTY_MACOS_TTS_VOICE:-}"
WHISPER_MODEL="${JPARTY_WHISPER_MODEL:-base.en}"
APP_SUPPORT="${HOME}/Library/Application Support/JParty/local-auto-host"
WHISPER_MODEL_FILE="${APP_SUPPORT}/models/ggml-${WHISPER_MODEL}.bin"
OLLAMA_HEALTH_URL="${LLM_URL%/v1}/api/tags"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<EOF
Set up a fully local beginner Auto Host stack on macOS:
  - Ollama local LLM for clue parsing and answer judging
  - whisper.cpp local Whisper server for speech-to-text
  - built-in macOS speech for text-to-speech, including Personal Voice

Usage:
  scripts/setup_full_local_auto_host_macos.sh
  JPARTY_LOCAL_LLM_MODEL=llama3.2:3b scripts/setup_full_local_auto_host_macos.sh
  JPARTY_WHISPER_MODEL=small.en scripts/setup_full_local_auto_host_macos.sh
  JPARTY_MACOS_TTS_VOICE="Your Personal Voice Name" scripts/setup_full_local_auto_host_macos.sh

This script installs/checks Homebrew packages, downloads local models, starts
local services, and prints the JParty settings to use. It does not edit your
JParty config file.
EOF
}

install_homebrew_if_needed() {
  if command -v brew >/dev/null 2>&1; then
    return
  fi
  echo "Homebrew is required to install Ollama, whisper.cpp, and ffmpeg."
  read -r -p "Install Homebrew now? [y/N] " install_brew
  if [[ ! "$install_brew" =~ ^[Yy]$ ]]; then
    echo "Stopped. Install Homebrew from https://brew.sh, then run this script again."
    exit 1
  fi
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
}

install_brew_package_if_needed() {
  local command_name="$1"
  local package_name="$2"
  if command -v "$command_name" >/dev/null 2>&1; then
    echo "$package_name is already installed."
    return
  fi
  echo "Installing $package_name..."
  brew install "$package_name"
}

wait_for_url() {
  local url="$1"
  local name="$2"
  for _ in {1..30}; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "$name is reachable."
      return 0
    fi
    sleep 1
  done
  echo "$name did not become reachable at $url."
  return 1
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This helper is for macOS. See FULL_LOCAL_AUTOHOST.md for manual setup notes."
  exit 1
fi

if [[ "$(uname -m)" != "arm64" ]]; then
  echo "Warning: Personal Voice requires Apple silicon. Local models may also be slower on this Mac."
fi

install_homebrew_if_needed
install_brew_package_if_needed ollama ollama
install_brew_package_if_needed ffmpeg ffmpeg
install_brew_package_if_needed whisper-server whisper-cpp

mkdir -p "${APP_SUPPORT}/models"

if [[ ! -s "$WHISPER_MODEL_FILE" ]]; then
  echo "Downloading Whisper model: $WHISPER_MODEL"
  curl -L --fail \
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-${WHISPER_MODEL}.bin" \
    -o "$WHISPER_MODEL_FILE"
else
  echo "Whisper model already exists: $WHISPER_MODEL_FILE"
fi

if ! curl -fsS "$OLLAMA_HEALTH_URL" >/dev/null 2>&1; then
  echo "Starting Ollama in the background..."
  nohup ollama serve >/tmp/jparty-ollama.log 2>&1 &
fi
wait_for_url "$OLLAMA_HEALTH_URL" "Ollama"

echo "Pulling local LLM model: $LLM_MODEL"
ollama pull "$LLM_MODEL"

if ! curl -fsS "http://127.0.0.1:${STT_PORT}" >/dev/null 2>&1; then
  echo "Starting whisper.cpp server in the background..."
  nohup whisper-server \
    --host 127.0.0.1 \
    --port "$STT_PORT" \
    --model "$WHISPER_MODEL_FILE" \
    --inference-path /v1/audio/transcriptions \
    --convert \
    --no-timestamps \
    >/tmp/jparty-whisper-server.log 2>&1 &
fi
wait_for_url "http://127.0.0.1:${STT_PORT}" "whisper.cpp"

if ! curl -fsS "http://127.0.0.1:${TTS_PORT}/health" >/dev/null 2>&1; then
  echo "Starting built-in macOS TTS bridge in the background..."
  nohup python3 "${SCRIPT_DIR}/local_macos_tts_server.py" \
    --host 127.0.0.1 \
    --port "$TTS_PORT" \
    >/tmp/jparty-macos-tts.log 2>&1 &
fi
wait_for_url "http://127.0.0.1:${TTS_PORT}/health" "macOS TTS"

echo
echo "Visible macOS speech voices:"
python3 "${SCRIPT_DIR}/local_macos_tts_server.py" --list-voices | sed -n '1,20p'

echo
echo "Fully local Auto Host setup is running."
echo
echo "For your own Personal Voice:"
echo "  1. Create it in System Settings > Accessibility > Personal Voice."
echo "  2. Turn on Allow applications to use your Personal Voice."
echo "  3. Use the exact voice name from the list above as Local TTS voice."
echo
echo "Use these JParty Settings:"
echo "  Auto Host AI provider: local"
echo "  Local LLM URL: $LLM_URL"
echo "  Local LLM model: $LLM_MODEL"
echo "  Local STT URL: $STT_URL"
echo "  Local STT model: whisper"
echo "  Local TTS: macOS Personal Voice"
echo "  Local TTS URL: $TTS_URL"
echo "  Local TTS model: $TTS_MODEL"
if [[ -n "$TTS_VOICE" ]]; then
  echo "  Local TTS voice: $TTS_VOICE"
else
  echo "  Local TTS voice: leave blank for the Mac default, or type your Personal Voice name"
fi
echo
echo "Logs:"
echo "  Ollama: /tmp/jparty-ollama.log"
echo "  Whisper: /tmp/jparty-whisper-server.log"
echo "  macOS TTS: /tmp/jparty-macos-tts.log"
echo
echo "To stop the background services later:"
echo "  scripts/stop_full_local_auto_host_macos.sh"
