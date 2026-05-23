#!/usr/bin/env bash
set -euo pipefail

APP_SUPPORT="${HOME}/Library/Application Support/JParty/local-auto-host"
VOICE_DIR="${APP_SUPPORT}/voice-clone"
ENV_FILE="${VOICE_DIR}/voice-clone.env"
CONTAINER_NAME="jparty-voice-clone-tts"
IMAGE_NAME="ghcr.io/matatonic/openedai-speech:latest"

usage() {
  cat <<EOF
Start the optional voice-clone TTS addon.

Usage:
  scripts/start_voice_clone_auto_host_macos.sh

Run scripts/setup_voice_clone_auto_host_macos.sh first if the addon has not
been configured.
EOF
}

wait_for_url() {
  local url="$1"
  local name="$2"
  for _ in {1..90}; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "$name is ready."
      return 0
    fi
    sleep 2
  done
  echo "$name did not become ready at $url."
  return 1
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Voice-clone addon is not configured."
  echo "Run scripts/setup_voice_clone_auto_host_macos.sh first."
  exit 1
fi

source "$ENV_FILE"
VOICE_PORT="${JPARTY_VOICE_CLONE_PORT:-8890}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker Desktop is required."
  exit 1
fi

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
  echo "Docker Desktop did not become ready."
  exit 1
fi

if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "Voice-clone TTS is already running."
elif docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "Starting voice-clone TTS..."
  docker start "$CONTAINER_NAME" >/dev/null
else
  echo "Creating voice-clone TTS container..."
  docker run -d \
    --name "$CONTAINER_NAME" \
    -p "127.0.0.1:${VOICE_PORT}:8000" \
    -e TTS_HOME=voices \
    -e HF_HOME=voices \
    -e EXTRA_ARGS="--xtts_device cpu" \
    -v "${VOICE_DIR}/voices:/app/voices" \
    -v "${VOICE_DIR}/config:/app/config" \
    "$IMAGE_NAME" >/dev/null
fi

wait_for_url "http://127.0.0.1:${VOICE_PORT}/v1/models" "Voice-clone TTS"

echo
echo "Voice-clone TTS is running."
echo "  Local TTS URL: http://localhost:${VOICE_PORT}/v1"
echo "  Local TTS model: ${JPARTY_VOICE_CLONE_MODEL:-tts-1-hd}"
echo "  Local TTS voice: ${JPARTY_VOICE_CLONE_VOICE:-my_voice}"
