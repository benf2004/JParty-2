# Fully Local Auto Host Setup For Beginners

This guide gets Auto Host running without paid AI APIs. Everything runs on your Mac.

## What You Are Installing

- **Ollama** runs the local LLM. JParty uses it to understand clue choices and judge ambiguous answers.
- **whisper.cpp** runs Whisper locally. JParty uses it to turn player microphone recordings into text.
- **Kokoro-FastAPI** runs a better local voice server. JParty uses it to speak host lines.
- **Docker Desktop** runs Kokoro without making you set up a Python voice server by hand.
- **ffmpeg** converts audio formats so phone recordings and generated speech work smoothly.

JParty does not secretly install or launch these during a game. You run the setup script yourself, and the script starts local services on your computer.

## One-Command Beginner Setup

From the JParty2 project folder, run:

```bash
scripts/setup_full_local_auto_host_macos.sh
```

That script will:

1. Check that you are on macOS.
2. Install Homebrew if you approve it.
3. Install/check Ollama, whisper.cpp, ffmpeg, and Docker Desktop.
4. Download a local Whisper model.
5. Pull a local Ollama model.
6. Start the local LLM, STT, and Kokoro TTS services.
7. Print the exact JParty settings to use.

The default choices are meant for a 16 GB Apple Silicon Mac:

```text
LLM: qwen2.5:7b
Whisper: base.en
TTS: Kokoro af_heart
```

During setup, the script asks whether you want to set up voice cloning. If you say yes, it runs the separate voice-clone addon setup and prints cloned-voice TTS settings instead of Kokoro settings.

## Smaller Or Larger Models

If the LLM feels slow, use the smaller model:

```bash
JPARTY_LOCAL_LLM_MODEL=llama3.2:3b scripts/setup_full_local_auto_host_macos.sh
```

If speech recognition misses too much, try a larger Whisper model:

```bash
JPARTY_WHISPER_MODEL=small.en scripts/setup_full_local_auto_host_macos.sh
```

Good starting choices:

```text
Fastest Whisper: tiny.en
Recommended Whisper: base.en
Better but slower Whisper: small.en
```

## JParty Settings

After the script finishes, open JParty Settings and use:

```text
Auto Host: True
Auto Host AI provider: local
Local LLM URL: http://localhost:11434/v1
Local LLM model: qwen2.5:7b
Local STT URL: http://localhost:8082/v1
Local STT model: whisper
Local TTS URL: http://localhost:8880/v1
Local TTS model: kokoro
Local TTS voice: af_heart
```

Kokoro voices are much more natural than the built-in macOS voices. `af_heart` is the beginner default because it is warm and clear.

If Docker or Kokoro gives you trouble, this repo also includes a simple fallback macOS voice bridge:

```bash
scripts/local_macos_tts_server.py
```

For that fallback, use `Local TTS model: macos-say` and a macOS voice such as `Samantha`.

## What Runs Where

```text
Player phone audio
  -> JParty
  -> whisper.cpp at http://localhost:8082/v1/audio/transcriptions
  -> transcript text
  -> Ollama at http://localhost:11434/v1/chat/completions
  -> judgement or clue choice
  -> Kokoro TTS at http://localhost:8880/v1/audio/speech
  -> host voice from computer speakers
```

## Stopping Services

After setup, you do not need to reinstall anything for game night. Start the local services with:

```bash
scripts/start_full_local_auto_host_macos.sh
```

When you are done playing, stop them with:

```bash
scripts/stop_full_local_auto_host_macos.sh
```

The setup script also prints logs and manual stop commands. The common stop commands are:

```bash
pkill -f 'ollama serve'
pkill -f 'whisper-server'
docker stop jparty-kokoro-tts
```

## Uninstalling The Full Local Setup

To remove the full local Auto Host services and downloaded model files:

```bash
scripts/uninstall_full_local_auto_host_macos.sh
```

The uninstall script does not remove Homebrew and does not edit your JParty settings. It can remove the Ollama, whisper.cpp, ffmpeg, Docker Desktop, Kokoro container/image, and downloaded Whisper files if you confirm those prompts.

## Troubleshooting

If JParty says it did not catch speech, check that whisper.cpp is running:

```bash
curl http://127.0.0.1:8082
```

If the host does not speak, check the Kokoro TTS server:

```bash
curl http://127.0.0.1:8880/v1/audio/voices
```

If judging is slow, switch to:

```bash
JPARTY_LOCAL_LLM_MODEL=llama3.2:3b scripts/setup_full_local_auto_host_macos.sh
```

If transcription is poor, switch to:

```bash
JPARTY_WHISPER_MODEL=small.en scripts/setup_full_local_auto_host_macos.sh
```
