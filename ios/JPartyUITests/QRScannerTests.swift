import XCTest

final class QRScannerTests: XCTestCase {
    func testScannedGameAddressConnectsAutomatically() {
        let app = XCUIApplication()
        app.launchEnvironment["JPARTY_TEST_QR_CODE"] = "http://127.0.0.1:18080"
        app.launch()
        let scan = app.buttons["scanQRCode"]
        XCTAssertTrue(scan.waitForExistence(timeout: 10))
        scan.tap()
        XCTAssertTrue(app.webViews.buttons["Record Answer"].waitForExistence(timeout: 15), app.debugDescription)
        app.buttons["Leave"].tap()
        XCTAssertTrue(scan.waitForExistence(timeout: 5))
    }

    func testUnrelatedQRCodeKeepsScannerOpenWithManualEntryAvailable() {
        let app = XCUIApplication()
        app.launchEnvironment["JPARTY_TEST_QR_CODE"] = "WIFI:S:party;T:WPA;P:password;;"
        app.launch()
        app.buttons["scanQRCode"].tap()
        let invalidMessage = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'That QR code isn’t a valid game address.'")).firstMatch
        XCTAssertTrue(invalidMessage.waitForExistence(timeout: 5))
        app.buttons["Enter Address Instead"].tap()
        XCTAssertTrue(app.textFields["serverAddress"].waitForExistence(timeout: 5))
    }

    func testScannerWithoutCameraCanBeCancelled() {
        let app = XCUIApplication()
        app.launch()
        app.buttons["scanQRCode"].tap()
        XCTAssertTrue(app.buttons["Enter Address Instead"].waitForExistence(timeout: 5))
        app.buttons["Cancel"].tap()
        XCTAssertTrue(app.buttons["scanQRCode"].waitForExistence(timeout: 5))
    }
}
