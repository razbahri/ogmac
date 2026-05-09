import XCTest
@testable import Ogmac

final class PanelSummaryTests: XCTestCase {

    // Fixed reference point: 2026-05-08 14:17:45 UTC
    // minute=17, second=45 → next quarter-hour is :30 → 12m15s away → ceil = 13 min
    private let refDate = Date(timeIntervalSince1970: 1_746_710_265)

    // MARK: - nextSyncRelative

    // refDate: minute=17, second=45
    // next quarter-hour from :17:45 → :30:00 → 12m15s → ceil(12.25) = 13
    func test_nextSync_from_ref_date_is_13_min() {
        let result = PanelSummary.nextSyncRelative(from: refDate)
        XCTAssertEqual(result, "in 13 min")
    }

    // minute=0, second=0 → exactly on the quarter; next is :15 → 15 min
    func test_nextSync_exactly_on_quarter_hour() {
        // Build a date at exactly :00:00 of its minute
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        var comps = cal.dateComponents([.year, .month, .day, .hour], from: refDate)
        comps.minute = 0
        comps.second = 0
        let d = cal.date(from: comps)!
        let result = PanelSummary.nextSyncRelative(from: d)
        XCTAssertEqual(result, "in 15 min")
    }

    // minute=44, second=59 → next quarter-hour is :45 → 1 sec away → ceil(1/60) = 1
    func test_nextSync_1min_away() {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        var comps = cal.dateComponents([.year, .month, .day, .hour], from: refDate)
        comps.minute = 44
        comps.second = 59
        let d = cal.date(from: comps)!
        let result = PanelSummary.nextSyncRelative(from: d)
        XCTAssertEqual(result, "in 1 min")
    }

    // minute=45, second=30 → next is :60 (i.e., :00 next hour) → 14m30s → ceil = 15
    func test_nextSync_wraps_past_45() {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        var comps = cal.dateComponents([.year, .month, .day, .hour], from: refDate)
        comps.minute = 45
        comps.second = 30
        let d = cal.date(from: comps)!
        let result = PanelSummary.nextSyncRelative(from: d)
        XCTAssertEqual(result, "in 15 min")
    }

    // MARK: - lastChange

    func test_lastChange_picks_most_recent_meaningful_run() {
        // Slice is chronological (oldest first). Latest = run3 with no CRUD;
        // most-recent meaningful = run2 with create=1.
        let now = Date()
        let runs: [SyncRun] = [
            SyncRun(startedAt: now.addingTimeInterval(-600), result: .success,
                    durationMs: 100,
                    counts: ReconcileCounts(create: 0, update: 0, delete: 0, skip: 10)),
            SyncRun(startedAt: now.addingTimeInterval(-300), result: .success,
                    durationMs: 100,
                    counts: ReconcileCounts(create: 1, update: 0, delete: 0, skip: 10)),
            SyncRun(startedAt: now, result: .success,
                    durationMs: 100,
                    counts: ReconcileCounts(create: 0, update: 0, delete: 0, skip: 11)),
        ]
        guard case .meaningful(let counts, let at) = PanelSummary.lastChange(from: runs) else {
            return XCTFail("expected .meaningful")
        }
        XCTAssertEqual(counts.create, 1)
        XCTAssertEqual(at.timeIntervalSinceReferenceDate,
                       now.addingTimeInterval(-300).timeIntervalSinceReferenceDate,
                       accuracy: 1.0)
    }

    func test_lastChange_falls_back_to_no_changes() {
        let now = Date()
        let runs: [SyncRun] = [
            SyncRun(startedAt: now.addingTimeInterval(-300), result: .success,
                    durationMs: 100,
                    counts: ReconcileCounts(create: 0, update: 0, delete: 0, skip: 10)),
            SyncRun(startedAt: now, result: .success,
                    durationMs: 100,
                    counts: ReconcileCounts(create: 0, update: 0, delete: 0, skip: 11)),
        ]
        guard case .noChanges(let lastRunAt) = PanelSummary.lastChange(from: runs) else {
            return XCTFail("expected .noChanges")
        }
        XCTAssertEqual(lastRunAt.timeIntervalSinceReferenceDate,
                       now.timeIntervalSinceReferenceDate,
                       accuracy: 1.0)
    }

    func test_lastChange_skips_failures() {
        let runs: [SyncRun] = [
            SyncRun(startedAt: Date(), result: .failure(reason: "x"), durationMs: nil, counts: nil),
        ]
        XCTAssertNil(PanelSummary.lastChange(from: runs))
    }

    func test_lastChange_empty_array() {
        XCTAssertNil(PanelSummary.lastChange(from: []))
    }
}
