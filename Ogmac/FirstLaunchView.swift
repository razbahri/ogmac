import SwiftUI

struct FirstLaunchView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Welcome to ogmac")
                .font(.headline)

            Text("Before this app can show sync status, you need to install and configure the ogmac CLI.")
                .font(.caption)
                .foregroundStyle(.secondary)

            Text("Run in Terminal:")
                .font(.caption)

            HStack {
                Text("ogmac login")
                    .font(.system(.body, design: .monospaced))
                    .padding(6)
                    .background(Color.secondary.opacity(0.1))
                    .cornerRadius(4)

                Button("Copy") {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString("ogmac login", forType: .string)
                }
                .buttonStyle(.borderless)
            }

            Divider()

            Button("Quit ogmac") {
                NSApp.terminate(nil)
            }
        }
        .padding(16)
    }
}
