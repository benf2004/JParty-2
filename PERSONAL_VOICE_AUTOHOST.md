# Personal Voice Auto Host

JParty can use your macOS Personal Voice through the built-in Mac speech system. No extra voice add-on is needed.

## Set Up Your Voice In macOS

1. Open **System Settings > Accessibility > Personal Voice**.
2. Create a Personal Voice and wait for macOS to finish processing it.
3. Turn on **Allow applications to use your Personal Voice**.
4. In Terminal, run:

```bash
say -v ?
```

Find the exact name of your Personal Voice in that list.

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
Custom macOS voice name: the exact Personal Voice name from say -v ?
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
