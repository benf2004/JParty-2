import AVFoundation
import SwiftUI

struct QRScannerView: View {
    let onScanned: (ServerAddress) -> Void
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var scanner = QRScannerModel()
    @State private var invalidCodeMessage: String?
    @State private var hasJoined = false

    var body: some View {
        NavigationStack {
            ZStack {
                Color.black.ignoresSafeArea()
                if scanner.state == .scanning {
                    CameraPreview(session: scanner.camera.session).ignoresSafeArea()
                    VStack(spacing: 24) {
                        Spacer()
                        RoundedRectangle(cornerRadius: 24)
                            .stroke(.white.opacity(0.9), style: StrokeStyle(lineWidth: 4, dash: [24, 10]))
                            .frame(maxWidth: 280, maxHeight: 280)
                            .accessibilityHidden(true)
                        Spacer()
                        Text(invalidCodeMessage ?? "Point your camera at the QR code on the JParty game screen. You’ll join automatically.")
                            .font(.headline).multilineTextAlignment(.center)
                            .padding(20).frame(maxWidth: .infinity)
                            .background(.black.opacity(0.75), in: RoundedRectangle(cornerRadius: 18))
                            .padding()
                    }
                } else {
                    VStack(spacing: 20) {
                        Image(systemName: "qrcode.viewfinder").font(.system(size: 60))
                        if scanner.state == .loading {
                            ProgressView("Opening camera…")
                        } else {
                            Text(scanner.state.message).multilineTextAlignment(.center)
                            if scanner.state == .denied {
                                Button("Open Settings") {
                                    if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
                                }.buttonStyle(.borderedProminent)
                            }
                            Button("Enter Address Instead") { dismiss() }.buttonStyle(.bordered)
                        }
                        if let invalidCodeMessage { Text(invalidCodeMessage).foregroundStyle(.orange) }
                    }.padding(30)
                }
            }
            .navigationTitle("Scan Game QR Code")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } } }
            .preferredColorScheme(.dark)
            .task { await scanner.start() }
            .onDisappear { scanner.stop() }
            .onChange(of: scenePhase) { _, phase in
                if phase == .background { scanner.stop() }
                if phase == .active { Task { await scanner.start() } }
            }
            .onChange(of: scanner.code) { _, code in
                guard !hasJoined, let code else { return }
                do {
                    #if targetEnvironment(simulator)
                    let address = try ServerAddress(qrCode: code, allowLoopback: true)
                    #else
                    let address = try ServerAddress(qrCode: code)
                    #endif
                    hasJoined = true
                    scanner.stop()
                    UIImpactFeedbackGenerator(style: .light).impactOccurred()
                    onScanned(address)
                } catch {
                    invalidCodeMessage = "That QR code isn’t a valid game address. \(error.localizedDescription)"
                }
            }
        }
    }
}

@MainActor
private final class QRScannerModel: ObservableObject {
    enum State: Equatable {
        case loading, scanning, denied, unavailable, failed
        var message: String {
            switch self {
            case .denied: return "Allow Camera in JParty’s Settings to scan the game’s QR code."
            case .unavailable: return "No camera is available. Scan on your iPhone or enter the computer’s address."
            default: return "Couldn’t start the camera. Close the scanner and try again, or enter the address."
            }
        }
    }

    @Published private(set) var state: State = .loading
    @Published private(set) var code: String?
    private var generation = UUID()
    private var active = false
    lazy var camera = QRScanSession(onCode: { [weak self] code in
        guard self?.active == true else { return }
        self?.code = code
    }, onError: { [weak self] in
        guard self?.active == true else { return }
        self?.active = false
        self?.state = .failed
    })

    func start() async {
        guard !active else { return }
        active = true
        state = .loading
        let id = UUID()
        generation = id
        #if DEBUG && targetEnvironment(simulator)
        // Simulator UI tests inject the same decoded string the camera delegate emits.
        if let fixture = ProcessInfo.processInfo.environment["JPARTY_TEST_QR_CODE"] {
            state = .unavailable
            code = fixture
            return
        }
        #endif
        guard AVCaptureDevice.default(for: .video) != nil else { active = false; state = .unavailable; return }
        let granted = await AVCaptureDevice.requestAccess(for: .video)
        guard generation == id, !Task.isCancelled else { return }
        guard granted else { active = false; state = .denied; return }
        state = .scanning
        camera.start()
    }

    func stop() {
        generation = UUID()
        active = false
        camera.stop()
    }
}

// All capture configuration and blocking start/stop calls use one serial queue.
private final class QRScanSession: NSObject, AVCaptureMetadataOutputObjectsDelegate, @unchecked Sendable {
    let session = AVCaptureSession()
    private let queue = DispatchQueue(label: "com.jparty.qr-camera", qos: .userInitiated)
    private var configured = false
    private let onCode: @MainActor (String) -> Void
    private let onError: @MainActor () -> Void

    init(onCode: @escaping @MainActor (String) -> Void, onError: @escaping @MainActor () -> Void) {
        self.onCode = onCode
        self.onError = onError
    }

    func start() {
        queue.async { [self] in
            do {
                if !configured { try configure() }
                if !session.isRunning { session.startRunning() }
                if !session.isRunning { Task { @MainActor in onError() } }
            } catch {
                Task { @MainActor in onError() }
            }
        }
    }

    func stop() {
        queue.async { [self] in
            if session.isRunning { session.stopRunning() }
        }
    }

    private func configure() throws {
        session.beginConfiguration()
        defer {
            if !configured {
                session.inputs.forEach { session.removeInput($0) }
                session.outputs.forEach { session.removeOutput($0) }
            }
            session.commitConfiguration()
        }
        session.automaticallyConfiguresApplicationAudioSession = false
        guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back)
                ?? AVCaptureDevice.default(for: .video) else { throw CameraError.unavailable }
        let input = try AVCaptureDeviceInput(device: device)
        let output = AVCaptureMetadataOutput()
        guard session.canAddInput(input) else { throw CameraError.unavailable }
        session.addInput(input)
        guard session.canAddOutput(output) else { throw CameraError.unavailable }
        session.addOutput(output)
        guard output.availableMetadataObjectTypes.contains(.qr) else { throw CameraError.unavailable }
        output.setMetadataObjectsDelegate(self, queue: .main)
        output.metadataObjectTypes = [.qr]
        configured = true
    }

    func metadataOutput(_ output: AVCaptureMetadataOutput, didOutput metadataObjects: [AVMetadataObject],
                        from connection: AVCaptureConnection) {
        guard let value = metadataObjects.compactMap({ ($0 as? AVMetadataMachineReadableCodeObject)?.stringValue }).first else { return }
        Task { @MainActor in onCode(value) }
    }

    private enum CameraError: Error { case unavailable }
}

private struct CameraPreview: UIViewRepresentable {
    let session: AVCaptureSession

    func makeUIView(context: Context) -> PreviewView {
        let view = PreviewView()
        view.previewLayer.session = session
        view.previewLayer.videoGravity = .resizeAspectFill
        return view
    }

    func updateUIView(_ uiView: PreviewView, context: Context) {}

    final class PreviewView: UIView {
        override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }
        var previewLayer: AVCaptureVideoPreviewLayer { layer as! AVCaptureVideoPreviewLayer }

        override func layoutSubviews() {
            super.layoutSubviews()
            let angle: CGFloat
            switch window?.windowScene?.interfaceOrientation {
            case .landscapeLeft: angle = 0
            case .landscapeRight: angle = 180
            case .portraitUpsideDown: angle = 270
            default: angle = 90
            }
            if let connection = previewLayer.connection, connection.isVideoRotationAngleSupported(angle) {
                connection.videoRotationAngle = angle
            }
        }
    }
}
