import SwiftUI

struct HistoryView: View {
    let reader: any LogReading
    var onDone: () -> Void = {}

    @State private var runs: [SyncRun] = []
    @State private var isLoading = true

    private static let dateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd HH:mm"
        return f
    }()

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Button {
                    onDone()
                } label: {
                    Image(systemName: "chevron.left")
                    Text("Back")
                }
                .buttonStyle(.borderless)
                Spacer()
                Text("Sync History")
                    .font(.headline)
                Spacer()
                // Spacer balance so the title centers
                Image(systemName: "chevron.left").opacity(0)
                Text("Back").opacity(0)
            }
            .padding(12)

            Divider()

            if isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity, minHeight: 200)
            } else if runs.isEmpty {
                Text("No meaningful sync runs recorded.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, minHeight: 200)
            } else {
                List(runs.indices, id: \.self) { index in
                    RunRowView(run: runs[index])
                }
                .listStyle(.plain)
                .frame(minHeight: 280, maxHeight: 320)
            }
        }
        .frame(minWidth: 320)
        .task {
            await loadRuns()
        }
    }

    private func loadRuns() async {
        isLoading = true
        do {
            let raw = try await reader.tail(maxRuns: 200)
            runs = raw.filter(Self.isMeaningful).reversed()
        } catch {
            runs = []
        }
        isLoading = false
    }

    /// A run is "meaningful" if it did real work OR landed on the 15-min
    /// schedule (:00/:15/:30/:45 within 90s tolerance). This filters out
    /// the network-change-triggered no-op syncs that fire every ~2 min
    /// because the launchd plist registers a NetworkChange LaunchEvent
    /// with ThrottleInterval=120.
    static func isMeaningful(_ run: SyncRun) -> Bool {
        if let c = run.counts, c.create + c.update + c.delete > 0 {
            return true
        }
        if case .failure = run.result {
            return true  // failures are always meaningful
        }
        let cal = Calendar(identifier: .gregorian)
        let comp = cal.dateComponents([.minute, .second], from: run.startedAt)
        let minute = comp.minute ?? 0
        let second = comp.second ?? 0
        let scheduledMinutes: Set<Int> = [0, 15, 30, 45]
        if scheduledMinutes.contains(minute) && second <= 90 { return true }
        if scheduledMinutes.contains((minute - 1 + 60) % 60) && second + 60 <= 90 { return true }
        return false
    }
}

// MARK: - Row

private struct RunRowView: View {
    let run: SyncRun

    private static let dateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd HH:mm"
        return f
    }()

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            resultIcon
                .frame(width: 16)

            VStack(alignment: .leading, spacing: 2) {
                HStack {
                    Text(Self.dateFormatter.string(from: run.startedAt))
                        .font(.subheadline)
                        .foregroundStyle(.primary)
                    Spacer()
                    Text(durationText)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                Text(detailText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }

    @ViewBuilder
    private var resultIcon: some View {
        switch run.result {
        case .success:
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(.green)
        case .failure(let reason) where reason == "incomplete":
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.yellow)
        case .failure:
            Image(systemName: "xmark.circle.fill")
                .foregroundStyle(.red)
        }
    }

    private var durationText: String {
        guard let ms = run.durationMs else { return "—" }
        let seconds = Double(ms) / 1000.0
        return String(format: "%.1fs", seconds)
    }

    private var detailText: String {
        switch run.result {
        case .success:
            if let c = run.counts {
                return "✓ \(c.create) created · \(c.update) updated · \(c.delete) deleted · \(c.skip) unchanged"
            }
            return "✓ completed"
        case .failure(let reason) where reason == "incomplete":
            return "⚠ incomplete"
        case .failure(let reason):
            return "✗ \(reason)"
        }
    }
}
