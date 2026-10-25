import AVFoundation
import SwiftUI

@main
struct JPartyApp: App {
    var body: some Scene { WindowGroup { ContentView() } }
}

struct ContentView: View {
    @AppStorage("jparty.serverAddress") private var serverText = ""
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var audio = NativeAudioRecorder()
    @StateObject private var browser = GameBrowser()
    @State private var server: ServerAddress?
    @State private var addressError: String?
    @State private var showPermissionHelp = false
    @State private var showScanner = false
    @FocusState private var addressFocused: Bool

    private let gold = Color(red: 1, green: 0.82, blue: 0.28)

    var body: some View {
        NavigationStack {
            ZStack {
                LinearGradient(colors: [Color(red: 0.08, green: 0.08, blue: 0.36), Color(red: 0.02, green: 0.02, blue: 0.12)],
                               startPoint: .topLeading, endPoint: .bottomTrailing).ignoresSafeArea()
                if let server {
                    game(server)
                } else {
                    connectionForm
                }
            }
            .preferredColorScheme(.dark)
            .navigationBarTitleDisplayMode(.inline)
            .tint(gold)
            .sheet(isPresented: $showScanner) {
                QRScannerView { address in
                    showScanner = false
                    join(address)
                }
            }
            .toolbar {
                if server != nil {
                    ToolbarItem(placement: .topBarLeading) {
                        Button("Leave", systemImage: "chevron.left") { disconnect() }
                            .labelStyle(.iconOnly)
                    }
                    ToolbarItem(placement: .principal) {
                        HStack(spacing: 6) {
                            Image(systemName: audio.isRecording ? "mic.fill" : "bolt.fill")
                            Text(audio.isRecording ? "Recording" : "JParty!")
                        }
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(audio.isRecording ? .red : gold)
                        .fixedSize()
                    }
                    ToolbarItem(placement: .topBarTrailing) {
                        Menu("Game options", systemImage: "ellipsis") {
                            Button("Microphone", systemImage: "mic") { checkMicrophone() }
                            Button("Reload", systemImage: "arrow.clockwise") { audio.cancel(); browser.reload() }
                        }
                        .labelStyle(.iconOnly)
                    }
                }
            }
            .alert("Microphone access is off", isPresented: $showPermissionHelp) {
                Button("Open Settings") {
                    if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
                }
                Button("Use on-screen controls", role: .cancel) {}
            } message: {
                Text("Allow Microphone in JParty’s Settings to speak answers, clue selections, and wagers.")
            }
            .onChange(of: scenePhase) { _, phase in
                UIApplication.shared.isIdleTimerDisabled = server != nil && phase == .active
                // A system permission sheet briefly makes the app inactive.
                if phase == .background { audio.cancel() }
            }
            .onReceive(NotificationCenter.default.publisher(for: AVAudioSession.interruptionNotification)) { _ in
                audio.cancel()
            }
        }
    }

    private var connectionForm: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 26) {
                VStack(alignment: .leading, spacing: 10) {
                    Image(systemName: "bolt.circle.fill").font(.system(size: 60)).foregroundStyle(gold)
                    Text("JParty!").font(.system(size: 48, weight: .heavy, design: .rounded))
                    Text("Your buzzer. Your voice.").font(.title2).foregroundStyle(.white.opacity(0.75))
                }
                VStack(alignment: .leading, spacing: 14) {
                    Text("Connect to your game").font(.title3.bold())
                    Text("Start JParty on your computer and join the same Wi-Fi. Scan the QR code on the game screen to join.")
                        .foregroundStyle(.secondary)
                    Button {
                        addressFocused = false
                        showScanner = true
                    } label: {
                        Label("Scan QR Code", systemImage: "qrcode.viewfinder")
                            .font(.headline).frame(maxWidth: .infinity).padding(.vertical, 8)
                    }
                    .buttonStyle(.borderedProminent).foregroundStyle(.black)
                    .accessibilityIdentifier("scanQRCode")
                    Text("Or enter the computer’s address").font(.footnote).foregroundStyle(.secondary)
                    TextField("192.168.1.25:8080", text: $serverText)
                        .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                        .padding().background(.white.opacity(0.09), in: RoundedRectangle(cornerRadius: 12))
                        .focused($addressFocused).submitLabel(.go).onSubmit(connect)
                        .accessibilityIdentifier("serverAddress")
                    if let addressError { Text(addressError).font(.callout).foregroundStyle(.orange) }
                    Button(action: connect) {
                        Label("Join Game", systemImage: "arrow.right.circle.fill")
                            .font(.headline).frame(maxWidth: .infinity).padding(.vertical, 8)
                    }
                    .buttonStyle(.bordered)
                    .accessibilityIdentifier("joinGame")
                }
                .padding(22).background(.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 24))
                VStack(alignment: .leading, spacing: 16) {
                    Label("Voice recording uses your iPhone’s microphone permission.", systemImage: "mic.fill")
                    Label("Use your computer’s Wi-Fi address. localhost means this phone.", systemImage: "wifi")
                    Label("Local HTTP works here. No local certificate setup is needed.", systemImage: "checkmark.shield")
                }
                .font(.callout).foregroundStyle(.white.opacity(0.65))
                Button("Check Microphone Access", systemImage: "mic.badge.plus") { checkMicrophone() }
            }
            .frame(maxWidth: 520).padding(26).frame(maxWidth: .infinity)
        }
        .scrollDismissesKeyboard(.interactively)
    }

    private func game(_ server: ServerAddress) -> some View {
        ZStack {
            GameWebView(server: server, audio: audio, browser: browser)
                .id(server.url)
            if let error = browser.error {
                VStack(spacing: 18) {
                    Image(systemName: "wifi.exclamationmark").font(.largeTitle)
                    Text("Couldn’t connect").font(.title2.bold())
                    Text(error).font(.callout).multilineTextAlignment(.center)
                    Button("Try Again") { browser.reload() }.buttonStyle(.borderedProminent)
                    Button("Change Address") { disconnect() }
                    Button("Open Settings") {
                        if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
                    }
                }
                .padding(28).frame(maxWidth: 480).background(.regularMaterial, in: RoundedRectangle(cornerRadius: 24)).padding()
            } else if browser.isLoading {
                ProgressView("Connecting to \(server.url.host ?? "JParty")…")
                    .padding(24).background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18))
            }
        }
    }

    private func connect() {
        do {
            #if targetEnvironment(simulator)
            let address = try ServerAddress(serverText, allowLoopback: true)
            #else
            let address = try ServerAddress(serverText)
            #endif
            join(address)
        } catch { addressError = error.localizedDescription }
    }

    private func join(_ address: ServerAddress) {
        addressFocused = false
        addressError = nil
        browser.error = nil
        browser.isLoading = true
        serverText = address.url.absoluteString
        server = address
        UIApplication.shared.isIdleTimerDisabled = true
    }

    private func disconnect() {
        audio.cancel()
        server = nil
        UIApplication.shared.isIdleTimerDisabled = false
    }

    private func checkMicrophone() {
        Task { if !(await audio.requestPermission()) { showPermissionHelp = true } }
    }
}
