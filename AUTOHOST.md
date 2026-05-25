# JParty Auto Host

## Summary

Auto Host is an optional mode that lets JParty run closer to a self-hosted game. The computer still owns the main game state, board display, scoring, and buzzer timing, but the host voice, clue selection, answer recording, and answer judging are assisted by AI.

Players use their phones for four main actions:

- buzz in
- choose the next clue when they have control
- record spoken answers
- see brief Auto Host judgement feedback

The Auto Host voice plays through the computer speakers. It welcomes players, reads clues, acknowledges buzzes, gives short correct/incorrect feedback, and reveals the answer when time runs out.

Auto Host is off by default and can be enabled in Settings.

## High-Level Game Flow

1. Players join from the QR code.
2. Each player types their name and signs/scribbles on the phone.
3. If Auto Host is enabled, the QR/player URL prefers local HTTPS so phone microphone APIs can work.
4. When the game starts, Auto Host reads a short intro:
   - welcomes contestants
   - briefly reads the board categories
   - asks the first joined player to choose the first clue
5. The player in control chooses a clue:
   - by speaking the clue selection
   - or by tapping the 6x5 clue grid on the phone
6. Once a clue is selected, phones return to the buzzer screen before the clue is read.
7. Auto Host reads the clue aloud.
8. JParty opens responses and players can buzz.
9. The first valid buzz gets control of the answer attempt.
10. That player's buzzer page shows `Wait to talk...`.
11. Auto Host says the player name, such as `Ben?`
12. The in-place answer panel starts answer recording on that player's buzzer page.
13. The recorded answer is uploaded to the computer.
14. AI transcribes and judges the answer.
15. If the answer is judged correct:
    - Auto Host gives brief positive feedback
    - JParty awards points
    - that player gains control
    - Auto Host prompts them to choose the next clue
16. If the answer is judged incorrect:
    - Auto Host says a short incorrect phrase
    - JParty subtracts points according to settings
    - other players may buzz in
17. If time runs out:
    - Auto Host announces the correct response
    - JParty returns to the board
    - the player in control is prompted to pick the next clue

Manual host controls remain available. The host can still adjust scores from the computer.

## Settings

Auto Host settings live in the regular JParty Settings dialog.

Current settings include:

- **Auto Host**: enables or disables the feature.
- **Auto Host AI provider**: currently `openai` or `local`.
- **Auto Host leniency**: controls answer-judging strictness.
- **Auto Host voice**: selects the OpenAI TTS voice.
- **OpenAI API Key**: optional local-only key field.

The OpenAI key lookup order is:

1. `OPENAI_API_KEY` environment variable
2. `auto_host.openai_api_key` saved in local JParty config

The saved config is local to the user's machine, such as:

```text
~/Library/Application Support/JParty/config.json
```

The key is not sent to player phones.

## Local AI Setup For Beginners

Local Auto Host lets JParty use AI services running on your own computer instead of paid cloud APIs.

The pieces are:

- **Local model runner**: an app such as Ollama or LM Studio that runs a local LLM.
- **LLM**: the text brain that parses clue choices and judges ambiguous answers.
- **STT**: speech-to-text; turns player microphone recordings into text.
- **TTS**: text-to-speech; turns host lines into spoken audio.

JParty does not install or start these services during a game. In local mode it connects to services you already started.

### Beginner LLM Path: Ollama

For a 16 GB Apple Silicon Mac, start with:

```text
qwen2.5:7b
```

If that feels slow, use:

```text
llama3.2:3b
```

If you want to try a heavier 7B model, use:

```text
mistral:7b
```

The helper script installs/checks Homebrew, Ollama, and ffmpeg, starts Ollama if needed, pulls the default model, and prints the settings to copy into JParty:

```bash
scripts/setup_local_auto_host_macos.sh
```

To use a smaller model:

```bash
JPARTY_LOCAL_LLM_MODEL=llama3.2:3b scripts/setup_local_auto_host_macos.sh
```

Default JParty local LLM settings:

```text
Auto Host AI provider: local
Local LLM URL: http://localhost:11434/v1
Local LLM model: qwen2.5:7b
```

### Local Speech-To-Text

Use a Whisper-compatible local server that exposes an OpenAI-style endpoint:

```text
POST /v1/audio/transcriptions
```

JParty defaults:

```text
Local STT URL: http://localhost:8082/v1
Local STT model: whisper
```

Good local STT families to look for are `whisper.cpp` and `faster-whisper`. If STT is not running or fails, JParty asks the player to retry or use the on-screen fallback.

For a fuller beginner path that installs and starts local Whisper speech-to-text, then asks whether you want macOS Say or Kokoro for TTS, use:

```bash
scripts/setup_full_local_auto_host_macos.sh
```

After setup, use `scripts/start_full_local_auto_host_macos.sh` before playing and `scripts/stop_full_local_auto_host_macos.sh` when you are done.

See `FULL_LOCAL_AUTOHOST.md` for the step-by-step version and `PERSONAL_VOICE_AUTOHOST.md` for Personal Voice notes.

### Local Text-To-Speech

Use either the built-in macOS speech bridge or Kokoro. Both expose an OpenAI-style endpoint:

```text
POST /v1/audio/speech
```

JParty defaults:

```text
Local TTS URL: http://localhost:8880/v1
Local TTS model: macos-say
macOS Say voice: Custom / Personal Voice, then your exact Personal Voice name
```

If TTS is not running or fails, the game continues without spoken host audio.

### LM Studio Alternative

LM Studio is a good option if you prefer a graphical app for downloading and swapping models. Start its local OpenAI-compatible server, then set:

```text
Local LLM URL: http://localhost:1234/v1
Local LLM model: the loaded model name shown in LM Studio
```

## Local HTTPS And Microphone Access

Phone microphone recording depends on browser security rules. Most phone browsers only expose `navigator.mediaDevices.getUserMedia(...)` in a secure browser context.

JParty serves the buzzer page two ways:

- HTTP: `http://<computer-ip>:8080`
- HTTPS: `https://<computer-ip>:8443`

Auto Host prefers the HTTPS URL in the QR code because phone microphone access is much more likely to work there.

The HTTPS server uses a local self-signed certificate stored under:

```text
~/Library/Application Support/JParty/
```

Players may need to accept or trust the local certificate in their browser. If the browser still blocks microphone access, the phone UI keeps tap/text fallback controls available.

## Phone Audio Recording Flow

Phone recording happens in `jparty/buzzer/static/buzzer.js`.

The important browser APIs are:

- `navigator.mediaDevices.getUserMedia({ audio: true })`
- `MediaRecorder`
- `FormData`
- `fetch("/api/player-audio", ...)`

When the phone records audio:

1. JParty sends a WebSocket prompt such as `PROMPT_SELECT_CLUE` or `PROMPT_RECORD_ANSWER_AUTO`.
2. The phone changes to the appropriate screen.
3. For Auto Host prompts, recording can start automatically.
4. The phone shows a visible `Speak now` status.
5. `MediaRecorder` records a short clip.
6. The phone sends the clip to:

```text
POST /api/player-audio
```

The upload includes:

- `token`: the player's token cookie
- `purpose`: `clue_selection`, `answer`, or `daily_double_wager`
- `sequence_id`: client timestamp/id
- `audio`: recorded audio blob

The preferred recording MIME type is:

```text
audio/webm;codecs=opus
```

The phone falls back to other browser-supported audio types if needed.

## Server Audio Upload Flow

Audio uploads are handled in `jparty/controller.py` by `PlayerAudioHandler`.

The handler:

1. Reads the player token.
2. Validates that the token belongs to a connected player.
3. Reads upload purpose and audio bytes.
4. Passes the audio to:

```python
BuzzerController.player_audio(...)
```

That forwards to:

```python
AutoHostController.receive_audio(...)
```

Audio processing then runs in a background thread so the Tornado request and PyQt UI do not block.

## Transcription

Transcription is handled by `AutoHostAI.transcribe(...)` in `jparty/auto_host.py`.

For OpenAI mode:

1. The uploaded bytes are written to a temporary file.
2. The file is sent to:

```text
POST https://api.openai.com/v1/audio/transcriptions
```

3. The default model is:

```text
gpt-4o-mini-transcribe
```

This can be overridden with:

```text
JPARTY_TRANSCRIBE_MODEL
```

If no OpenAI API key is available, transcription returns an empty string and the phone uses fallback UI.

## Clue Selection Processing

Spoken clue selection uses this path:

1. Phone records the clue request.
2. Audio uploads with purpose:

```text
clue_selection
```

3. Auto Host transcribes the audio.
4. The transcript is parsed into a clue choice.

OpenAI parsing returns structured data:

- `category_index`
- `value`
- `needs_gui`

If parsing fails, Auto Host asks the player to tap the clue on the 6x5 phone board.

When a valid clue is selected:

1. All phones are sent back to the buzzer screen.
2. The computer loads the selected clue.
3. Auto Host reads the clue.
4. Responses open after clue audio finishes.

## Answer Processing

Spoken answer processing uses this path:

1. A player buzzes.
2. JParty locks out other buzzes.
3. The player's buzzer page shows a brief wait prompt.
4. Auto Host says the player's typed name.
5. The answer panel appears on that buzzer page.
6. Recording starts automatically.
7. Audio uploads with purpose:

```text
answer
```

8. Auto Host transcribes the audio.
9. Empty transcripts do not open judgement. The player is prompted to try again.
10. Non-empty transcripts are checked locally for an exact or near-exact answer match before slower AI judging is used.
11. Answers that still need judgement are checked against:
   - clue text
   - expected answer
   - leniency setting

The judgement result includes:

- `is_correct`
- `confidence`
- `reason`
- `transcript`

Correct answers call the existing JParty correct-answer path. Incorrect answers call the existing incorrect-answer path and reopen buzzing when appropriate.

## Judgement Feedback Flow

Auto Host judgement is designed to keep the game moving. Once the AI judges a non-empty answer, JParty applies the result immediately.

The answering player's phone may briefly show:

- the judged result
- the transcribed answer

This is informational only. It should not block the next clue or reveal the expected correct answer before the clue has resolved.

The computer host can still manually adjust scores afterward.

## Daily Double Flow

For Daily Doubles:

1. The controlling player is prompted for a wager.
2. Auto Host reads a brief wager prompt.
3. The player can speak or type the wager.
4. Spoken wager audio uploads with purpose:

```text
daily_double_wager
```

5. Auto Host parses the amount.
6. The value is clamped to the legal maximum.
7. The clue is shown and the controlling player answers.

## Text-To-Speech Flow

TTS is handled by `AutoHostAI.speech_file(...)`.

For OpenAI mode, JParty calls:

```text
POST https://api.openai.com/v1/audio/speech
```

Defaults:

- model: `gpt-4o-mini-tts`
- voice: selected in Settings, default `coral`
- format: `wav`
- speed: `1.3`

The model can be overridden with:

```text
JPARTY_TTS_MODEL
```

Generated WAV files are cached locally under:

```text
~/Library/Application Support/JParty/auto_host_audio_cache/
```

The cache key includes:

- model
- voice
- speed
- purpose
- text

This prevents repeated API calls for the same generated host line.

## TTS Playback

TTS audio plays on the computer using `simpleaudio`.

Playback is intentionally best-effort:

- if TTS generation fails, the game continues
- if playback fails, the game continues
- if cached audio exists, it is reused

For clue reading:

1. JParty loads the clue.
2. Auto Host plays cached/generated clue audio.
3. After playback finishes, JParty opens responses.

## Important WebSocket Messages

Phone prompts are mostly driven by WebSocket messages.

Common messages:

- `PROMPT_SELECT_CLUE`: show the clue picker and start clue-selection recording.
- `PROMPT_BUZZ`: return phone to buzzer screen.
- `PROMPT_WAIT_ANSWER`: show the buzzer-page wait prompt before the host acknowledgement finishes.
- `PROMPT_RECORD_ANSWER`: show the buzzer-page answer panel.
- `PROMPT_RECORD_ANSWER_AUTO`: show the buzzer-page answer panel and auto-record.
- `PROMPT_DD_WAGER`: show Daily Double wager screen.
- `JUDGEMENT_RESULT`: briefly show the applied AI judgement to the answering player.
- `AUTO_HOST_FALLBACK`: show fallback message.

## Fallback Behavior

Auto Host is designed to degrade gracefully.

Fallbacks include:

- tap clue grid if speech clue selection fails
- type answer if recording fails
- retry answer recording if transcription is empty
- manual score adjustment on the computer
- regular keyboard adjudication if needed

## Known Practical Limits

Phone microphone access can still fail if:

- the phone does not trust the local HTTPS certificate
- the browser blocks self-signed local certificates
- the player uses the HTTP URL instead of HTTPS
- mic permission is denied

When that happens, Auto Host should still remain playable through tap/text fallback controls.
