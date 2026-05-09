import Foundation
import Yams

protocol ConfigStoring {
    func load() throws -> ConfigDoc
    func save(_ doc: ConfigDoc) throws
}

enum ConfigStoreError: Error {
    case fileNotFound
    case encodingFailed(String)
}

struct ConfigStore: ConfigStoring {
    let configPath: URL

    init(configPath: URL) {
        self.configPath = configPath
    }

    func load() throws -> ConfigDoc {
        guard FileManager.default.fileExists(atPath: configPath.path) else {
            throw ConfigStoreError.fileNotFound
        }
        let data = try Data(contentsOf: configPath)
        let decoder = YAMLDecoder()
        return try decoder.decode(ConfigDoc.self, from: data)
    }

    func save(_ doc: ConfigDoc) throws {
        let encoder = YAMLEncoder()
        let yaml: String
        do {
            yaml = try encoder.encode(doc)
        } catch {
            throw ConfigStoreError.encodingFailed(error.localizedDescription)
        }
        if !FileManager.default.fileExists(atPath: configPath.path) {
            let dir = configPath.deletingLastPathComponent()
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            try yaml.write(to: configPath, atomically: true, encoding: .utf8)
            return
        }
        let tmp = configPath.appendingPathExtension("tmp")
        try yaml.write(to: tmp, atomically: true, encoding: .utf8)
        _ = try FileManager.default.replaceItemAt(configPath, withItemAt: tmp)
    }
}
