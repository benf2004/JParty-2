import Foundation

struct ServerAddress: Equatable {
    let url: URL

    init(qrCode: String, allowLoopback: Bool = false) throws {
        let trimmed = qrCode.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let scheme = URLComponents(string: trimmed)?.scheme?.lowercased(),
              ["http", "https"].contains(scheme) else { throw AddressError.invalid }
        let address = try ServerAddress(qrCode, allowLoopback: allowLoopback)
        guard var parts = URLComponents(url: address.url, resolvingAgainstBaseURL: false) else {
            throw AddressError.invalid
        }
        // The desktop QR uses HTTPS by default. Its standard local HTTP listener
        // avoids the self-signed certificate when joining through the native app.
        if parts.scheme == "https", parts.port == 8443,
           Self.isLocalHost(parts.host ?? "") {
            parts.scheme = "http"
            parts.port = 8080
        }
        guard let url = parts.url else { throw AddressError.invalid }
        self.url = url
    }

    private static func isLocalHost(_ host: String) -> Bool {
        let host = host.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "[]"))
        if host == "localhost" || host.hasSuffix(".local") || (!host.contains(".") && !host.contains(":")) { return true }
        let octets = host.split(separator: ".").compactMap { Int($0) }
        if octets.count == 4, octets.allSatisfy({ (0...255).contains($0) }) {
            return octets[0] == 10 || octets[0] == 127
                || (octets[0] == 192 && octets[1] == 168)
                || (octets[0] == 172 && (16...31).contains(octets[1]))
                || (octets[0] == 169 && octets[1] == 254)
        }
        return host == "::1" || (host.hasPrefix("fc") && host.contains(":"))
            || (host.hasPrefix("fd") && host.contains(":")) || host.hasPrefix("fe80:")
    }

    init(_ input: String, allowLoopback: Bool = false) throws {
        let trimmed = input.trimmingCharacters(in: .whitespacesAndNewlines)
        let value = trimmed.contains("://") ? trimmed : "http://" + trimmed
        guard !trimmed.isEmpty,
              var parts = URLComponents(string: value),
              let host = parts.host, !host.isEmpty,
              ["http", "https"].contains(parts.scheme?.lowercased() ?? ""),
              parts.user == nil, parts.password == nil,
              parts.query == nil, parts.fragment == nil,
              ["", "/", "/play"].contains(parts.path),
              !host.contains(where: { $0.isWhitespace }),
              parts.port == nil || (1...65535).contains(parts.port!) else {
            throw AddressError.invalid
        }
        let normalizedHost = host.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "[]"))
        if !allowLoopback && (normalizedHost == "localhost" || normalizedHost.hasSuffix(".localhost")
            || normalizedHost.hasPrefix("127.") || normalizedHost == "::1" || normalizedHost == "0.0.0.0") {
            throw AddressError.loopback
        }
        parts.scheme = parts.scheme?.lowercased()
        // An address without a port uses JParty's default, not port 80/443.
        if parts.port == nil { parts.port = parts.scheme == "https" ? 8443 : 8080 }
        parts.path = "/"
        guard let url = parts.url else { throw AddressError.invalid }
        self.url = url
    }

    func contains(_ candidate: URL?) -> Bool {
        guard let candidate else { return false }
        return candidate.scheme?.lowercased() == url.scheme?.lowercased()
            && candidate.host?.lowercased() == url.host?.lowercased()
            && candidate.port == url.port
    }

    enum AddressError: LocalizedError {
        case invalid, loopback
        var errorDescription: String? {
            switch self {
            case .invalid:
                return "Enter the computer’s JParty address, for example http://192.168.1.25:8080."
            case .loopback:
                return "localhost points to this iPhone. Enter the computer’s Wi-Fi address shown on the JParty screen."
            }
        }
    }
}
