import Foundation
import SwiftUI

@MainActor
final class StatusController: ObservableObject {

    @Published var icon: IconState = .healthy
    @Published var summary: PanelSummary = .empty
    @Published private(set) var isSyncing: Bool = false

    private let stateReader: StateReading
    private let logReader: LogReading
    private let runner: OgmacCommanding
    private let stateDbPath: String

    private var watcher: StateFileWatcher?
    private var fallbackTimerTask: Task<Void, Never>?

    init(
        stateReader: StateReading,
        logReader: LogReading,
        runner: OgmacCommanding,
        stateDbPath: String
    ) {
        self.stateReader = stateReader
        self.logReader = logReader
        self.runner = runner
        self.stateDbPath = stateDbPath
    }

    /// Start monitoring. Performs an immediate refresh, then installs a
    /// file-system watcher on state.db so subsequent refreshes fire only
    /// when the daemon actually writes (sync completion, pause toggle,
    /// failure counter update). No periodic polling.
    func startMonitoring() {
        Task { await self.refresh() }
        startWatcher()
    }

    /// Stop the watcher. Use when the app is being torn down.
    func stopMonitoring() {
        watcher?.stop()
        watcher = nil
        fallbackTimerTask?.cancel()
        fallbackTimerTask = nil
    }

    /// Trigger an on-demand refresh. Call from panel onAppear so the user
    /// always sees fresh data when they click the menu bar icon.
    func refreshNow() {
        Task { await self.refresh() }
    }

    private func startWatcher() {
        watcher?.stop()
        let w = StateFileWatcher(path: stateDbPath) { [weak self] in
            await self?.refresh()
        }
        if w.start() {
            watcher = w
            fallbackTimerTask?.cancel()
            fallbackTimerTask = nil
            return
        }
        // File doesn't exist yet (e.g., first run before any sync). Fall
        // back to a slow timer that retries the watcher every 30s and
        // refreshes opportunistically.
        DebugLog.write("StatusController fallback timer (state.db not yet present)")
        fallbackTimerTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(30))
                guard let self else { return }
                await self.refresh()
                if FileManager.default.fileExists(atPath: self.stateDbPath) {
                    self.startWatcher()
                    return
                }
            }
        }
    }

    /// User clicked Sync now. Awaits the underlying `ogmac sync` Process,
    /// which can take >1 min for a real sync. The Process exits only after
    /// state.db is fully written, so we're guaranteed fresh data when we
    /// refresh on completion. Errors are surfaced via the icon on refresh.
    func triggerSync() async {
        isSyncing = true
        icon = Self.resolve(snapshot: lastSnapshot ?? Self.emptySnapshot, isSyncing: true, now: .now)
        defer {
            isSyncing = false
            Task { await self.refresh() }
        }
        do {
            try await runner.sync()
        } catch {
            DebugLog.write("triggerSync error: \(error)")
        }
    }

    private var lastSnapshot: StateSnapshot?

    private static let emptySnapshot = StateSnapshot(
        lastSuccessAt: nil,
        consecutiveFailures: 0,
        disabled: false,
        paused: false,
        disableReason: nil
    )

    private func refresh() async {
        DebugLog.write("refresh start")
        var snap: StateSnapshot? = nil
        var runs: [SyncRun] = []
        var stateErr: Error? = nil
        var logErr: Error? = nil

        do { snap = try await stateReader.snapshot() }
        catch { stateErr = error; DebugLog.write("refresh stateReader error: \(error)") }

        do { runs = try await logReader.tail(maxRuns: 50) }
        catch { logErr = error; DebugLog.write("refresh logReader error: \(error)") }

        DebugLog.write("refresh state=\(snap != nil ? "ok" : "nil") runs=\(runs.count) lastSuccess=\(snap?.lastSuccessAt.map { ISO8601DateFormatter().string(from: $0) } ?? "nil")")

        let effectiveSnap = snap ?? Self.emptySnapshot
        lastSnapshot = snap

        if stateErr != nil && logErr != nil {
            icon = .error
        } else {
            icon = Self.resolve(snapshot: effectiveSnap, isSyncing: isSyncing, now: .now)
        }

        summary = Self.makeSummary(recent: runs, now: .now)
        DebugLog.write("refresh end icon=\(icon.rawValue)")
    }

    // MARK: - Pure resolution function (tested)

    nonisolated static func resolve(snapshot: StateSnapshot, isSyncing: Bool, now: Date) -> IconState {
        if isSyncing { return .syncing }
        if snapshot.paused { return .paused }
        if snapshot.disabled { return .autoDisabled }

        // needsLogin: deferred to v0.2 (requires parsing log for TokenRefreshError)
        // Always false for v0.1.

        if snapshot.consecutiveFailures > 0 { return .error }
        guard let lastSuccess = snapshot.lastSuccessAt else { return .error }
        let age = now.timeIntervalSince(lastSuccess)
        if age >= 24 * 3600 { return .error }
        if age >= 30 * 60 { return .warning }
        return .healthy
    }

    // MARK: - PanelSummary construction

    static func makeSummary(recent: [SyncRun], now: Date) -> PanelSummary {
        PanelSummary(
            nextSyncRelative: PanelSummary.nextSyncRelative(from: now),
            lastChange: PanelSummary.lastChange(from: recent)
        )
    }
}
