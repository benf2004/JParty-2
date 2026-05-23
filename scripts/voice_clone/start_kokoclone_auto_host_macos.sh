#!/usr/bin/env bash
set -euo pipefail

APP_SUPPORT="${HOME}/Library/Application Support/JParty/local-auto-host"
KOKO_DIR="${APP_SUPPORT}/kokoclone"
ENV_FILE="${KOKO_DIR}/kokoclone.env"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADAPTER_PID_FILE="/tmp/jparty-kokoclone-adapter.pid"

usage() {
  cat <<EOF
Start the optional KokoClone TTS addon.

Usage:
  scripts/start_kokoclone_auto_host_macos.sh

Run scripts/setup_kokoclone_auto_host_macos.sh first if the addon has not been
configured.
EOF
}

wait_for_url() {
  local url="$1"
  local name="$2"
  for _ in {1..120}; do
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
  echo "KokoClone addon is not configured."
  echo "Run scripts/setup_kokoclone_auto_host_macos.sh first."
  exit 1
fi

source "$ENV_FILE"
VOICE_PORT="${JPARTY_KOKOCLONE_PORT:-8892}"
VOICE_LANG="${JPARTY_KOKOCLONE_LANG:-en}"
VOICE_FILE="${JPARTY_KOKOCLONE_REF_AUDIO:?Missing JPARTY_KOKOCLONE_REF_AUDIO in $ENV_FILE}"
SRC_DIR="${JPARTY_KOKOCLONE_SRC_DIR:?Missing JPARTY_KOKOCLONE_SRC_DIR in $ENV_FILE}"
VENV_DIR="${JPARTY_KOKOCLONE_VENV:?Missing JPARTY_KOKOCLONE_VENV in $ENV_FILE}"

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  echo "KokoClone Python environment was not found: ${VENV_DIR}"
  echo "Run scripts/setup_kokoclone_auto_host_macos.sh again."
  exit 1
fi

if [[ ! -f "$VOICE_FILE" ]]; then
  echo "KokoClone voice sample was not found: $VOICE_FILE"
  echo "Run scripts/setup_kokoclone_auto_host_macos.sh again."
  exit 1
fi

if ! curl -fsS "http://127.0.0.1:${VOICE_PORT}/health" >/dev/null 2>&1; then
  echo "Starting KokoClone adapter. First start can take a while while models load..."
  if [[ -f "$ADAPTER_PID_FILE" ]] && ! kill -0 "$(cat "$ADAPTER_PID_FILE")" >/dev/null 2>&1; then
    rm -f "$ADAPTER_PID_FILE"
  fi
  nohup "${VENV_DIR}/bin/python" -u "${SCRIPT_DIR}/kokoclone_openai_tts_adapter.py" \
    --host 127.0.0.1 \
    --port "$VOICE_PORT" \
    --repo-dir "$SRC_DIR" \
    --reference-audio "$VOICE_FILE" \
    --language "$VOICE_LANG" \
    >/tmp/jparty-kokoclone-adapter.log 2>&1 &
  echo "$!" > "$ADAPTER_PID_FILE"
else
  echo "KokoClone adapter is already running."
fi

wait_for_url "http://127.0.0.1:${VOICE_PORT}/health" "KokoClone adapter"

echo
echo "KokoClone clone TTS is running."
echo "  Local TTS URL: http://localhost:${VOICE_PORT}/v1"
echo "  Local TTS model: ${JPARTY_KOKOCLONE_MODEL:-kokoclone}"
echo "  Local TTS voice: ${JPARTY_KOKOCLONE_VOICE:-my_voice}"
echo "  Log: /tmp/jparty-kokoclone-adapter.log"
