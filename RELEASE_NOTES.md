# JParty 2.5.1

Choose and download local AI models directly in JParty, with clearer settings and automatic readiness checks. No AI models are included in the desktop downloads.

## Downloads

- **macOS arm64**: Apple Silicon (M1 or newer), macOS 11 or newer. Extract the ZIP and drag `JParty.app` to Applications.
- **macOS x64**: Intel Mac, macOS 11 or newer. Extract the ZIP and drag `JParty.app` to Applications.
- **Windows x64**: Windows 10/11. Extract the whole ZIP and launch `JParty/JParty.exe`; keep `_internal` alongside it.
- **Linux x64**: Ubuntu 22.04 or newer, or a compatible desktop distribution. Extract the whole tar.gz and run `JParty/JParty`; keep `_internal` alongside it. Audio and Qt require your distribution's normal ALSA and graphics libraries.

Mac downloads must pass Developer ID signing, Apple notarization, and Gatekeeper verification before this release is published. Windows executables are not Authenticode signed.

## What changed

- **Settings → Local Services → Local AI model** lists installed Ollama models and their sizes. Choose a model and save; no restart is required. Missing models and an offline Ollama installation are explained without changing your selection.
- **Install Ollama** opens the official installer instructions for your platform. **Open/Start Ollama** starts an existing installation. Ollama runs models; the dropdown chooses the model JParty uses.
- **Download a model…** offers Qwen 2.5 7B (about 4.7 GB), Qwen 2.5 3B (about 1.9 GB), and an advanced option for other Ollama text-model names. Downloads show progress, can be cancelled and retried, and continue while Settings is closed. Save after a download to apply your choice.
- All five settings tabs use matching cards, headings, aligned fields, accessible switches, and visible dropdown arrows. Team mode follows the same layout.
- **Settings → Images → Find replacement images with Pexels** requires a running local text model and a Pexels API key. It uses local AI to write stock-photo search terms for missing clue images. Image search pauses during local AI outages and resumes automatically; an OpenAI key no longer enables this feature or supplies a cloud fallback.
- Native macOS Personal Voice permission requests and voice discovery are available in Host voice settings. This requires macOS 14 or later on supported hardware. Permission and audio-file playback through the separate Say bridge remain separate; see `PERSONAL_VOICE_AUTOHOST.md`.
- Keeps in-app updates, manual and optional Auto Host modes, phone buzzers, team play, themes, smaller audio assets, and video playback.

## Updating

JParty 2.5.0 users can use **Settings → Game → Updates**, then **Download update** and **Restart to update** from the lobby. Earlier versions need a manual installation. Settings, game history, API keys, and downloaded local models remain in their existing locations.

Local text AI now uses Ollama on this computer at `http://localhost:11434/v1`. A previously configured custom text-server address stays saved until you save Settings, which replaces it with the Ollama address. Speech recognition, voice, and Kev retain their separate endpoint settings.

## Optional local AI Auto Host

Manual hosting works immediately without downloading models. Cloud Auto Host requires your own OpenAI API key.

Ollama installation guidance and in-app model downloads work on macOS, Windows, and Linux. Downloading a text model does not install speech recognition, host voices, or Kev. Internet access and several GB of free space may be required for downloads.

On **macOS**, choose your local model and voice, save, and use **Local Services → Set up** for the full local Auto Host stack. Homebrew must already be installed for this full-stack setup from the GUI. Use **Start services** and check component status before starting an Auto Host game. Setup/start/stop and model downloads cannot run at the same time.

On **Windows and Linux**, manage speech recognition and speech synthesis services separately. Full-stack setup/start/stop helpers remain macOS-only. See `FULL_LOCAL_AUTOHOST.md` and `AUTOHOST.md` for details.

Executable bundles include Python and Qt. They do not include model weights, API keys, your saved settings, or your game history. The iOS Xcode project is available in the repository and source archives; no installable iOS app is attached.
