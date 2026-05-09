import XCTest
@testable import Ogmac

final class StatusControllerTests: XCTestCase {

    private let now = Date(timeIntervalSince1970: 1_000_000)

    // MARK: - Helpers

    private func snap(
        lastSuccessAt: Date? = nil,
        consecutiveFailures: Int = 0,
        disabled: Bool = false,
        paused: Bool = false
    ) -> StateSnapshot {
        StateSnapshot(
            lastSuccessAt: lastSuccessAt,
            consecutiveFailures: consecutiveFailures,
            disabled: disabled,
            paused: paused,
            disableReason: nil
        )
    }

    private func resolve(_ snapshot: StateSnapshot, isSyncing: Bool = false) -> IconState {
        StatusController.resolve(snapshot: snapshot, isSyncing: isSyncing, now: now)
    }

    // MARK: - Priority 1: syncing beats everything

    func test_syncing_beats_paused() {
        let s = snap(paused: true)
        XCTAssertEqual(resolve(s, isSyncing: true), .syncing)
    }

    func test_syncing_beats_disabled() {
        let s = snap(disabled: true)
        XCTAssertEqual(resolve(s, isSyncing: true), .syncing)
    }

    func test_syncing_beats_error() {
        let s = snap(consecutiveFailures: 3)
        XCTAssertEqual(resolve(s, isSyncing: true), .syncing)
    }

    func test_syncing_beats_healthy() {
        let s = snap(lastSuccessAt: now.addingTimeInterval(-60))
        XCTAssertEqual(resolve(s, isSyncing: true), .syncing)
    }

    // MARK: - Priority 2: paused beats disabled/error/warning

    func test_paused_beats_disabled() {
        let s = snap(disabled: true, paused: true)
        XCTAssertEqual(resolve(s), .paused)
    }

    func test_paused_beats_error() {
        let s = snap(consecutiveFailures: 5, paused: true)
        XCTAssertEqual(resolve(s), .paused)
    }

    func test_paused_alone() {
        let s = snap(lastSuccessAt: now.addingTimeInterval(-60), paused: true)
        XCTAssertEqual(resolve(s), .paused)
    }

    // MARK: - Priority 3: autoDisabled

    func test_disabled_alone() {
        let s = snap(disabled: true)
        XCTAssertEqual(resolve(s), .autoDisabled)
    }

    func test_disabled_with_failures() {
        let s = snap(consecutiveFailures: 3, disabled: true)
        XCTAssertEqual(resolve(s), .autoDisabled)
    }

    // MARK: - Priority 4: needsLogin (deferred to v0.2 — always false for now)

    func test_needsLogin_deferred_returns_error_when_failures_present() {
        // needsLogin is never true in v0.1; ensure the slot doesn't swallow real errors
        let s = snap(consecutiveFailures: 1)
        XCTAssertEqual(resolve(s), .error)
    }

    // MARK: - Priority 5/6/7/8/9: error → warning → healthy

    func test_error_when_consecutive_failures_nonzero() {
        let s = snap(lastSuccessAt: now.addingTimeInterval(-60), consecutiveFailures: 1)
        XCTAssertEqual(resolve(s), .error)
    }

    func test_error_when_no_last_success() {
        let s = snap()
        XCTAssertEqual(resolve(s), .error)
    }

    func test_error_when_last_success_over_24h() {
        let t = now.addingTimeInterval(-(24 * 3600 + 1))
        let s = snap(lastSuccessAt: t)
        XCTAssertEqual(resolve(s), .error)
    }

    func test_error_exactly_at_24h_boundary() {
        let t = now.addingTimeInterval(-24 * 3600)
        let s = snap(lastSuccessAt: t)
        XCTAssertEqual(resolve(s), .error)
    }

    func test_warning_when_last_success_between_30min_and_24h() {
        let t = now.addingTimeInterval(-(30 * 60 + 1))
        let s = snap(lastSuccessAt: t)
        XCTAssertEqual(resolve(s), .warning)
    }

    func test_warning_just_inside_24h() {
        let t = now.addingTimeInterval(-(24 * 3600 - 1))
        let s = snap(lastSuccessAt: t)
        XCTAssertEqual(resolve(s), .warning)
    }

    func test_healthy_when_last_success_within_30min() {
        let t = now.addingTimeInterval(-(30 * 60 - 1))
        let s = snap(lastSuccessAt: t)
        XCTAssertEqual(resolve(s), .healthy)
    }

    func test_healthy_recent() {
        let t = now.addingTimeInterval(-120)
        let s = snap(lastSuccessAt: t)
        XCTAssertEqual(resolve(s), .healthy)
    }

    // MARK: - Exactly at 30-minute boundary

    func test_exactly_30min_is_warning() {
        let t = now.addingTimeInterval(-30 * 60)
        let s = snap(lastSuccessAt: t)
        XCTAssertEqual(resolve(s), .warning)
    }
}
