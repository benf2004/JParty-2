#!/usr/bin/env bash
set -euo pipefail

LLM_MODEL="${JPARTY_LOCAL_LLM_MODEL:-qwen2.5:7b}"
LLM_URL="${JPARTY_LOCAL_LLM_BASE_URL:-http://localhost:11434/v1}"
STT_PORT="${JPARTY_LOCAL_STT_PORT:-8082}"
STT_URL="http://localhost:${STT_PORT}/v1"
TTS_PORT="${JPARTY_LOCAL_TTS_PORT:-8880}"
TTS_URL="http://localhost:${TTS_PORT}/v1"
TTS_ENGINE="${JPARTY_LOCAL_TTS_ENGINE:-ask}"
TTS_MODEL=""
TTS_VOICE=""
TTS_LABEL=""
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
  - built-in macOS speech or Kokoro for text-to-speech

Usage:
  scripts/setup_full_local_auto_host_macos.sh
  JPARTY_LOCAL_LLM_MODEL=llama3.2:3b scripts/setup_full_local_auto_host_macos.sh
  JPARTY_WHISPER_MODEL=small.en scripts/setup_full_local_auto_host_macos.sh
  JPARTY_LOCAL_TTS_ENGINE=kokoro scripts/setup_full_local_auto_host_macos.sh
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

install_brew_cask_if_needed() {
  local app_path="$1"
  local cask_name="$2"
  if [[ -e "$app_path" ]]; then
    echo "$cask_name is already installed."
    return
  fi
  echo "Installing $cask_name..."
  brew install --cask "$cask_name"
}

choose_tts_engine() {
  case "$TTS_ENGINE" in
    macos|macos-say|say)
      TTS_ENGINE="macos"
      ;;
    kokoro)
      TTS_ENGINE="kokoro"
      ;;
    ask|"")
      read -r -p "Use which local TTS? [m]acOS Say / [k]okoro [m] " tts_answer
      if [[ "$tts_answer" =~ ^[Kk] ]]; then
        TTS_ENGINE="kokoro"
      else
        TTS_ENGINE="macos"
      fi
      ;;
    *)
      echo "Unknown JPARTY_LOCAL_TTS_ENGINE: $TTS_ENGINE"
      echo "Use macos or kokoro."
      exit 1
      ;;
  esac

  if [[ "$TTS_ENGINE" == "kokoro" ]]; then
    TTS_MODEL="kokoro"
    TTS_VOICE="${JPARTY_KOKORO_TTS_VOICE:-af_heart}"
    TTS_LABEL="Kokoro"
  else
    TTS_MODEL="macos-say"
    TTS_VOICE="${JPARTY_MACOS_TTS_VOICE:-}"
    TTS_LABEL="macOS Say / Personal Voice"
  fi
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

stop_process() {
  local pattern="$1"
  local label="$2"
  if pgrep -f "$pattern" >/dev/null 2>&1; then
    echo "Stopping $label..."
    pkill -f "$pattern" || true
  fi
}

macos_tts_ready() {
  local body
  body="$(curl -fsS "http://127.0.0.1:${TTS_PORT}/health" 2>/dev/null || true)"
  [[ "$body" == *'"engine": "macos-say"'* || "$body" == *'"engine":"macos-say"'* ]]
}

kokoro_tts_ready() {
  curl -fsS "http://127.0.0.1:${TTS_PORT}/v1/audio/voices" >/dev/null 2>&1 && ! macos_tts_ready
}

stop_legacy_tts_on_port() {
  if macos_tts_ready; then
    return
  fi
  if ! curl -fsS "http://127.0.0.1:${TTS_PORT}/health" >/dev/null 2>&1; then
    return
  fi
  if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' | grep -qx 'jparty-kokoro-tts'; then
    echo "Port ${TTS_PORT} is occupied by the old Kokoro TTS container. Stopping it..."
    docker stop jparty-kokoro-tts >/dev/null || true
    return
  fi
  echo "Port ${TTS_PORT} is occupied by a non-macOS TTS server."
  echo "Stop that service or set JPARTY_LOCAL_TTS_PORT to another port, then rerun this script."
  exit 1
}

wait_for_macos_tts() {
  for _ in {1..30}; do
    if macos_tts_ready; then
      echo "macOS TTS is reachable."
      return 0
    fi
    sleep 1
  done
  echo "macOS TTS did not become reachable at http://127.0.0.1:${TTS_PORT}/health."
  echo "Check /tmp/jparty-macos-tts.log for details."
  return 1
}

start_macos_tts() {
  stop_legacy_tts_on_port
  if ! macos_tts_ready; then
    echo "Starting built-in macOS TTS bridge in the background..."
    nohup python3 "${SCRIPT_DIR}/local_macos_tts_server.py" \
      --host 127.0.0.1 \
      --port "$TTS_PORT" \
      >/tmp/jparty-macos-tts.log 2>&1 &
  fi
  wait_for_macos_tts
}

start_kokoro_tts() {
  stop_process "local_macos_tts_server.py" "macOS TTS bridge"
  install_brew_cask_if_needed "/Applications/Docker.app" docker
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker command was not found after installing Docker Desktop."
    echo "Open Docker Desktop once, finish its setup, then rerun this script."
    exit 1
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "Docker Desktop is not running. Opening it now..."
    open -a Docker || true
    echo "Waiting for Docker Desktop to start. This can take a minute the first time."
    for _ in {1..90}; do
      if docker info >/dev/null 2>&1; then
        break
      fi
      sleep 2
    done
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "Docker Desktop did not become ready."
    echo "Open Docker Desktop, finish any first-run prompts, then rerun this script."
    exit 1
  fi
  if docker ps --format '{{.Names}}' | grep -qx 'jparty-kokoro-tts'; then
    echo "Kokoro TTS container is already running."
  elif docker ps -a --format '{{.Names}}' | grep -qx 'jparty-kokoro-tts'; then
    echo "Starting existing Kokoro TTS container..."
    docker start jparty-kokoro-tts >/dev/null
  else
    echo "Starting Kokoro TTS container. The image download can take a while the first time."
    docker run -d \
      --name jparty-kokoro-tts \
      -p "127.0.0.1:${TTS_PORT}:8880" \
      ghcr.io/remsky/kokoro-fastapi-cpu:latest >/dev/null
  fi
  wait_for_url "http://127.0.0.1:${TTS_PORT}/v1/audio/voices" "Kokoro TTS"
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

choose_tts_engine
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

if [[ "$TTS_ENGINE" == "kokoro" ]]; then
  start_kokoro_tts
else
  start_macos_tts
fi

echo
if [[ "$TTS_ENGINE" == "macos" ]]; then
  echo "Visible macOS speech voices:"
  python3 "${SCRIPT_DIR}/local_macos_tts_server.py" --list-voices | sed -n '1,20p'
  echo
fi

echo "Fully local Auto Host setup is running."
echo
if [[ "$TTS_ENGINE" == "macos" ]]; then
  echo "For your own Personal Voice:"
  echo "  1. Create it in System Settings > Accessibility > Personal Voice."
  echo "  2. Turn on Allow applications to use your Personal Voice."
  echo "  3. Choose Custom / Personal Voice in JParty and enter the exact voice name."
  echo
fi
echo "Use these JParty Settings:"
echo "  Auto Host AI provider: local"
echo "  Local LLM URL: $LLM_URL"
echo "  Local LLM model: $LLM_MODEL"
echo "  Local STT URL: $STT_URL"
echo "  Local STT model: whisper"
echo "  Local TTS: $TTS_LABEL"
echo "  Local TTS URL: $TTS_URL"
echo "  Local TTS model: $TTS_MODEL"
if [[ -n "$TTS_VOICE" ]]; then
  echo "  Local TTS voice: $TTS_VOICE"
else
  echo "  Local TTS voice: leave blank for the Mac default, or choose Custom / Personal Voice"
fi
echo
echo "Logs:"
echo "  Ollama: /tmp/jparty-ollama.log"
echo "  Whisper: /tmp/jparty-whisper-server.log"
if [[ "$TTS_ENGINE" == "macos" ]]; then
  echo "  macOS TTS: /tmp/jparty-macos-tts.log"
else
  echo "  Kokoro: docker logs jparty-kokoro-tts"
fi
echo
echo "To stop the background services later:"
echo "  scripts/stop_full_local_auto_host_macos.sh"
