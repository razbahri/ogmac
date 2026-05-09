import XCTest
@testable import Ogmac

final class StateReaderTests: XCTestCase {
    private func fixtureURL(_ name: String) -> URL {
        let bundle = Bundle(for: type(of: self))
        if let url = bundle.url(forResource: name, withExtension: "sqlite") {
            return url
        }
        // Fall back to source-relative path for when tests run via xcodebuild
        let testDir = URL(fileURLWithPath: #file).deletingLastPathComponent()
        return testDir.appendingPathComponent("Fixtures/\(name).sqlite")
    }

    func testHealthySnapshot() async throws {
        let reader = StateReader(dbPath: fixtureURL("state_healthy").path)
        let snap = try await reader.snapshot()

        XCTAssertNotNil(snap.lastSuccessAt)
        XCTAssertEqual(snap.consecutiveFailures, 0)
        XCTAssertFalse(snap.disabled)
        XCTAssertFalse(snap.paused)
        XCTAssertNil(snap.disableReason)
    }

    func testHealthyLastSuccessAt() async throws {
        let reader = StateReader(dbPath: fixtureURL("state_healthy").path)
        let snap = try await reader.snapshot()

        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        let expected = formatter.date(from: "2026-05-08T14:30:00Z")
        XCTAssertEqual(snap.lastSuccessAt, expected)
    }

    func testDisabledSnapshot() async throws {
        let reader = StateReader(dbPath: fixtureURL("state_disabled").path)
        let snap = try await reader.snapshot()

        XCTAssertTrue(snap.disabled)
        XCTAssertFalse(snap.paused)
        XCTAssertEqual(snap.consecutiveFailures, 5)
        XCTAssertNotNil(snap.disableReason)
        XCTAssertTrue(snap.disableReason!.contains("TokenRefreshError"))
    }

    func testPausedSnapshot() async throws {
        let reader = StateReader(dbPath: fixtureURL("state_paused").path)
        let snap = try await reader.snapshot()

        XCTAssertTrue(snap.paused)
        XCTAssertFalse(snap.disabled)
        XCTAssertEqual(snap.consecutiveFailures, 0)
        XCTAssertNil(snap.disableReason)
    }

    func testFailedSnapshot() async throws {
        let reader = StateReader(dbPath: fixtureURL("state_failed").path)
        let snap = try await reader.snapshot()

        XCTAssertFalse(snap.disabled)
        XCTAssertFalse(snap.paused)
        XCTAssertEqual(snap.consecutiveFailures, 3)
        XCTAssertNil(snap.disableReason)
    }

    func testMissingConsecutiveFailuresDefaultsToZero() async throws {
        // Use healthy fixture which has consecutive_failures=0 explicitly,
        // but also test empty DB where the key is absent
        let tmp = FileManager.default.temporaryDirectory
            .appendingPathComponent("state_empty_\(UUID().uuidString).sqlite")
        defer { try? FileManager.default.removeItem(at: tmp) }

        // Create empty DB with schema but no run_state rows
        let schema = """
        CREATE TABLE IF NOT EXISTS run_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/sqlite3")
        process.arguments = [tmp.path, schema]
        try process.run()
        process.waitUntilExit()

        let reader = StateReader(dbPath: tmp.path)
        let snap = try await reader.snapshot()
        XCTAssertEqual(snap.consecutiveFailures, 0)
        XCTAssertNil(snap.lastSuccessAt)
        XCTAssertFalse(snap.disabled)
        XCTAssertFalse(snap.paused)
    }
}
