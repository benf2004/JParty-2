import XCTest

final class NativeMicrophoneTests: XCTestCase {
    // Run ios/test-native-client.sh to start the HTTP fixture.
    func testRecordsAndUploadsNativeAudioOverHTTP() {
        let app = XCUIApplication()
        app.resetAuthorizationStatus(for: .microphone)
        app.launch()
        let address = app.textFields["serverAddress"]
        XCTAssertTrue(address.waitForExistence(timeout: 10))
        address.tap()
        if let value = address.value as? String, !value.isEmpty {
            address.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: value.count))
        }
        address.typeText("http://127.0.0.1:18080")
        app.buttons["joinGame"].tap()
        let record = app.webViews.buttons["Record Answer"]
        XCTAssertTrue(record.waitForExistence(timeout: 15), app.debugDescription)
        record.tap()
        let system = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let allow = system.alerts.buttons.matching(NSPredicate(format: "label == 'Allow' OR label == 'OK'")).firstMatch
        XCTAssertTrue(allow.waitForExistence(timeout: 8), "Expected the native iOS microphone permission prompt")
        allow.tap()
        XCTAssertTrue(app.webViews.staticTexts["Native microphone upload received"].waitForExistence(timeout: 15), app.debugDescription)
        app.buttons["Leave"].tap()
        XCTAssertTrue(address.waitForExistence(timeout: 5))
    }
}
