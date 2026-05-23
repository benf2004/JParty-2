# Voice Cloning Auto Host Addon

This optional addon lets Auto Host use a local cloned voice instead of Kokoro.

The addon uses KokoClone through a tiny local adapter that exposes JParty's OpenAI-style `/v1/audio/speech` endpoint. It runs from a local Python 3.12 environment.

The addon uses a local OpenAI-compatible TTS server, so JParty's flow stays the same:

```text
JParty host text
  -> local /v1/audio/speech endpoint
  -> cloned-voice WAV
  -> JParty plays and caches the audio
```

## Voice Consent

Use your own voice or a voice you have clear permission to clone. Do not clone someone else's voice without consent.

## Prepare A Voice Sample

Record a clean 20-60 second clip of your own voice. Tips:

- speak naturally, like you would host the game
- use a quiet room
- avoid background music/noise
- export as WAV, M4A, or MP3

## Install The Addon

After the full local Auto Host setup has installed ffmpeg, run:

```bash
scripts/voice_clone.sh setup-kokoclone
```

Or pass the sample path directly:

```bash
JPARTY_VOICE_SAMPLE=/path/to/my-voice.m4a scripts/voice_clone.sh setup-kokoclone
```

The script converts the sample to the right WAV format, installs KokoClone in its own environment, starts the local voice-clone adapter, and prints JParty settings.

## JParty Settings

Use these settings after setup:

```text
Local TTS: KokoClone cloned voice
Local TTS URL: http://localhost:8892/v1
Local TTS model: kokoclone
Local TTS voice: my_voice
```

In JParty Settings, choose `KokoClone cloned voice` from the `Local TTS` dropdown.

If you choose a custom voice name:

```bash
JPARTY_KOKOCLONE_VOICE_NAME=ben JPARTY_VOICE_SAMPLE=/path/to/ben.wav scripts/voice_clone.sh setup-kokoclone
```

then set:

```text
Local TTS voice: ben
```

## Game Night

If voice cloning is configured, the main game-night start script will start it:

```bash
scripts/start_full_local_auto_host_macos.sh
```

To stop everything:

```bash
scripts/stop_full_local_auto_host_macos.sh
```

You can also start or stop only the voice-clone addon:

```bash
scripts/voice_clone.sh start-kokoclone
scripts/voice_clone.sh stop-kokoclone
```

## Fallback

Kokoro remains the recommended fallback. If voice cloning is too slow or glitchy, switch JParty back to:

```text
Local TTS URL: http://localhost:8880/v1
Local TTS model: kokoro
Local TTS voice: af_heart
```
