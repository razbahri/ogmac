import XCTest
@testable import Ogmac

final class LogReaderTests: XCTestCase {
    private func fixtureURL(_ name: String) -> URL {
        let testDir = URL(fileURLWithPath: #file).deletingLastPathComponent()
        return testDir.appendingPathComponent("Fixtures/\(name)")
    }

    func testCleanRun() async throws {
        let reader = LogReader(logPath: fixtureURL("sync_log_clean.txt"))
        let runs = try await reader.tail(maxRuns: 50)

        XCTAssertEqual(runs.count, 1)
        let run = runs[0]
        if case .success = run.result {} else { XCTFail("Expected success") }
        XCTAssertEqual(run.durationMs, 3377)
        XCTAssertNotNil(run.counts)
        XCTAssertEqual(run.counts?.create, 2)
        XCTAssertEqual(run.counts?.update, 0)
        XCTAssertEqual(run.counts?.delete, 0)
        XCTAssertEqual(run.counts?.skip, 40)
    }

    func testFailedRun() async throws {
        let reader = LogReader(logPath: fixtureURL("sync_log_failed.txt"))
        let runs = try await reader.tail(maxRuns: 50)

        XCTAssertEqual(runs.count, 1)
        let run = runs[0]
        if case .failure(let reason) = run.result {
            XCTAssertEqual(reason, "TokenRefreshError")
        } else {
            XCTFail("Expected failure")
        }
        XCTAssertNil(run.durationMs)
    }

    func testPartialRun() async throws {
        let reader = LogReader(logPath: fixtureURL("sync_log_partial.txt"))
        let runs = try await reader.tail(maxRuns: 50)

        XCTAssertEqual(runs.count, 1)
        let run = runs[0]
        if case .failure(let reason) = run.result {
            XCTAssertEqual(reason, "incomplete")
        } else {
            XCTFail("Expected incomplete failure")
        }
        XCTAssertNil(run.durationMs)
        XCTAssertNil(run.counts)
    }

    func testSkippedLinesNotCounted() async throws {
        let reader = LogReader(logPath: fixtureURL("sync_log_skipped.txt"))
        let runs = try await reader.tail(maxRuns: 50)

        XCTAssertEqual(runs.count, 1)
        if case .success = runs[0].result {} else { XCTFail("Expected success") }
    }

    func testRotatedLogs() async throws {
        let logURL = fixtureURL("sync_log_rotated.log")
        let reader = LogReader(logPath: logURL)
        let runs = try await reader.tail(maxRuns: 50)

        XCTAssertEqual(runs.count, 2)
        // Older run comes first (from .log.1)
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss'Z'"
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        let oldStart = formatter.date(from: "2026-05-07T10:00:00Z")!
        let newStart = formatter.date(from: "2026-05-08T14:15:00Z")!
        XCTAssertEqual(runs[0].startedAt, oldStart)
        XCTAssertEqual(runs[1].startedAt, newStart)
        if case .success = runs[0].result {} else { XCTFail("run[0] expected success") }
        if case .success = runs[1].result {} else { XCTFail("run[1] expected success") }
    }

    func testMaxRunsCaps() async throws {
        let reader = LogReader(logPath: fixtureURL("sync_log_clean.txt"))
        let runs = try await reader.tail(maxRuns: 0)
        XCTAssertEqual(runs.count, 0)
    }

    func testMissingLogFileReturnsEmpty() async throws {
        let missing = fixtureURL("does_not_exist.log")
        let reader = LogReader(logPath: missing)
        let runs = try await reader.tail(maxRuns: 50)
        XCTAssertEqual(runs.count, 0)
    }
}
