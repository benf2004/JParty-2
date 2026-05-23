#!/usr/bin/env bash
set -euo pipefail

VOICE_NAME="${JPARTY_KOKOCLONE_VOICE_NAME:-my_voice}"
VOICE_SAMPLE="${JPARTY_VOICE_SAMPLE:-${JPARTY_KOKOCLONE_SAMPLE:-}}"
VOICE_PORT="${JPARTY_KOKOCLONE_PORT:-8892}"
VOICE_LANG="${JPARTY_KOKOCLONE_LANG:-en}"
APP_SUPPORT="${HOME}/Library/Application Support/JParty/local-auto-host"
KOKO_DIR="${APP_SUPPORT}/kokoclone"
SRC_DIR="${KOKO_DIR}/src"
VENV_DIR="${KOKO_DIR}/.venv"
VOICE_FILE="${KOKO_DIR}/voices/${VOICE_NAME}.wav"
ENV_FILE="${KOKO_DIR}/kokoclone.env"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<EOF
Set up the optional local KokoClone TTS addon for Auto Host.

Usage:
  scripts/setup_kokoclone_auto_host_macos.sh
  JPARTY_VOICE_SAMPLE=/path/to/voice.wav scripts/setup_kokoclone_auto_host_macos.sh
  JPARTY_KOKOCLONE_VOICE_NAME=ben JPARTY_VOICE_SAMPLE=/path/to/voice.m4a scripts/setup_kokoclone_auto_host_macos.sh

Use a clean 10-60 second recording of your own voice. WAV, M4A, and MP3 are ok;
the script converts it to WAV with ffmpeg. KokoClone uses Python 3.12 and runs
without Docker.
EOF
}

confirm() {
  local prompt="$1"
  read -r -p "$prompt [y/N] " answer
  [[ "$answer" =~ ^[Yy]$ ]]
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

python312_command() {
  if command -v python3.12 >/dev/null 2>&1; then
    echo "python3.12"
    return 0
  fi
  if command -v /opt/homebrew/bin/python3.12 >/dev/null 2>&1; then
    echo "/opt/homebrew/bin/python3.12"
    return 0
  fi
  if command -v /usr/local/bin/python3.12 >/dev/null 2>&1; then
    echo "/usr/local/bin/python3.12"
    return 0
  fi
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

require_command git "Install Apple's Command Line Tools or Homebrew git."
require_command ffmpeg "Run scripts/setup_full_local_auto_host_macos.sh first, or install ffmpeg with Homebrew."

if command -v brew >/dev/null 2>&1 && ! brew list --formula espeak-ng >/dev/null 2>&1; then
  echo "Installing espeak-ng for KokoClone phoneme support..."
  brew install espeak-ng
fi

PYTHON_BIN="$(python312_command || true)"
if [[ -z "$PYTHON_BIN" ]]; then
  if ! command -v brew >/dev/null 2>&1; then
    echo "Python 3.12 is required for KokoClone, and Homebrew was not found."
    echo "Install Python 3.12, then rerun this script."
    exit 1
  fi
  if confirm "Python 3.12 is required. Install Homebrew package python@3.12 now?"; then
    brew install python@3.12
    PYTHON_BIN="$(python312_command || true)"
  fi
fi

if [[ -z "$PYTHON_BIN" ]]; then
  echo "Python 3.12 was not found. Install it, then rerun this script."
  exit 1
fi

if [[ -z "$VOICE_SAMPLE" ]]; then
  echo "Choose a clean 10-60 second recording of your own voice."
  read -r -p "Path to voice sample file: " VOICE_SAMPLE
fi

VOICE_SAMPLE="${VOICE_SAMPLE/#\~/$HOME}"
if [[ ! -f "$VOICE_SAMPLE" ]]; then
  echo "Voice sample was not found: $VOICE_SAMPLE"
  exit 1
fi

mkdir -p "${KOKO_DIR}/voices"

if [[ -d "$SRC_DIR/.git" ]]; then
  echo "Updating KokoClone source..."
  git -C "$SRC_DIR" pull --ff-only
else
  echo "Downloading KokoClone source..."
  rm -rf "$SRC_DIR"
  git clone https://github.com/Ashish-Patnaik/kokoclone.git "$SRC_DIR"
fi

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  echo "Creating KokoClone Python environment..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

echo "Installing KokoClone dependencies. This can take several minutes."
"${VENV_DIR}/bin/python" -m pip install --upgrade pip setuptools wheel
"${VENV_DIR}/bin/python" -m pip install torch torchaudio
"${VENV_DIR}/bin/python" -m pip install \
  soundfile \
  huggingface_hub \
  gradio \
  kokoro-onnx \
  "misaki[en,ja,zh]" \
  "git+https://github.com/frothywater/kanade-tokenizer"

echo "Preparing voice sample: $VOICE_FILE"
ffmpeg -y -loglevel error -i "$VOICE_SAMPLE" -ac 1 -ar 24000 "$VOICE_FILE"

{
  printf 'JPARTY_KOKOCLONE_ENABLED=yes\n'
  printf 'JPARTY_KOKOCLONE_PORT=%q\n' "$VOICE_PORT"
  printf 'JPARTY_KOKOCLONE_URL=%q\n' "http://localhost:${VOICE_PORT}/v1"
  printf 'JPARTY_KOKOCLONE_MODEL=kokoclone\n'
  printf 'JPARTY_KOKOCLONE_VOICE=%q\n' "$VOICE_NAME"
  printf 'JPARTY_KOKOCLONE_LANG=%q\n' "$VOICE_LANG"
  printf 'JPARTY_KOKOCLONE_REF_AUDIO=%q\n' "$VOICE_FILE"
  printf 'JPARTY_KOKOCLONE_SRC_DIR=%q\n' "$SRC_DIR"
  printf 'JPARTY_KOKOCLONE_VENV=%q\n' "$VENV_DIR"
} >"$ENV_FILE"

"${SCRIPT_DIR}/start_kokoclone_auto_host_macos.sh"

echo
echo "KokoClone TTS addon is running."
echo
echo "Use these JParty local TTS settings:"
echo "  Local TTS: KokoClone cloned voice"
echo "  Local TTS URL: http://localhost:${VOICE_PORT}/v1"
echo "  Local TTS model: kokoclone"
echo "  Local TTS voice: ${VOICE_NAME}"
echo
echo "Config marker: ${ENV_FILE}"
