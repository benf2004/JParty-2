import XCTest
@testable import JParty

final class ServerAddressTests: XCTestCase {
    func testBareAddressUsesJPartyPort() throws {
        XCTAssertEqual(try ServerAddress(" 192.168.1.25 ").url.absoluteString, "http://192.168.1.25:8080/")
        XCTAssertEqual(try ServerAddress("game-mac.local:8090/play").url.absoluteString, "http://game-mac.local:8090/")
    }

    func testHTTPSRemainsHTTPS() throws {
        XCTAssertEqual(try ServerAddress("https://game-mac.local").url.absoluteString, "https://game-mac.local:8443/")
    }

    func testDesktopHTTPSQRCodeUsesDefaultLocalHTTPListener() throws {
        for host in ["192.168.1.25", "10.0.0.12", "172.20.1.2", "game-mac.local", "[fd12::1]"] {
            XCTAssertEqual(try ServerAddress(qrCode: "https://\(host):8443").url.absoluteString, "http://\(host):8080/")
        }
        XCTAssertEqual(try ServerAddress(qrCode: "http://192.168.1.25:8090/play").url.absoluteString,
                       "http://192.168.1.25:8090/")
    }

    func testQRCodePreservesPublicHTTPSAndCustomPorts() throws {
        for host in ["example.com", "203.0.113.12", "172.32.1.2", "192.169.1.2"] {
            XCTAssertEqual(try ServerAddress(qrCode: "https://\(host):8443").url.absoluteString, "https://\(host):8443/")
        }
        XCTAssertEqual(try ServerAddress(qrCode: "https://game-mac.local:9443").url.scheme, "https")
    }

    func testQRCodeRejectsUnrelatedPayloadsAndPhoneLoopback() {
        for value in ["WIFI:S:party;T:WPA;P:password;;", "javascript:alert(1)", "https://localhost:8443",
                      "https://127.0.0.1:8443", "https://example.com/login", "hello world", "hello", "12345"] {
            XCTAssertThrowsError(try ServerAddress(qrCode: value), value)
        }
    }

    func testRejectsPhoneLoopbackAndInvalidAddresses() {
        for value in ["", "localhost", "http://127.0.0.1:8080", "[::1]", "0.0.0.0", "ftp://game.local",
                      "http://user:password@game.local", "game.local:99999", "game.local/designer", "game.local?other=host"] {
            XCTAssertThrowsError(try ServerAddress(value), value)
        }
    }

    func testSimulatorCanUseLoopback() throws {
        XCTAssertEqual(try ServerAddress("127.0.0.1", allowLoopback: true).url.host, "127.0.0.1")
    }

    func testBridgeTrustIsBoundToOrigin() throws {
        let server = try ServerAddress("192.168.1.25:8080")
        XCTAssertTrue(server.contains(URL(string: "http://192.168.1.25:8080/play")))
        for value in ["http://192.168.1.26:8080/", "https://192.168.1.25:8080/", "http://192.168.1.25:8443/", "http://example.com/"] {
            XCTAssertFalse(server.contains(URL(string: value)), value)
        }
    }
}
