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
Start already-installed full local Auto Host services for game night.

Usage:
  scripts/start_full_local_auto_host_macos.sh
  JPARTY_LOCAL_LLM_MODEL=llama3.2:3b scripts/start_full_local_auto_host_macos.sh
  JPARTY_WHISPER_MODEL=small.en scripts/start_full_local_auto_host_macos.sh
  JPARTY_MACOS_TTS_VOICE="Your Personal Voice Name" scripts/start_full_local_auto_host_macos.sh

This does not install packages or download models. Run
scripts/setup_full_local_auto_host_macos.sh first if setup has not been done.
EOF
}

wait_for_url() {
  local url="$1"
  local name="$2"
  for _ in {1..30}; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "$name is ready."
      return 0
    fi
    sleep 1
  done
  echo "$name did not become ready at $url."
  return 1
}

require_command() {
  local command_name="$1"
  local install_hint="$2"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "$command_name is not installed."
    echo "$install_hint"
    exit 1
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

require_command ollama "Run scripts/setup_full_local_auto_host_macos.sh first."
require_command whisper-server "Run scripts/setup_full_local_auto_host_macos.sh first."
require_command ffmpeg "Run scripts/setup_full_local_auto_host_macos.sh first."
require_command python3 "Install Python 3 or run scripts/setup_full_local_auto_host_macos.sh first."

if [[ ! -s "$WHISPER_MODEL_FILE" ]]; then
  echo "Whisper model was not found: $WHISPER_MODEL_FILE"
  echo "Run scripts/setup_full_local_auto_host_macos.sh first, or set JPARTY_WHISPER_MODEL to an installed model."
  exit 1
fi

if ! curl -fsS "$OLLAMA_HEALTH_URL" >/dev/null 2>&1; then
  echo "Starting Ollama..."
  nohup ollama serve >/tmp/jparty-ollama.log 2>&1 &
fi
wait_for_url "$OLLAMA_HEALTH_URL" "Ollama"

if ! ollama list | awk 'NR > 1 {print $1}' | grep -qx "$LLM_MODEL"; then
  echo "Ollama model '$LLM_MODEL' is not installed."
  echo "Run: ollama pull $LLM_MODEL"
  exit 1
fi

if ! curl -fsS "http://127.0.0.1:${STT_PORT}" >/dev/null 2>&1; then
  echo "Starting whisper.cpp..."
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
  echo "Starting built-in macOS TTS bridge..."
  nohup python3 "${SCRIPT_DIR}/local_macos_tts_server.py" \
    --host 127.0.0.1 \
    --port "$TTS_PORT" \
    >/tmp/jparty-macos-tts.log 2>&1 &
fi
wait_for_url "http://127.0.0.1:${TTS_PORT}/health" "macOS TTS"

echo
echo "Full local Auto Host services are running."
echo
echo "JParty Settings:"
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
