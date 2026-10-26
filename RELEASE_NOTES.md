# JParty 2.5.0

One desktop app, with optional local AI Auto Host. No AI models are included in these downloads.

## Downloads

- **macOS arm64**: Apple Silicon (M1 or newer), macOS 11 or newer. Extract the ZIP and drag `JParty.app` to Applications.
- **macOS x64**: Intel Macs, macOS 12 or newer. Extract the ZIP and drag `JParty.app` to Applications.
- **Windows x64**: Windows 10/11. Extract the whole ZIP and launch `JParty/JParty.exe`; keep `_internal` alongside it.
- **Linux x64**: Ubuntu 22.04 or newer, or a compatible desktop distribution. Extract the whole tar.gz and run `JParty/JParty`; keep `_internal` alongside it. Audio and Qt require your distribution's normal ALSA and graphics libraries.

The macOS apps are signed with an Apple Developer ID, notarized by Apple, and include a stapled notarization ticket. Windows executables are not Authenticode signed.

## What changed

- Automatic update checks with a lobby notice and Settings → Game → Updates controls. JParty always asks before downloading; choose **Download update**, then **Restart to update** from the lobby. Games keep running until you choose to restart.
- Downloads are verified against GitHub's SHA-256 digest. Mac updates also require the same Developer ID signature and Gatekeeper acceptance. The previous app copy is retained until the new version opens successfully; failed replacement restores it.
- Downloaded updates remain ready if you close and reopen JParty. Settings, game history, API keys, and local AI models stay in their existing locations.
- Auto Host now has a clear On/Off toggle, with **Off** as the default. Existing saved preferences are respected.
- Keeps the smaller audio assets, working phone signatures, all themes, team features, video playback, and optional local AI Auto Host.

**Install this version manually once to enable future in-app updates.** Updates use the full release archive and require space for the new and previous app copies. Keep the app in a writable folder; Mac users should move it to Applications before updating.
The updated iOS Xcode project is included in the repository and source archives. This release's executable downloads are the four desktop builds listed above; there is no installable iOS app attached.

## Optional local AI Auto Host

Manual hosting works immediately without downloading models. Cloud Auto Host requires your own OpenAI API key.

On **macOS**, open Settings → Auto Host, select the local provider and voice, save, then use Settings → Local Services → Set up. Setup downloads the selected models and installs the local tools. Homebrew must already be installed for setup from the GUI. Model downloads may total several GB. Use Start services and Check status before starting an Auto Host game. See the included `FULL_LOCAL_AUTOHOST.md` for details.

On **Windows and Linux**, the app can connect to externally managed OpenAI-compatible local LLM, speech recognition, and speech synthesis services. The automatic setup/start/stop helpers are currently macOS-only. Configure service URLs under Local Services; select a compatible voice/model for your platform. See `AUTOHOST.md` for the endpoint interfaces.

Executable bundles include Python and Qt. They do not include model weights, API keys, your saved settings, or your game history.
