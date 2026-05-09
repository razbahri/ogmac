import XCTest
@testable import Ogmac

private enum SomeError: Error {
    case fail
}

private final class MockConfigStore: ConfigStoring {
    private let loaded: ConfigDoc
    private let saveError: Error?
    private(set) var savedDoc: ConfigDoc?

    init(loaded: ConfigDoc = .empty, saveError: Error? = nil) {
        self.loaded = loaded
        self.saveError = saveError
    }

    func load() throws -> ConfigDoc {
        return loaded
    }

    func save(_ doc: ConfigDoc) throws {
        if let error = saveError {
            throw error
        }
        savedDoc = doc
    }
}

@MainActor
final class SettingsViewModelTests: XCTestCase {
    func testLoadPopulatesDoc() throws {
        let store = MockConfigStore(loaded: ConfigDoc.canonical)
        let vm = SettingsViewModel(store: store)
        XCTAssertEqual(vm.doc, ConfigDoc.canonical)
    }

    func testLoadErrorIsExposedWhenStoreFails() throws {
        final class FailingStore: ConfigStoring {
            func load() throws -> ConfigDoc { throw SomeError.fail }
            func save(_ doc: ConfigDoc) throws {}
        }
        let vm = SettingsViewModel(store: FailingStore())
        XCTAssertNotNil(vm.loadError)
        XCTAssertEqual(vm.doc, ConfigDoc.empty)
    }

    func testSavePassesDocToStore() throws {
        let store = MockConfigStore(loaded: .empty)
        let vm = SettingsViewModel(store: store)
        vm.doc.outlook.account = "x@y.com"
        vm.save()
        XCTAssertEqual(store.savedDoc?.outlook.account, "x@y.com")
    }

    func testSaveErrorIsExposed() throws {
        let store = MockConfigStore(saveError: SomeError.fail)
        let vm = SettingsViewModel(store: store)
        vm.save()
        XCTAssertNotNil(vm.saveError)
    }

    func testSaveErrorClearedOnSuccess() throws {
        let store = MockConfigStore(loaded: .empty)
        let vm = SettingsViewModel(store: store)
        vm.saveError = SomeError.fail
        vm.save()
        XCTAssertNil(vm.saveError)
    }
}
