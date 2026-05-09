import Foundation

@MainActor
final class AppDeps: ObservableObject {
    let stateReader: any StateReading
    let logReader: any LogReading
    let configStore: any ConfigStoring
    let runner: any OgmacCommanding
    let settingsViewModel: SettingsViewModel
    let statusController: StatusController
    let launchAtLogin: LaunchAtLogin
    @Published var firstLaunch: Bool

    convenience init() {
        let home = FileManager.default.homeDirectoryForCurrentUser
        let dbPath = home
            .appendingPathComponent("Library/Application Support/ogmac/state.db")
            .path
        let logPath = home
            .appendingPathComponent("Library/Logs/ogmac/sync.log")
        let configPath = home
            .appendingPathComponent(".config/ogmac/config.yaml")

        self.init(
            runnerOverride: OgmacRunner(),
            configStoreOverride: ConfigStore(configPath: configPath),
            stateReaderOverride: StateReader(dbPath: dbPath),
            logReaderOverride: LogReader(logPath: logPath)
        )
    }

    init(
        runnerOverride: any OgmacCommanding,
        configStoreOverride: any ConfigStoring,
        stateReaderOverride: (any StateReading)? = nil,
        logReaderOverride: (any LogReading)? = nil
    ) {
        let home = FileManager.default.homeDirectoryForCurrentUser
        let dbPath = home
            .appendingPathComponent("Library/Application Support/ogmac/state.db")
            .path
        let logPath = home
            .appendingPathComponent("Library/Logs/ogmac/sync.log")

        let stateReader = stateReaderOverride ?? StateReader(dbPath: dbPath)
        let logReader = logReaderOverride ?? LogReader(
            logPath: home.appendingPathComponent("Library/Logs/ogmac/sync.log")
        )
        _ = logPath

        self.stateReader = stateReader
        self.logReader = logReader
        self.configStore = configStoreOverride
        self.runner = runnerOverride
        self.launchAtLogin = LaunchAtLogin()

        self.settingsViewModel = SettingsViewModel(store: configStoreOverride)

        let cliMissing = runnerOverride.binaryPath == nil
        let configMissing = (try? configStoreOverride.load()) == nil
        self.firstLaunch = cliMissing || configMissing

        self.statusController = StatusController(
            stateReader: stateReader,
            logReader: logReader,
            runner: runnerOverride,
            stateDbPath: dbPath
        )
    }
}
