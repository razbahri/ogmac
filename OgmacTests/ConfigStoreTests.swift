import XCTest
@testable import Ogmac

final class ConfigStoreTests: XCTestCase {
    private func fixtureURL(_ name: String) -> URL {
        let testDir = URL(fileURLWithPath: #file).deletingLastPathComponent()
        return testDir.appendingPathComponent("Fixtures/\(name)")
    }

    private func tmpURL() -> URL {
        FileManager.default.temporaryDirectory
            .appendingPathComponent("config_test_\(UUID().uuidString).yaml")
    }

    func testLoadCanonical() throws {
        let store = ConfigStore(configPath: fixtureURL("config_canonical.yaml"))
        let doc = try store.load()

        XCTAssertEqual(doc.outlook.account, "you@example.com")
        XCTAssertEqual(doc.outlook.sourceCalendar, "default")
        XCTAssertEqual(doc.outlook.readMethod, "apple_calendar")
        XCTAssertEqual(doc.google.account, "you@gmail.com")
        XCTAssertEqual(doc.google.targetCalendarId, "abc123@group.calendar.google.com")
        XCTAssertEqual(doc.sync.windowPastDays, 1)
        XCTAssertEqual(doc.sync.windowFutureDays, 30)
        XCTAssertTrue(doc.privacy.copySubject)
        XCTAssertFalse(doc.privacy.copyAttendees)
        XCTAssertEqual(doc.failure.maxConsecutiveBeforeDisable, 5)
        XCTAssertTrue(doc.failure.notifyOnFailure)
    }

    func testLoadLegacyIgnoresIntervalSeconds() throws {
        let store = ConfigStore(configPath: fixtureURL("config_legacy.yaml"))
        let doc = try store.load()

        XCTAssertEqual(doc.sync.windowPastDays, 2)
        XCTAssertEqual(doc.sync.windowFutureDays, 60)
        XCTAssertEqual(doc.outlook.readMethod, "microsoft_graph")
    }

    func testRoundTrip() throws {
        let src = ConfigStore(configPath: fixtureURL("config_canonical.yaml"))
        var doc = try src.load()

        doc.sync.windowPastDays = 7
        doc.sync.windowFutureDays = 60
        doc.failure.maxConsecutiveBeforeDisable = 10

        let dest = tmpURL()
        // Create the file so replaceItemAt has something to replace
        try "".write(to: dest, atomically: true, encoding: .utf8)
        defer { try? FileManager.default.removeItem(at: dest) }

        let store = ConfigStore(configPath: dest)
        try store.save(doc)
        let reloaded = try store.load()

        XCTAssertEqual(reloaded.sync.windowPastDays, 7)
        XCTAssertEqual(reloaded.sync.windowFutureDays, 60)
        XCTAssertEqual(reloaded.failure.maxConsecutiveBeforeDisable, 10)
        XCTAssertEqual(reloaded.outlook.account, doc.outlook.account)
        XCTAssertEqual(reloaded.google.targetCalendarId, doc.google.targetCalendarId)
    }

    func testSaveUsesAtomicReplacement() throws {
        let dest = tmpURL()
        try "".write(to: dest, atomically: true, encoding: .utf8)
        defer { try? FileManager.default.removeItem(at: dest) }

        let src = ConfigStore(configPath: fixtureURL("config_canonical.yaml"))
        var doc = try src.load()
        doc.sync.windowPastDays = 14

        let store = ConfigStore(configPath: dest)
        try store.save(doc)

        // Confirm temp file was cleaned up
        let tmp = dest.appendingPathExtension("tmp")
        XCTAssertFalse(FileManager.default.fileExists(atPath: tmp.path))

        // Confirm final file has the new value
        let reloaded = try store.load()
        XCTAssertEqual(reloaded.sync.windowPastDays, 14)
    }

    func testLoadMissingFileThrows() {
        let store = ConfigStore(configPath: fixtureURL("does_not_exist.yaml"))
        XCTAssertThrowsError(try store.load()) { error in
            if case ConfigStoreError.fileNotFound = error {} else {
                XCTFail("Expected ConfigStoreError.fileNotFound, got \(error)")
            }
        }
    }
}
