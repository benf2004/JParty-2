# Personal Voice Auto Host

JParty can request permission to access your macOS Personal Voice from its settings. Permission and voice playback are separate: the current macOS Say bridge exports speech to audio files and does not guarantee Personal Voice playback.

## Set Up Your Voice In macOS

1. Open **System Settings > Accessibility > Personal Voice**.
2. Create a Personal Voice and wait for macOS to finish processing it.
3. Turn on **Allow applications to use your Personal Voice**.
4. In JParty, open **Settings > Local Services > Host voice**, choose **macOS Say / Personal Voice**, then **Custom / Personal Voice**.
5. JParty requests access using Apple's native Personal Voice authorization dialog. Click **Allow**. You can also click **Allow Personal Voice…** to request or check access again.
6. The status shows whether access was granted and lists available Personal Voices. If denied, enable JParty under macOS **Accessibility > Personal Voice** and try again. General **Privacy & Security > Accessibility** permission is not required.

Use an updated packaged JParty app so the request belongs to JParty. When running from Python, macOS may associate permission with the development launcher. Source installs need the macOS dependencies in `requirements.txt`. The native API requires macOS 14 or later on supported hardware.

For standard system voices supported by the separate Say bridge, list names with:

```bash
say -v ?
```

Personal Voices visible to JParty's native API may not appear in this command. Granting access to JParty does not grant it to an independently launched speech service or Kokoro.

## Start The JParty Voice Bridge

The full local setup script starts it for you:

```bash
scripts/setup_full_local_auto_host_macos.sh
```

For game night after setup:

```bash
scripts/start_full_local_auto_host_macos.sh
```

You can also run only the macOS TTS bridge:

```bash
scripts/local_macos_tts_server.py
```

## JParty Settings

Use:

```text
Auto Host AI provider: local
Local TTS: macOS Say / Personal Voice
Local TTS URL: http://localhost:8880/v1
Local TTS model: macos-say
macOS Say voice: Custom / Personal Voice
Custom macOS voice name: an exact voice name supported by the Say bridge
```

If you leave the voice blank, macOS uses its current default speech voice.

## Wrong Server On Port 8880

If JParty logs `Unsupported model: macos-say`, port `8880` is still being served by an older TTS server. Restart the local services:

```bash
scripts/stop_full_local_auto_host_macos.sh
scripts/start_full_local_auto_host_macos.sh
```

The bridge health check should say `"engine": "macos-say"`:

```bash
curl http://127.0.0.1:8880/health
```
