# Fully Local Auto Host Setup For Beginners

This guide gets Auto Host running without paid AI APIs. Everything runs on your Mac.

## Start from JParty

1. Open **Settings → Auto Host**, choose **Local · on this Mac**, and select your answer judge.
2. Save changes. If you enable Auto Host for the first time, JParty restarts to enable phone microphone access.
3. Open **Settings → Local Services** and click **Set up** once to install tools and models. Choose your voice engine in this tab before setup, and save changes first.
4. For later sessions, click **Start services**. Check each component's status and the activity log; the game becomes startable when its required services are ready, a game is loaded, and players have joined.
5. Click **Stop services** after your session.

Setup/start/stop run in the background, and closing Settings leaves an active command running. Reopen **Settings → Local Services** to view status and progress. Save is disabled while a command is running. Automatic management is macOS-only; other platforms can use externally managed servers and the same readiness checks. If Homebrew has not been installed, install it from [brew.sh](https://brew.sh) in Terminal first; the activity log will prompt you to do so.

The default answer judge uses **Qwen2.5-7B with fast true/false output**, sharing Ollama with text generation. Empty answers are rejected and normalized exact matches are accepted locally; all other answers reach the judge. See [benchmark results](benchmarks/answer_judging/RESULTS.md).

## Optional: Kev-0.8B answer judging

Kev can judge answers while Ollama continues to handle clue selection, speech normalization, and image search text. Keep **Auto Host AI provider** set to `local`, and select **Answer judge → Kev (local decision model)** in Settings.

The full-local scripts install and manage Kev when enabled with `JPARTY_LOCAL_KEV_ENABLED=1` in `~/Library/Application Support/JParty/local-auto-host/kev`, with a separate Python 3.13 environment. Setup installs `uv` if needed, checks out the `kev-1.0` server release, and downloads the model when starting it. This requires several GB of disk space and an internet connection. The scripts print the Settings values to use and do not edit your JParty configuration.

```bash
scripts/setup_full_local_auto_host_macos.sh
scripts/start_full_local_auto_host_macos.sh
scripts/stop_full_local_auto_host_macos.sh
```

Game-night starts use cached model files only. To enable Kev, prefix setup/start with `JPARTY_LOCAL_KEV_ENABLED=1`. Stop still shuts down a managed Kev process even when that flag is disabled. Existing full-local installations need one setup run to install Kev before using the new start script.

Overrides (use the same values for setup and start):

- `JPARTY_LOCAL_KEV_PORT=8009`: loopback server port; copy the printed URL into JParty Settings.
- `JPARTY_LOCAL_KEV_CHECKPOINT=jaredpalmer/kev-0.8b@v1.0`: checkpoint to load. Run setup after changing it to download the weights. Stop the existing server before changing the checkpoint or port.
- `JPARTY_KEV_START_TIMEOUT=180`: readiness polling limit in seconds (setup defaults to 1800 to allow downloads).

Kev logs go to `~/Library/Application Support/JParty/local-auto-host/kev-server.log`. Stop only terminates the server recorded by JParty, leaving other Kev installations alone. Uninstall also stops this process and offers to remove its checkout/environment with the existing local model directory; shared Hugging Face caches and `uv` remain installed.

For manual setup instead of the full-local scripts, install the [Kev server](https://github.com/jaredpalmer/kev) in a separate directory:

```bash
git clone https://github.com/jaredpalmer/kev.git
cd kev
uv sync --extra serve
uv run --extra serve python -m kev.serve --run jaredpalmer/kev-0.8b@v1.0 --port 8009
```

The first run downloads the base model and adapter. Apple Silicon serving uses MLX automatically. Leave **Kev URL** at `http://localhost:8009/v1` and **Kev served model** at `kev-latest`; this is the server's API alias for the checkpoint loaded by `--run`, not the Hugging Face download name.

Fast answer checks still run before Kev. Remaining answers go to a yes/no decision using the clue, expected answer, transcript, and leniency setting. The returned yes probability determines correctness at 0.5; confidence is the probability of the chosen verdict. Reasons are fixed feedback text because Kev does not generate an explanation.

If Kev fails, times out, or returns an invalid probability, JParty uses the configured Auto Host AI provider and a conservative exact-only fallback. The default Kev request timeout is three seconds; override it with `JPARTY_KEV_JUDGE_TIMEOUT` (seconds). The full-local scripts manage Kev alongside Ollama, STT, and TTS; manually installed Kev servers must be started and stopped separately.

Kev is experimental for Jeopardy judging. Check its decisions against labeled game answers before relying on it for scoring; this integration does not establish its accuracy on your clues.

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
