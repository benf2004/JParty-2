#!/usr/bin/env bash
set -euo pipefail

LLM_MODEL="${JPARTY_LOCAL_LLM_MODEL:-qwen2.5:7b}"
LLM_URL="${JPARTY_LOCAL_LLM_BASE_URL:-http://localhost:11434/v1}"
STT_PORT="${JPARTY_LOCAL_STT_PORT:-8082}"
STT_URL="http://localhost:${STT_PORT}/v1"
TTS_PORT="${JPARTY_LOCAL_TTS_PORT:-8880}"
TTS_URL="http://localhost:${TTS_PORT}/v1"
TTS_MODEL="kokoro"
TTS_VOICE="af_heart"
WHISPER_MODEL="${JPARTY_WHISPER_MODEL:-base.en}"
APP_SUPPORT="${HOME}/Library/Application Support/JParty/local-auto-host"
WHISPER_MODEL_FILE="${APP_SUPPORT}/models/ggml-${WHISPER_MODEL}.bin"
OLLAMA_HEALTH_URL="${LLM_URL%/v1}/api/tags"
VOICE_ENV="${APP_SUPPORT}/voice-clone/voice-clone.env"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<EOF
Start already-installed full local Auto Host services for game night.

Usage:
  scripts/start_full_local_auto_host_macos.sh
  JPARTY_LOCAL_LLM_MODEL=llama3.2:3b scripts/start_full_local_auto_host_macos.sh
  JPARTY_WHISPER_MODEL=small.en scripts/start_full_local_auto_host_macos.sh

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
require_command docker "Open/install Docker Desktop, or run scripts/setup_full_local_auto_host_macos.sh first."

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

if ! docker info >/dev/null 2>&1; then
  echo "Docker Desktop is not running. Opening it now..."
  open -a Docker || true
  for _ in {1..90}; do
    if docker info >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker Desktop did not become ready. Open Docker Desktop, then rerun this script."
  exit 1
fi

if [[ -f "$VOICE_ENV" ]]; then
  echo "Voice-clone addon is configured; starting cloned-voice TTS..."
  "${SCRIPT_DIR}/start_voice_clone_auto_host_macos.sh"
  source "$VOICE_ENV"
  TTS_PORT="${JPARTY_VOICE_CLONE_PORT:-8890}"
  TTS_URL="${JPARTY_VOICE_CLONE_URL:-http://localhost:${TTS_PORT}/v1}"
  TTS_MODEL="${JPARTY_VOICE_CLONE_MODEL:-tts-1-hd}"
  TTS_VOICE="${JPARTY_VOICE_CLONE_VOICE:-my_voice}"
else
  if docker ps --format '{{.Names}}' | grep -qx 'jparty-kokoro-tts'; then
    echo "Kokoro TTS is already running."
  elif docker ps -a --format '{{.Names}}' | grep -qx 'jparty-kokoro-tts'; then
    echo "Starting Kokoro TTS..."
    docker start jparty-kokoro-tts >/dev/null
  else
    echo "Kokoro TTS container was not found."
    echo "Run scripts/setup_full_local_auto_host_macos.sh first."
    exit 1
  fi
  wait_for_url "http://127.0.0.1:${TTS_PORT}/v1/audio/voices" "Kokoro TTS"
fi

echo
echo "Full local Auto Host services are running."
echo
echo "JParty Settings:"
echo "  Auto Host AI provider: local"
echo "  Local LLM URL: $LLM_URL"
echo "  Local LLM model: $LLM_MODEL"
echo "  Local STT URL: $STT_URL"
echo "  Local STT model: whisper"
echo "  Local TTS URL: $TTS_URL"
echo "  Local TTS model: $TTS_MODEL"
echo "  Local TTS voice: $TTS_VOICE"
echo
echo "Logs:"
echo "  Ollama: /tmp/jparty-ollama.log"
echo "  Whisper: /tmp/jparty-whisper-server.log"
echo "  Kokoro: docker logs jparty-kokoro-tts"
echo "  Voice clone: docker logs jparty-voice-clone-tts"
