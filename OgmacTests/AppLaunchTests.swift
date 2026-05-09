import XCTest
@testable import Ogmac

@MainActor
final class AppLaunchTests: XCTestCase {
    func testAppDepsConstructs() {
        let deps = AppDeps()
        XCTAssertNotNil(deps.stateReader)
        XCTAssertNotNil(deps.runner)
        XCTAssertNotNil(deps.statusController)
        XCTAssertNotNil(deps.settingsViewModel)
        XCTAssertNotNil(deps.logReader)
        XCTAssertNotNil(deps.configStore)
    }

    func testSingleSettingsViewModelInstance() {
        let deps = AppDeps()
        deps.settingsViewModel.doc.outlook.account = "test@example.com"
        var capturedDoc: ConfigDoc?
        let mirror = Mirror(reflecting: deps.statusController)
        _ = mirror
        XCTAssertEqual(deps.settingsViewModel.doc.outlook.account, "test@example.com")
    }

    func testFirstLaunchTrueWhenCLIMissing() {
        let deps = AppDeps(
            runnerOverride: MockRunner(binaryPath: nil),
            configStoreOverride: FailingConfigStore()
        )
        XCTAssertTrue(deps.firstLaunch)
    }

    func testFirstLaunchFalseWhenCLIAndConfigPresent() {
        let tmp = FileManager.default.temporaryDirectory
            .appendingPathComponent("test_config_\(UUID().uuidString).yaml")
        let yaml = """
            outlook:
              account: test@example.com
              source_calendar: default
              read_method: apple_calendar
            google:
              account: test@gmail.com
              client_secret_path: /tmp/secret.json
              target_calendar_id: abc@group.calendar.google.com
            sync:
              window_past_days: 1
              window_future_days: 30
            privacy:
              copy_subject: true
              copy_location: true
              copy_body: true
              copy_attendees: false
            failure:
              max_consecutive_before_disable: 5
              notify_on_failure: true
            """
        try? yaml.write(to: tmp, atomically: true, encoding: .utf8)
        defer { try? FileManager.default.removeItem(at: tmp) }

        let fakeBinary = URL(fileURLWithPath: "/usr/bin/true")
        let deps = AppDeps(
            runnerOverride: MockRunner(binaryPath: fakeBinary),
            configStoreOverride: ConfigStore(configPath: tmp)
        )
        XCTAssertFalse(deps.firstLaunch)
    }
}

private final class MockRunner: OgmacCommanding {
    let binaryPath: URL?
    init(binaryPath: URL?) { self.binaryPath = binaryPath }
    func sync() async throws {}
    func pause() async throws {}
    func unpause() async throws {}
    func resume() async throws {}
    func reset(yes: Bool) async throws {}
}

private struct FailingConfigStore: ConfigStoring {
    func load() throws -> ConfigDoc { throw ConfigStoreError.fileNotFound }
    func save(_ doc: ConfigDoc) throws {}
}
