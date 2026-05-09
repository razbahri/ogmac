import SwiftUI

struct SettingsSyncTab: View {
    @ObservedObject var viewModel: SettingsViewModel
    @StateObject private var launchAtLogin = LaunchAtLoginBinding()

    var body: some View {
        Form {
            Section("Sync window") {
                Stepper(
                    "Past: \(viewModel.doc.sync.windowPastDays) day(s)",
                    value: $viewModel.doc.sync.windowPastDays,
                    in: 1...30
                )
                Stepper(
                    "Future: \(viewModel.doc.sync.windowFutureDays) day(s)",
                    value: $viewModel.doc.sync.windowFutureDays,
                    in: 1...365
                )
            }

            Section("Schedule") {
                LabeledContent("Interval") {
                    Text("Every 15 minutes (configured in launchd plist)")
                        .foregroundStyle(.secondary)
                }
            }

            Section("Login") {
                Toggle("Launch at login", isOn: $launchAtLogin.isEnabled)
            }
        }
        .formStyle(.grouped)
    }
}

@MainActor
private final class LaunchAtLoginBinding: ObservableObject {
    private let service = LaunchAtLogin()

    var isEnabled: Bool {
        get { service.isEnabled }
        set {
            objectWillChange.send()
            service.isEnabled = newValue
        }
    }
}
