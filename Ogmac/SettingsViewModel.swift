import Foundation

@MainActor
final class SettingsViewModel: ObservableObject {
    @Published var doc: ConfigDoc
    @Published var loadError: Error?
    @Published var saveError: Error?

    private let store: any ConfigStoring

    init(store: any ConfigStoring) {
        self.store = store
        self.doc = ConfigDoc.empty
        load()
    }

    func load() {
        do {
            doc = try store.load()
            loadError = nil
        } catch {
            loadError = error
        }
    }

    func save() {
        do {
            try store.save(doc)
            saveError = nil
        } catch {
            saveError = error
        }
    }
}
