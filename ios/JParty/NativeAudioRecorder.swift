import AVFoundation
import Combine
import UIKit

@MainActor
final class NativeAudioRecorder: NSObject, ObservableObject, AVAudioRecorderDelegate {
    @Published private(set) var isRecording = false
    private var busy = false
    private var requestID: UUID?
    private var recorder: AVAudioRecorder?
    private var fileURL: URL?
    private var continuation: CheckedContinuation<String, Error>?

    func requestPermission() async -> Bool {
        await AVAudioApplication.requestRecordPermission()
    }

    func record(durationMs: Double) async throws -> String {
        guard !busy else { throw RecordingError.busy }
        busy = true
        let id = UUID()
        requestID = id
        defer {
            busy = false
            requestID = nil
            cleanup()
        }
        guard await requestPermission() else { throw RecordingError.permission }
        guard requestID == id, UIApplication.shared.applicationState != .background else {
            throw RecordingError.cancelled
        }
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.record, mode: .measurement)
        try session.setActive(true)
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("jparty-\(id).m4a")
        fileURL = url
        let audio = try AVAudioRecorder(url: url, settings: [
            AVFormatIDKey: kAudioFormatMPEG4AAC,
            AVSampleRateKey: 44_100,
            AVNumberOfChannelsKey: 1,
            AVEncoderBitRateKey: 64_000,
            AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue
        ])
        recorder = audio
        audio.delegate = self
        return try await withCheckedThrowingContinuation { continuation in
            self.continuation = continuation
            // Bound every request, including malformed messages from web content.
            let duration = durationMs.isFinite ? min(max(durationMs / 1000, 0.5), 30) : 4.5
            guard audio.prepareToRecord(), audio.record(forDuration: duration) else {
                finish(.failure(RecordingError.failed))
                return
            }
            isRecording = true
        }
    }

    func cancel() {
        requestID = nil
        finish(.failure(RecordingError.cancelled))
        cleanup()
    }

    private func finish(_ result: Result<String, Error>) {
        guard let pending = continuation else { return }
        continuation = nil
        if isRecording { isRecording = false }
        pending.resume(with: result)
    }

    private func cleanup() {
        // Remove the delegate first so cancellation can't complete another request.
        recorder?.delegate = nil
        recorder?.stop()
        recorder = nil
        if isRecording { isRecording = false }
        if let fileURL { try? FileManager.default.removeItem(at: fileURL) }
        fileURL = nil
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    nonisolated func audioRecorderDidFinishRecording(_ recorder: AVAudioRecorder, successfully flag: Bool) {
        Task { @MainActor in
            guard self.recorder === recorder, self.continuation != nil else { return }
            do {
                guard flag else { throw RecordingError.failed }
                let data = try Data(contentsOf: recorder.url)
                guard !data.isEmpty else { throw RecordingError.failed }
                finish(.success(data.base64EncodedString()))
            } catch {
                finish(.failure(error))
            }
        }
    }

    nonisolated func audioRecorderEncodeErrorDidOccur(_ recorder: AVAudioRecorder, error: Error?) {
        Task { @MainActor in
            guard self.recorder === recorder else { return }
            finish(.failure(error ?? RecordingError.failed))
        }
    }

    enum RecordingError: LocalizedError {
        case busy, permission, cancelled, failed
        var errorDescription: String? {
            switch self {
            case .busy: return "A recording is already in progress."
            case .permission: return "Microphone access is off. Open JParty’s Settings and allow Microphone, or use the on-screen controls."
            case .cancelled: return "Recording stopped. Keep JParty open, then try again."
            case .failed: return "Could not record audio. Check your microphone and try again."
            }
        }
    }
}
