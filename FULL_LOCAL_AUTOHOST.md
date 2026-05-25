# Fully Local Auto Host Setup For Beginners

This guide gets Auto Host running without paid AI APIs. Everything runs on your Mac.

## What You Are Installing

- **Ollama** runs the local LLM. JParty uses it to understand clue choices, normalize clue speech, and judge ambiguous answers.
- **whisper.cpp** runs Whisper locally. JParty uses it to turn player microphone recordings into text.
- **macOS speech** speaks host lines through Apple's built-in speech system, including your Personal Voice when macOS exposes it to apps.
- **Kokoro** is an optional local TTS voice server if you prefer it over macOS Say.
- **ffmpeg** converts generated speech into WAV audio that JParty can play.

JParty does not secretly install or launch these during a game. You run the setup script yourself, and the script starts local services on your computer.

## Personal Voice

Create your Personal Voice in **System Settings > Accessibility > Personal Voice**, then turn on **Allow applications to use your Personal Voice**.

After that, run:

```bash
say -v ?
```

Use the exact Personal Voice name from that list as JParty's **Local TTS voice**. You can also run:

```bash
scripts/local_macos_tts_server.py --list-voices
```

## One-Command Beginner Setup

From the JParty2 project folder, run:

```bash
scripts/setup_full_local_auto_host_macos.sh
```

That script will:

1. Check that you are on macOS.
2. Install Homebrew if you approve it.
3. Install/check Ollama, whisper.cpp, and ffmpeg.
4. Download a local Whisper model.
5. Pull a local Ollama model.
6. Ask whether you want macOS Say or Kokoro for local TTS.
7. Start the local LLM, STT, and selected TTS service.
8. Print the exact JParty settings to use.

The default choices are meant for a 16 GB Apple Silicon Mac:

```text
LLM: qwen2.5:7b
Whisper: base.en
TTS: macOS Say / Personal Voice, or Kokoro if selected
```

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
Local TTS: macOS Say / Personal Voice
Local TTS URL: http://localhost:8880/v1
Local TTS model: macos-say
macOS Say voice: Custom / Personal Voice, then your exact Personal Voice name
```

If you choose Kokoro in the setup script, use:

```text
Local TTS: Kokoro
Kokoro voice: af_heart
```

## What Runs Where

```text
Player phone audio
  -> JParty
  -> whisper.cpp at http://localhost:8082/v1/audio/transcriptions
  -> transcript text
  -> Ollama at http://localhost:11434/v1/chat/completions
  -> judgement, clue choice, or clue speech normalization
  -> selected TTS at http://localhost:8880/v1/audio/speech
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

## Uninstalling The Full Local Setup

To remove the full local Auto Host services and downloaded model files:

```bash
scripts/uninstall_full_local_auto_host_macos.sh
```

The uninstall script does not remove Homebrew and does not edit your JParty settings. It can remove the Ollama, whisper.cpp, ffmpeg, and downloaded Whisper files if you confirm those prompts.

## Troubleshooting

If JParty says it did not catch speech, check that whisper.cpp is running:

```bash
curl http://127.0.0.1:8082
```

If the host does not speak, check the macOS TTS bridge:

```bash
curl http://127.0.0.1:8880/health
curl http://127.0.0.1:8880/v1/audio/voices
```

The `/health` response should include `"engine": "macos-say"`. If JParty logs `Unsupported model: macos-say`, an old TTS server is still running on port `8880`. Run:

```bash
scripts/stop_full_local_auto_host_macos.sh
scripts/start_full_local_auto_host_macos.sh
```

If your Personal Voice does not appear, make sure it is finished processing and **Allow applications to use your Personal Voice** is enabled in macOS Accessibility settings.

If judging is slow, switch to:

```bash
JPARTY_LOCAL_LLM_MODEL=llama3.2:3b scripts/setup_full_local_auto_host_macos.sh
```

If transcription is poor, switch to:

```bash
JPARTY_WHISPER_MODEL=small.en scripts/setup_full_local_auto_host_macos.sh
```
