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
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<EOF
Set up a fully local beginner Auto Host stack on macOS:
  - Ollama local LLM for clue parsing and answer judging
  - whisper.cpp local Whisper server for speech-to-text
  - Kokoro local TTS server for text-to-speech
  - optional KokoClone clone TTS addon

Usage:
  scripts/setup_full_local_auto_host_macos.sh
  JPARTY_LOCAL_LLM_MODEL=llama3.2:3b scripts/setup_full_local_auto_host_macos.sh
  JPARTY_WHISPER_MODEL=small.en scripts/setup_full_local_auto_host_macos.sh

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

wait_for_url() {
  local url="$1"
  local name="$2"
  for _ in {1..15}; do
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
  echo "Warning: this Mac is not Apple Silicon. Local models may be slower."
fi

ENABLE_VOICE_CLONE="${JPARTY_ENABLE_VOICE_CLONE:-ask}"
if [[ "$ENABLE_VOICE_CLONE" == "ask" ]]; then
  read -r -p "Would you like to set up KokoClone voice cloning for your own host voice? [y/N] " clone_answer
  if [[ "$clone_answer" =~ ^[Yy]$ ]]; then
    ENABLE_VOICE_CLONE="yes"
  else
    ENABLE_VOICE_CLONE="no"
  fi
fi

install_homebrew_if_needed
install_brew_package_if_needed ollama ollama
install_brew_package_if_needed ffmpeg ffmpeg
install_brew_package_if_needed whisper-server whisper-cpp
if [[ ! "$ENABLE_VOICE_CLONE" =~ ^(yes|true|1)$ ]]; then
  install_brew_cask_if_needed "/Applications/Docker.app" docker
fi

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

if [[ "$ENABLE_VOICE_CLONE" =~ ^(yes|true|1)$ ]]; then
  "${SCRIPT_DIR}/voice_clone/setup_kokoclone_auto_host_macos.sh"
  VOICE_ENV="${APP_SUPPORT}/kokoclone/kokoclone.env"
  if [[ -f "$VOICE_ENV" ]]; then
    source "$VOICE_ENV"
    TTS_PORT="${JPARTY_KOKOCLONE_PORT:-8892}"
    TTS_URL="${JPARTY_KOKOCLONE_URL:-http://localhost:${TTS_PORT}/v1}"
    TTS_MODEL="${JPARTY_KOKOCLONE_MODEL:-kokoclone}"
    TTS_VOICE="${JPARTY_KOKOCLONE_VOICE:-my_voice}"
  fi
else
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
fi

echo
echo "Fully local Auto Host setup is running."
echo
echo "Use these JParty Settings:"
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
echo "  TTS: docker logs jparty-kokoro-tts"
echo "  KokoClone: /tmp/jparty-kokoclone-adapter.log"
echo
echo "To stop the background services later:"
echo "  pkill -f 'ollama serve'"
echo "  pkill -f 'whisper-server'"
echo "  docker stop jparty-kokoro-tts"
echo "  scripts/voice_clone.sh stop-kokoclone"
