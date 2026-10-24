<img src="resources/icon.png" align="right" height="100"/>

# JParty!
![](https://img.shields.io/github/v/release/stuartthomas25/JParty)
![](https://img.shields.io/github/downloads/stuartthomas25/JParty/total)
![](https://img.shields.io/github/stars/stuartthomas25/JParty?style=social)

_The Jeopardy! Party Game_

Homepage: https://www.stuartthomas.us/jparty/

Ever wanted to play the game show Jeopardy? This Python-based application aims to provide a full _Jeopardy!_ simulator complete with real questions from actual games. This game is perfect for parties and supports 3-8 players plus a host. Typically, _Jeopardy!_ has three contestants which is recommended for the best experience; JParty supports up to 8 players for larger groups (warning: may cause many complaints about buzzer races). For ideal usage, plug a laptop into a TV, setting the laptop as the main monitor. Note that connecting wirelessly using AirPlay works but may cause latency in the buzzer. Instruct contestants to join the same Wifi network as the computer and scan the QR code on the screen. The person with the laptop is the host and runs the game by reading the questions and running the buzzers.

## Download
Download the desktop app for your platform from [JParty releases](https://github.com/benf2004/JParty-2/releases). One app includes manual hosting and optional Auto Host; local AI models download separately during setup. See [release notes](RELEASE_NOTES.md) for platform support.

## iPhone / iPad client

The [iOS client](ios/README.md) uses native microphone recording and connects directly to the desktop game over Wi-Fi HTTP, avoiding browser microphone restrictions and local HTTPS certificate setup. Open `ios/JParty.xcodeproj` in Xcode to install it on your device. Requires iOS 17 or later.

## Recent Updates:
- Added ability to use up to 4 physical buzzers (With the possibility to add more)! (Currently Only Confirmed Working On Windows Computers)
    - With some new updates by Ross and Garrett JParty! now supports physical buzzers. More information on making these can be found farther down in the README file. [See Building the Physical Buzzers README](physicalbuzzers/README.md)
- Added ability to change theme within the game. Current theme options are default and christmas.

## Screenshots:

Welcome screen:

<img src="screenshots/welcome_screen.png" height="300"/>

The main game board:

<img src="screenshots/main_board.png" height="300"/>

The host sees the answer on the laptop screen and can adjudicate with the arrow keys:

<img src="screenshots/alex_view.png" height="300"/>

## Features:
- WebSocket buzzer for use on mobile devices 
- Up to 8 individual players, or 32 players across 2–8 teams
- Complete access to all games on J-Archive
- Load custom games via a <a href="https://docs.google.com/spreadsheets/d/1_vBBsWn-EVc7npamLnOKHs34Mc2iAmd9hOGSzxHQX0Y/edit?usp=sharing">simple Google Sheets template</a>
- Scrape games from https://jeopardylabs.com using this <a href="https://chrome.google.com/webstore/detail/jeopardy-labs-to-csv/biijijhfghhckhlkjbonjedmgnkmenlk?hl=en&authuser=0">Google Chrome extension</a>
- Final Jeopardy, Daily Doubles, Double Jeopardy

## Team mode

Open **Settings → Team mode** on the host's welcome screen. Turn on team play, name 2–8 teams, and choose **Save changes**. Players join on their own phones and choose a team; they can switch teams until the game starts. At least two teams must have members.

Each team shares a score and gets one attempt per clue. Anyone can buzz. The first member to join acts for the team initially; a correct regular-clue answer makes that member the team's representative. The representative picks clues, handles Daily Doubles, and submits the team's single Final Jeopardy wager and answer. Auto Host review and Play Again votes still count per person.

Use **Manage players** in the Team mode tab, or the **…** button on a team podium, to manage members and recover representative controls if someone disconnects. Finish an active answer or Final Jeopardy review before removing its participants. Returning to the lobby clears game state while keeping the mode and team names.

## Requirements:
### For running the app (binary)
- macOS, Windows or Linux
- Two monitors (recommended)
- A device with web access for each player

### For compiling from source code
- Python [>=3.9]
- PyQt6
- requests
- simpleaudio
- tornado
- BeautifulSoup4
- qrcode
- pyinstaller [>=5.0]

To debug, run 

`
pip install -r requirements.txt;
cd jparty;
python ../run.py
`

### Build desktop executables

Use Python 3.11 on the platform you are building for:

```bash
python -m pip install -r requirements.txt
python scripts/build_release.py
```

The build script bundles Python, Qt, themes, phone assets, and optional local AI setup helpers. It runs the installed executable from a clean working directory before writing the platform archive, SHA-256 checksum, and smoke-test report to `dist/releases/`. macOS produces an app ZIP, Windows a ZIP containing `JParty.exe` and its `_internal` folder, and Linux a tar.gz that preserves executable permissions. Model weights and personal settings are excluded.

GitHub Actions builds Apple Silicon and Intel macOS, Windows x64, and Linux x64. After updating `jparty/version.py` and `RELEASE_NOTES.md`, pushing a `codex/release-*` branch runs tests, builds and verifies every platform, and publishes a release at that exact commit. Pushing a `v*` tag also runs the release workflow; its version must match the source. Manual workflow runs build downloadable Actions artifacts without publishing unless run on a release branch.

Automatic local AI setup/start/stop is currently macOS-only. Windows and Linux can use cloud hosting or connect to separately managed compatible local AI services.

### Mac release signing

Mac builds in GitHub Actions require these repository Actions secrets:

| Secret | Value |
| --- | --- |
| `BUILD_CERTIFICATE_BASE64` | Base64-encoded `.p12` containing the private key paired with the public Developer ID release certificate in `resources/signing/` |
| `P12_PASSWORD` | Password used when exporting the `.p12` |
| `KEYCHAIN_PASSWORD` | Separate random password for the temporary build keychain |
| `APPLE_ID` | Apple account email used for notarization |
| `APPLE_TEAM_ID` | Apple Developer membership Team ID |
| `APPLE_APP_SPECIFIC_PASSWORD` | App-specific password generated at account.apple.com; do not use your normal Apple password |

The workflow imports the identity into a temporary keychain, validates Apple credentials, signs the bundled binaries with hardened runtime, submits the app using `notarytool`, staples the accepted ticket, and verifies Gatekeeper acceptance before creating the final ZIP and checksum. It removes the temporary keychain even if the build fails. Mac releases fail if any credential or verification is missing; local builds without signing settings remain ad-hoc signed for development.

The public certificate and Apple intermediate certificates live in `resources/signing/`. The workflow pairs the public release certificate with the private key from the `.p12`, so the encrypted secret does not need to be replaced when a certificate is issued for the same key. Replace the leaf certificate before its February 1, 2027 expiration. For forks without public certificates, the `.p12` must contain exactly one valid Developer ID Application identity.

Keep the original signing identity in macOS Keychain, with a password-protected `.p12` backup in an encrypted vault. Certificate passwords and private keys must never be committed. GitHub secrets hold the CI copy; Base64 itself is not encryption. See [GitHub's certificate setup](https://docs.github.com/en/actions/how-tos/deploy/deploy-to-third-party-platforms/sign-xcode-applications) and [Apple's notarization workflow](https://developer.apple.com/documentation/security/customizing-the-notarization-workflow).

## FAQ

### How does it work? (technical details)
JParty minimally scrapes the J-Archive (https://j-archive.com) to download a previously-played game and then simulates that on the screen. The game then uses PyQt6 to produce a GUI that simulates the motions of a full _Jeopardy!_ game. A `tornado` web server uses WebSockets to connect to the contestants' smartphones. If that's all gibberish to you, don't worry! You can still play without any technical knowledge.

### Can I create my own custom game?
Yes! JParty supports playing your own custom game via <a target=_blank href="https://docs.google.com/spreadsheets/d/1_vBBsWn-EVc7npamLnOKHs34Mc2iAmd9hOGSzxHQX0Y/edit?usp=sharing">this simple Google Sheets template</a>. First, make a copy of the template and change the sharing permissions to "Anyone With the Link Can View". Then, copy the Google Sheet file ID and paste it into the "Game ID" box. There are more detailed instructions on the template page. Limitations: there is no way to add pictures (yet!) and you are limited to the traditional 6 categories x 5 dollar values board. 

If you don't want to write your own questions but want to play a topical _Jeopardy!_ game, use this handy <a target=_blank href="https://chrome.google.com/webstore/detail/jeopardy-labs-to-csv/biijijhfghhckhlkjbonjedmgnkmenlk?hl=en&authuser=0">Google Chrome extension to scrape Jeopardy Labs questions</a> (<a href=https://github.com/benf2004/JeopardyLabsToCSV>source code</a>). There are millions of games available on https://jeopardylabs.com that are free to play on a variety of topics. While Jeopardy Labs is a great repository for many topical games & worked great 20 years ago, it lacks in features such as daily doubles, final jeopardy, music/sound effects, and buzzers. 

To use the extension:
1. Make a copy of the <a target=_blank href="https://docs.google.com/spreadsheets/d/1_vBBsWn-EVc7npamLnOKHs34Mc2iAmd9hOGSzxHQX0Y/edit?usp=sharing">Jparty Google Sheets custom game template</a>
2. Find a game on https://jeopardylabs.com. 
3. Click the extension icon.
4. The questions will download as a csv (spreadsheet) in the style of the template. 
5. Copy the questions into your Google Sheet template
6. Paste the Google Sheet file ID into the "Game ID" box in JParty.

### The QR code doesn't work!
First, make sure you are on the same wireless network as the computer. If this still doesn't work, it may be an issue with allowing local devices on the network. In this case, you can try another network or try tethering both the phones and the computer to another phone.
