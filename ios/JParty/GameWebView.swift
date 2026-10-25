import SwiftUI
import WebKit

@MainActor
final class GameBrowser: ObservableObject {
    @Published var isLoading = true
    @Published var error: String?
    weak var webView: WKWebView?
    var serverURL: URL?

    func reload() {
        error = nil
        isLoading = true
        if let serverURL { webView?.load(URLRequest(url: serverURL)) }
    }
}

struct GameWebView: UIViewRepresentable {
    let server: ServerAddress
    @ObservedObject var audio: NativeAudioRecorder
    @ObservedObject var browser: GameBrowser

    func makeCoordinator() -> Coordinator { Coordinator(server: server, audio: audio, browser: browser) }

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.userContentController.addScriptMessageHandler(context.coordinator, contentWorld: .page, name: "jpartyAudio")
        configuration.userContentController.addUserScript(WKUserScript(source: """
            document.addEventListener('DOMContentLoaded', function() {
                document.body.classList.add('native-ios');
                var hint = document.querySelector('.buzz-hint');
                if (hint) hint.textContent = 'Keep JParty open while playing. Your screen stays awake.';
            });
            """, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        let view = WKWebView(frame: .zero, configuration: configuration)
        view.navigationDelegate = context.coordinator
        view.uiDelegate = context.coordinator
        view.isOpaque = false
        view.backgroundColor = UIColor(red: 0.035, green: 0.035, blue: 0.18, alpha: 1)
        view.scrollView.backgroundColor = view.backgroundColor
        view.allowsBackForwardNavigationGestures = false
        view.isInspectable = _isDebugAssertConfiguration()
        context.coordinator.webView = view
        browser.webView = view
        browser.serverURL = server.url
        view.load(URLRequest(url: server.url))
        return view
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}

    static func dismantleUIView(_ uiView: WKWebView, coordinator: Coordinator) {
        coordinator.audio.cancel()
        uiView.stopLoading()
        uiView.configuration.userContentController.removeScriptMessageHandler(forName: "jpartyAudio", contentWorld: .page)
        uiView.navigationDelegate = nil
        uiView.uiDelegate = nil
        uiView.loadHTMLString("", baseURL: nil)
    }

    @MainActor
    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandlerWithReply {
        let server: ServerAddress
        let audio: NativeAudioRecorder
        let browser: GameBrowser
        weak var webView: WKWebView?

        init(server: ServerAddress, audio: NativeAudioRecorder, browser: GameBrowser) {
            self.server = server
            self.audio = audio
            self.browser = browser
        }

        func userContentController(_ userContentController: WKUserContentController,
                                   didReceive message: WKScriptMessage,
                                   replyHandler: @escaping (Any?, String?) -> Void) {
            guard message.frameInfo.isMainFrame, server.contains(message.frameInfo.request.url),
                  server.contains(webView?.url),
                  let body = message.body as? [String: Any],
                  let purpose = body["purpose"] as? String,
                  ["answer", "clue_selection", "daily_double_wager"].contains(purpose),
                  let duration = body["durationMs"] as? Double, duration.isFinite else {
                replyHandler(nil, "Invalid recording request.")
                return
            }
            Task { @MainActor in
                do {
                    let base64 = try await audio.record(durationMs: duration)
                    replyHandler(["audioBase64": base64], nil)
                } catch {
                    replyHandler(nil, error.localizedDescription)
                }
            }
        }

        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            // Only the game host may become the main document and use the microphone bridge.
            decisionHandler(server.contains(navigationAction.request.url) ? .allow : .cancel)
        }

        func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
            audio.cancel()
            browser.isLoading = true
            browser.error = nil
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            browser.isLoading = false
        }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            show(error)
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) { show(error) }

        func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
            audio.cancel()
            webView.reload()
        }

        private func show(_ error: Error) {
            if (error as NSError).code == NSURLErrorCancelled { return }
            browser.isLoading = false
            browser.error = "\(error.localizedDescription)\n\nCheck that JParty is running, both devices are on the same Wi-Fi, and Local Network access is allowed in Settings. For the local server, use http:// with port 8080."
        }

        // The existing game uses alerts and a keyboard-name prompt.
        func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                     initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
            let alert = UIAlertController(title: "JParty", message: message, preferredStyle: .alert)
            alert.addAction(UIAlertAction(title: "OK", style: .default) { _ in completionHandler() })
            present(alert, fallback: completionHandler)
        }

        func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String,
                     defaultText: String?, initiatedByFrame frame: WKFrameInfo,
                     completionHandler: @escaping (String?) -> Void) {
            let alert = UIAlertController(title: prompt, message: nil, preferredStyle: .alert)
            alert.addTextField { $0.text = defaultText; $0.autocapitalizationType = .words }
            alert.addAction(UIAlertAction(title: "Cancel", style: .cancel) { _ in completionHandler(nil) })
            alert.addAction(UIAlertAction(title: "Join", style: .default) { [weak alert] _ in
                completionHandler(alert?.textFields?.first?.text)
            })
            present(alert) { completionHandler(nil) }
        }

        private func present(_ alert: UIAlertController, fallback: () -> Void) {
            guard var presenter = webView?.window?.rootViewController else { fallback(); return }
            while let presented = presenter.presentedViewController { presenter = presented }
            guard !presenter.isBeingDismissed else { fallback(); return }
            presenter.present(alert, animated: true)
        }
    }
}
