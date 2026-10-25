# JParty iOS client

An iPhone/iPad client for the JParty game running on your computer. Requires iOS 17 or later and Xcode with an iOS SDK.

The app displays the existing buzzer UI in `WKWebView` and records voice with native `AVAudioRecorder`. Teams, signatures, clue selection, wagers, disputes, and manual text entry use the same desktop game. Recording does **not** depend on Safari's `getUserMedia`, HTTPS, or trusting a self-signed certificate.

## Run on your iPhone

1. Open `ios/JParty.xcodeproj` in Xcode and select the **JParty** scheme.
2. In the JParty target's **Signing & Capabilities**, select your Apple development team. Change `com.jparty.buzzer` to your own unique bundle identifier if signing requires it.
3. Select your connected iPhone as the destination and click Run. Follow Xcode's device pairing / Developer Mode prompts if shown.
4. Start the desktop game from this checkout (`.venv/bin/python run.py`), or rebuild the desktop app so it includes the updated buzzer assets.
5. Put the phone and computer on the same Wi-Fi. Tap **Scan QR Code**, allow **Camera**, and point it at the QR code on the game screen. The app connects automatically. You can also enter the **HTTP** address, such as `http://192.168.1.25:8080`, and tap **Join Game**. A bare IP address or `.local` hostname also works; port 8080 is the default.
6. Allow **Local Network** when prompted. Tap **Check Microphone Access** before joining, or allow **Microphone** on the first recording request.

`localhost` and `127.0.0.1` refer to the phone, not the computer. The app rejects these addresses on physical devices. They are allowed in the simulator, which can reach the Mac at `127.0.0.1:8080`.

The screen stays awake while a game is open. Keep the app in the foreground to buzz and speak. Leaving, reloading, backgrounding, or an audio interruption cancels an active recording. Microphone denial leaves the on-screen controls available; Game options → Microphone offers a link to Settings.

The embedded game browser has a compact inline header: Leave, the game title (or recording status), and a Game options menu for microphone access and reload. In team mode the web page shows a small team/score strip; Change team expands only when needed in the lobby. Team creators type and draw the team name separately from their individual name signature.

HTTPS remains available with a normally trusted certificate and defaults to port 8443. Certificate validation is not bypassed. For the desktop's self-signed local server, use HTTP on port 8080.

The QR scanner recognizes the desktop's default local `https://…:8443` address and connects through `http://…:8080`, avoiding local certificate setup. Public HTTPS URLs and nonstandard ports are preserved. If you configured custom desktop ports, enter the correct HTTP address manually. Invalid QR codes leave the scanner open. If Camera access is denied, the scanner offers **Open Settings** and **Enter Address Instead**. Scanning stops when you close the scanner or put the app in the background.

## How audio reaches the game

`recordAutoHostAudio` detects the `jpartyAudio` WebKit message handler. The app checks that the request comes from the selected server's main frame, asks iOS for microphone access, and records mono AAC in an M4A container. Requests are limited to 0.5–30 seconds. The temporary recording is deleted after being returned to the page.

The page uploads the recording to the existing `/api/player-audio` endpoint as `audio/mp4`, with the existing player token, purpose, and sequence ID. Desktop transcription already accepts this format and uses the configured speech provider. Ordinary browsers keep their existing recording path. Audio sent over the local HTTP connection is unencrypted.

The buzzer's scripts and font are served by the desktop, so the player UI also works on Wi-Fi without internet. Any configured cloud speech provider still needs internet from the computer.

The native permission and local transport configuration follows Apple's [microphone permission API](https://developer.apple.com/documentation/avfaudio/avaudioapplication/requestrecordpermission(completionhandler:)) and [local networking ATS setting](https://developer.apple.com/documentation/bundleresources/information-property-list/nsapptransportsecurity/nsallowslocalnetworking).

## Verify

Build for the simulator without signing:

```sh
xcodebuild -project ios/JParty.xcodeproj -scheme JParty \
  -sdk iphonesimulator -derivedDataPath ios/DerivedData \
  build CODE_SIGNING_ALLOWED=NO
```

Run the full native smoke test from the repository root:

```sh
ios/test-native-client.sh
node --test tests/test_buzzer.cjs tests/test_start_countdown.cjs tests/test_native_audio.cjs
```

The script needs Python with Tornado (it prefers the repository's `.venv`). It selects an available iPhone simulator, builds the app, starts an HTTP fixture on Mac loopback port 18080, and runs address validation plus UI tests. The microphone test resets permission **in that simulator**, accepts the native iOS prompt, records through the real buzzer page, then verifies the authenticated multipart upload contains an M4A file. QR tests inject decoded strings into the debug simulator build to verify automatic connection, invalid-code handling, and cancellation. The simulator has no camera; live camera scanning needs a physical-device check. These tests do not verify speech recognition accuracy or physical-device Wi-Fi access.

Override simulator / Python with `JPARTY_SIMULATOR_ID` / `JPARTY_PYTHON`. Logs and build outputs stay under ignored `ios/DerivedData/`. The ordinary **JParty** scheme runs the address unit tests with Cmd-U; the **JParty Native Smoke** scheme also needs the fixture started by the script.
