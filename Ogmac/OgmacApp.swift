import SwiftUI

@main
struct OgmacApp: App {
    @StateObject private var deps = AppDeps()

    var body: some Scene {
        MenuBarExtra {
            if deps.firstLaunch {
                FirstLaunchView()
                    .frame(minWidth: 280)
            } else {
                MenuPanelView(
                    controller: deps.statusController,
                    runner: deps.runner,
                    logReader: deps.logReader
                )
                .onAppear { deps.statusController.refreshNow() }
            }
        } label: {
            MenuBarLabel(controller: deps.statusController)
        }
        .menuBarExtraStyle(.window)

        SettingsScene(viewModel: deps.settingsViewModel)
    }
}

private struct MenuBarLabel: View {
    @ObservedObject var controller: StatusController

    var body: some View {
        Image(systemName: controller.icon.systemImageName)
            .onAppear { controller.startMonitoring() }
    }
}
