#!/usr/bin/env bash
set -euo pipefail

VOICE_NAME="${JPARTY_VOICE_CLONE_NAME:-my_voice}"
VOICE_SAMPLE="${JPARTY_VOICE_SAMPLE:-}"
VOICE_PORT="${JPARTY_VOICE_CLONE_PORT:-8890}"
APP_SUPPORT="${HOME}/Library/Application Support/JParty/local-auto-host"
VOICE_DIR="${APP_SUPPORT}/voice-clone"
VOICE_FILE="${VOICE_DIR}/voices/${VOICE_NAME}.wav"
CONTAINER_NAME="jparty-voice-clone-tts"
IMAGE_NAME="ghcr.io/matatonic/openedai-speech:latest"

usage() {
  cat <<EOF
Set up the optional local voice-clone TTS addon for Auto Host.

Usage:
  scripts/setup_voice_clone_auto_host_macos.sh
  JPARTY_VOICE_SAMPLE=/path/to/voice.wav scripts/setup_voice_clone_auto_host_macos.sh
  JPARTY_VOICE_CLONE_NAME=ben JPARTY_VOICE_SAMPLE=/path/to/voice.m4a scripts/setup_voice_clone_auto_host_macos.sh

Use a clear 20-60 second recording of your own voice. WAV, M4A, and MP3 are ok;
the script converts it to WAV with ffmpeg.
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

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This helper is for macOS."
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg is required to prepare the voice sample."
  echo "Run scripts/setup_full_local_auto_host_macos.sh first."
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker Desktop is required for the voice-clone addon."
  echo "Run scripts/setup_full_local_auto_host_macos.sh first."
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
  echo "Docker Desktop did not become ready. Open Docker Desktop, then rerun this script."
  exit 1
fi

if [[ -z "$VOICE_SAMPLE" ]]; then
  echo "Choose a clean 20-60 second recording of your own voice."
  read -r -p "Path to voice sample file: " VOICE_SAMPLE
fi

VOICE_SAMPLE="${VOICE_SAMPLE/#\~/$HOME}"
if [[ ! -f "$VOICE_SAMPLE" ]]; then
  echo "Voice sample was not found: $VOICE_SAMPLE"
  exit 1
fi

mkdir -p "${VOICE_DIR}/voices" "${VOICE_DIR}/config"

echo "Preparing voice sample: $VOICE_FILE"
ffmpeg -y -loglevel error -i "$VOICE_SAMPLE" -ac 1 -ar 24000 "$VOICE_FILE"

cat >"${VOICE_DIR}/config/voice_to_speaker.yaml" <<EOF
tts-1-hd:
  ${VOICE_NAME}:
    model: xtts
    speaker: voices/${VOICE_NAME}.wav
    language: en
EOF

cat >"${VOICE_DIR}/voice-clone.env" <<EOF
JPARTY_VOICE_CLONE_ENABLED=yes
JPARTY_VOICE_CLONE_PORT=${VOICE_PORT}
JPARTY_VOICE_CLONE_URL=http://localhost:${VOICE_PORT}/v1
JPARTY_VOICE_CLONE_MODEL=tts-1-hd
JPARTY_VOICE_CLONE_VOICE=${VOICE_NAME}
EOF

if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "Voice-clone TTS container is already running."
elif docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "Replacing existing voice-clone TTS container so it uses the latest sample/config..."
  docker rm -f "$CONTAINER_NAME" >/dev/null || true
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "Starting voice-clone TTS container. The image download/model warmup can take a while."
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
echo "Voice-clone TTS addon is running."
echo
echo "Use these JParty local TTS settings:"
echo "  Local TTS URL: http://localhost:${VOICE_PORT}/v1"
echo "  Local TTS model: tts-1-hd"
echo "  Local TTS voice: ${VOICE_NAME}"
echo
echo "The full start/stop scripts will now include the voice-clone addon."
echo "Config marker: ${VOICE_DIR}/voice-clone.env"
