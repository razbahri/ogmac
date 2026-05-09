import SwiftUI
import AppKit

struct SettingsConnectionTab: View {
    @ObservedObject var viewModel: SettingsViewModel

    var body: some View {
        Form {
            Section("Outlook") {
                Picker("Read backend", selection: $viewModel.doc.outlook.readMethod) {
                    Text("Apple Calendar").tag("apple_calendar")
                    Text("Microsoft Graph").tag("microsoft_graph")
                }
                .pickerStyle(.segmented)

                if viewModel.doc.outlook.readMethod == "microsoft_graph" {
                    Text("You may need to run `ogmac login microsoft` in Terminal.")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }

                TextField("Account", text: $viewModel.doc.outlook.account)
                    .textFieldStyle(.roundedBorder)

                TextField("Source calendar", text: $viewModel.doc.outlook.sourceCalendar)
                    .textFieldStyle(.roundedBorder)
            }

            Section("Google") {
                TextField("Account", text: $viewModel.doc.google.account)
                    .textFieldStyle(.roundedBorder)

                HStack {
                    Text("Client secret")
                        .frame(width: 120, alignment: .leading)
                    Text(viewModel.doc.google.clientSecretPath.isEmpty
                         ? "Not set"
                         : viewModel.doc.google.clientSecretPath)
                        .foregroundStyle(viewModel.doc.google.clientSecretPath.isEmpty ? .secondary : .primary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Spacer()
                    Button("Choose…") {
                        chooseClientSecretFile()
                    }
                }

                TextField("Target calendar ID", text: $viewModel.doc.google.targetCalendarId)
                    .textFieldStyle(.roundedBorder)
            }
        }
        .formStyle(.grouped)
    }

    private func chooseClientSecretFile() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.init(filenameExtension: "json")!]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        if panel.runModal() == .OK, let url = panel.url {
            viewModel.doc.google.clientSecretPath = url.path
        }
    }
}
