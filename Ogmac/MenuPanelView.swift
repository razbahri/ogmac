import SwiftUI

struct MenuPanelView: View {
    @ObservedObject var controller: StatusController
    let runner: OgmacCommanding
    let logReader: any LogReading

    @State private var showingHistory = false
    @Environment(\.openSettings) private var openSettings

    var body: some View {
        if showingHistory {
            HistoryView(reader: logReader, onDone: { showingHistory = false })
        } else {
            mainPanel
        }
    }

    private var mainPanel: some View {
        VStack(alignment: .leading, spacing: 0) {
            headerSection
            Divider().padding(.vertical, 8)
            backendSection
            Divider().padding(.vertical, 8)
            lastRunSection
            Divider().padding(.vertical, 8)
            syncButton
            Divider().padding(.vertical, 8)
            menuItems
        }
        .padding(12)
        .frame(minWidth: 260)
    }

    // MARK: - Header

    private var headerSection: some View {
        HStack(alignment: .top) {
            Text("ogmac")
                .font(.headline)
            Spacer()
            HStack(spacing: 4) {
                Image(systemName: controller.icon.systemImageName)
                    .foregroundStyle(controller.icon.tint)
                Text(controller.icon.label)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.bottom, 4)
    }

    // MARK: - Sync timing

    private var timingSection: some View {
        HStack {
            Text("Next sync")
                .foregroundStyle(.secondary)
            Text("·")
                .foregroundStyle(.secondary)
            Text(controller.summary.nextSyncRelative)
        }
        .font(.subheadline)
    }

    // MARK: - Timing

    private var backendSection: some View {
        timingSection
    }

    // MARK: - Last run counts

    private var lastRunSection: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("Last change")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            switch controller.summary.lastChange {
            case .meaningful(let counts, let at):
                Text("✓ \(counts.create) created · \(counts.update) updated · \(counts.delete) del")
                    .font(.subheadline)
                    .padding(.leading, 4)
                Text(MenuPanelView.relativeTimeFormatter.localizedString(for: at, relativeTo: .now))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.leading, 4)
            case .noChanges(let lastRunAt):
                Text("Up to date")
                    .font(.subheadline)
                    .padding(.leading, 4)
                Text("checked \(MenuPanelView.relativeTimeFormatter.localizedString(for: lastRunAt, relativeTo: .now))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.leading, 4)
            case nil:
                Text("No successful run recorded")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .padding(.leading, 4)
            }
        }
    }

    private static let relativeTimeFormatter: RelativeDateTimeFormatter = {
        let f = RelativeDateTimeFormatter()
        f.unitsStyle = .full
        return f
    }()

    // MARK: - Sync button

    private var syncButton: some View {
        Button {
            Task { await controller.triggerSync() }
        } label: {
            HStack {
                Spacer()
                if controller.isSyncing {
                    ProgressView().controlSize(.small)
                    Text("Syncing…")
                } else {
                    Text("Sync now")
                }
                Spacer()
            }
        }
        .buttonStyle(.bordered)
        .controlSize(.regular)
        .disabled(controller.isSyncing)
    }

    // MARK: - Menu items

    private var menuItems: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button("Settings…") {
                NSApp.activate(ignoringOtherApps: true)
                openSettings()
            }
            .buttonStyle(.plain)
            .padding(.vertical, 4)

            Button("History…") {
                showingHistory = true
            }
            .buttonStyle(.plain)
            .padding(.vertical, 4)

            pauseResumeButton
                .padding(.vertical, 4)

            Divider().padding(.vertical, 4)

            Button("Quit ogmac") {
                NSApp.terminate(nil)
            }
            .buttonStyle(.plain)
            .padding(.vertical, 4)
        }
    }

    @ViewBuilder
    private var pauseResumeButton: some View {
        if controller.icon == .paused {
            Button("Resume") {
                Task { try? await runner.unpause() }
            }
            .buttonStyle(.plain)
        } else if controller.icon == .autoDisabled {
            Button("Resume") {
                Task { try? await runner.resume() }
            }
            .buttonStyle(.plain)
        } else {
            Button("Pause") {
                Task { try? await runner.pause() }
            }
            .buttonStyle(.plain)
        }
    }
}

// MARK: - IconState display label

private extension IconState {
    var label: String {
        switch self {
        case .healthy:      return "Healthy"
        case .warning:      return "Warning"
        case .error:        return "Error"
        case .autoDisabled: return "Auto-disabled"
        case .paused:       return "Paused"
        case .syncing:      return "Syncing"
        case .needsLogin:   return "Needs login"
        }
    }
}
