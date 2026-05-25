#!/usr/bin/env bash
set -euo pipefail

MODEL="${JPARTY_LOCAL_LLM_MODEL:-qwen2.5:7b}"
LLM_URL="${JPARTY_LOCAL_LLM_BASE_URL:-http://localhost:11434/v1}"
OLLAMA_HEALTH_URL="${LLM_URL%/v1}/api/tags"

usage() {
  cat <<EOF
Set up the beginner local Auto Host LLM path for macOS.

Usage:
  scripts/setup_local_auto_host_macos.sh
  JPARTY_LOCAL_LLM_MODEL=llama3.2:3b scripts/setup_local_auto_host_macos.sh

This installs/checks Homebrew, Ollama, and ffmpeg, pulls a local model, and
prints the JParty settings to use. It does not edit your JParty config.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This helper is for macOS. See AUTOHOST.md for manual local setup."
  exit 1
fi

if [[ "$(uname -m)" != "arm64" ]]; then
  echo "Warning: this Mac is not Apple Silicon. Local models may be slower."
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required to install Ollama and ffmpeg."
  read -r -p "Install Homebrew now? [y/N] " install_brew
  if [[ ! "$install_brew" =~ ^[Yy]$ ]]; then
    echo "Stopped. Install Homebrew from https://brew.sh, then run this script again."
    exit 1
  fi
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

if ! command -v ollama >/dev/null 2>&1; then
  echo "Installing Ollama..."
  brew install ollama
else
  echo "Ollama is already installed."
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Installing ffmpeg..."
  brew install ffmpeg
else
  echo "ffmpeg is already installed."
fi

if ! curl -fsS "$OLLAMA_HEALTH_URL" >/dev/null 2>&1; then
  echo "Starting Ollama in the background..."
  nohup ollama serve >/tmp/jparty-ollama.log 2>&1 &
  sleep 3
fi

if ! curl -fsS "$OLLAMA_HEALTH_URL" >/dev/null 2>&1; then
  echo "Could not reach Ollama at $OLLAMA_HEALTH_URL."
  echo "Try running this in another terminal, then rerun this script:"
  echo "  ollama serve"
  exit 1
fi

echo "Pulling local LLM model: $MODEL"
ollama pull "$MODEL"

echo
echo "Local LLM setup is ready."
echo
echo "Use these JParty Settings:"
echo "  Auto Host AI provider: local"
echo "  Local LLM URL: $LLM_URL"
echo "  Local LLM model: $MODEL"
echo
echo "For full local voice, also start OpenAI-compatible STT and TTS services:"
echo "  Local STT URL: http://localhost:8082/v1"
echo "  Local STT model: whisper"
echo "  Local TTS URL: http://localhost:8880/v1"
echo "  Local TTS model: macos-say"
echo "  Local TTS voice: leave blank for Mac default, or type your Personal Voice name"
echo
echo "See AUTOHOST.md for beginner STT/TTS options."
