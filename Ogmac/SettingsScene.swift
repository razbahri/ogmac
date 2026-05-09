import SwiftUI

struct SettingsScene: Scene {
    @StateObject private var viewModel: SettingsViewModel

    init(viewModel: SettingsViewModel) {
        _viewModel = StateObject(wrappedValue: viewModel)
    }

    var body: some Scene {
        Settings {
            TabView {
                SettingsConnectionTab(viewModel: viewModel)
                    .tabItem { Label("Connection", systemImage: "link") }
                SettingsSyncTab(viewModel: viewModel)
                    .tabItem { Label("Sync", systemImage: "arrow.triangle.2.circlepath") }
                SettingsPrivacyTab(viewModel: viewModel)
                    .tabItem { Label("Privacy", systemImage: "lock") }
            }
            .frame(width: 480, height: 320)
            .padding(20)
            .onChange(of: viewModel.doc) { _, _ in
                viewModel.save()
            }
        }
    }
}
