import Foundation

struct PanelSummary {
    let nextSyncRelative: String
    let lastChange: LastChange?

    enum LastChange: Equatable {
        case meaningful(counts: ReconcileCounts, at: Date)
        case noChanges(lastRunAt: Date)
    }

    static let empty = PanelSummary(
        nextSyncRelative: "—",
        lastChange: nil
    )

    static func nextSyncRelative(from now: Date) -> String {
        let calendar = Calendar.current
        let components = calendar.dateComponents([.minute, .second], from: now)
        let currentMinute = components.minute ?? 0
        let currentSecond = components.second ?? 0

        let gridMinutes = [0, 15, 30, 45]
        let nextMinute: Int
        if let found = gridMinutes.first(where: { $0 > currentMinute }) {
            nextMinute = found
        } else {
            nextMinute = 60
        }

        let minutesUntil: Int
        if nextMinute == 60 {
            minutesUntil = 60 - currentMinute
        } else {
            minutesUntil = nextMinute - currentMinute
        }

        let secondsUntil = minutesUntil * 60 - currentSecond
        let displayMinutes = max(1, Int(ceil(Double(secondsUntil) / 60.0)))
        return "in \(displayMinutes) min"
    }

    /// Pick the most recent successful run with any CRUD activity. If no
    /// recent run has activity, fall back to the most recent successful run
    /// (so the panel can show "Up to date as of X min ago"). Returns nil if
    /// no successful run is in the slice.
    static func lastChange(from recentRuns: [SyncRun]) -> LastChange? {
        let successes = recentRuns.compactMap { run -> (SyncRun, ReconcileCounts)? in
            guard case .success = run.result else { return nil }
            let counts = run.counts ?? ReconcileCounts(create: 0, update: 0, delete: 0, skip: 0)
            return (run, counts)
        }
        guard !successes.isEmpty else { return nil }

        if let meaningful = successes.reversed().first(where: { _, c in
            c.create + c.update + c.delete > 0
        }) {
            return .meaningful(counts: meaningful.1, at: meaningful.0.startedAt)
        }

        let latest = successes.last!
        return .noChanges(lastRunAt: latest.0.startedAt)
    }
}
