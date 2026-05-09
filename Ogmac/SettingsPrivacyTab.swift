import SwiftUI

struct SettingsPrivacyTab: View {
    @ObservedObject var viewModel: SettingsViewModel

    var body: some View {
        Form {
            Section("Fields to copy") {
                Toggle("Copy subject", isOn: $viewModel.doc.privacy.copySubject)
                Toggle("Copy location", isOn: $viewModel.doc.privacy.copyLocation)
                Toggle("Copy body", isOn: $viewModel.doc.privacy.copyBody)
                Toggle("Copy attendees", isOn: .constant(false))
                    .disabled(true)
                    .help("Attendee syncing is disabled by design. See README → Privacy.")
            }
        }
        .formStyle(.grouped)
    }
}
