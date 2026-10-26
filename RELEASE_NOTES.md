# JParty 2.4.3

One desktop app, with optional local AI Auto Host. No AI models are included in these downloads.

## Downloads

- **macOS arm64**: Apple Silicon (M1 or newer), macOS 11 or newer. Extract the ZIP and drag `JParty.app` to Applications.
- **macOS x64**: Intel Macs, macOS 12 or newer. Extract the ZIP and drag `JParty.app` to Applications.
- **Windows x64**: Windows 10/11. Extract the whole ZIP and launch `JParty/JParty.exe`; keep `_internal` alongside it.
- **Linux x64**: Ubuntu 22.04 or newer, or a compatible desktop distribution. Extract the whole tar.gz and run `JParty/JParty`; keep `_internal` alongside it. Audio and Qt require your distribution's normal ALSA and graphics libraries.

The macOS apps are signed with an Apple Developer ID, notarized by Apple, and include a stapled notarization ticket. Windows executables are not Authenticode signed.

## What changed

- Players create or join teams on their phones. Team creators type and draw their team name separately from their individual name and signature; hosts no longer need to set up teams.
- Saving a team-mode change in Settings restarts JParty and remembers the selected mode. Players join again after the restart.
- Team podiums show the team's shared score and drawn name, with the answering person's own name and signature underneath.
- The phone team/score strip is more compact, and lobby team changes expand only when needed. The iOS client's embedded browser also has a compact toolbar with a Game options menu.
- Team creation validates names and drawings, handles simultaneous duplicate names, cancels pending start countdowns when rosters change, and respects the eight-team and 32-player limits.
- Registration now correctly handles team names containing “BUZZ”.
- Mac release builds retry notarization ticket attachment and validation, with detailed ticket diagnostics if verification fails.

The updated iOS Xcode project is included in the repository and source archives. This release's executable downloads are the four desktop builds listed above; there is no installable iOS app attached.

## Optional local AI Auto Host

Manual hosting works immediately without downloading models. Cloud Auto Host requires your own OpenAI API key.

On **macOS**, open Settings → Auto Host, select the local provider and voice, save, then use Settings → Local Services → Set up. Setup downloads the selected models and installs the local tools. Homebrew must already be installed for setup from the GUI. Model downloads may total several GB. Use Start services and Check status before starting an Auto Host game. See the included `FULL_LOCAL_AUTOHOST.md` for details.

On **Windows and Linux**, the app can connect to externally managed OpenAI-compatible local LLM, speech recognition, and speech synthesis services. The automatic setup/start/stop helpers are currently macOS-only. Configure service URLs under Local Services; select a compatible voice/model for your platform. See `AUTOHOST.md` for the endpoint interfaces.

Executable bundles include Python and Qt. They do not include model weights, API keys, your saved settings, or your game history.
