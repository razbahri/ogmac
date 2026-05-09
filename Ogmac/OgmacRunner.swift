import Foundation

protocol OgmacCommanding {
    var binaryPath: URL? { get }
    func sync() async throws
    func pause() async throws
    func unpause() async throws
    func resume() async throws
    func reset(yes: Bool) async throws
}

class OgmacRunner: OgmacCommanding {

    private var _binaryPath: URL??
    private let fileManager: FileManager
    private let environment: [String: String]?
    private let venvFallback: URL

    init(
        fileManager: FileManager = .default,
        environment: [String: String]? = nil,
        venvFallback: URL? = nil
    ) {
        self.fileManager = fileManager
        self.environment = environment
        self.venvFallback = venvFallback ?? fileManager.homeDirectoryForCurrentUser
            .appendingPathComponent(".local/share/ogmac/venv/bin/ogmac")
    }

    var binaryPath: URL? {
        if let cached = _binaryPath {
            return cached
        }
        let resolved = resolveBinaryPath()
        _binaryPath = .some(resolved)
        return resolved
    }

    private func resolveBinaryPath() -> URL? {
        if let pathFromWhich = resolveViaWhich() {
            return pathFromWhich
        }
        if fileManager.fileExists(atPath: venvFallback.path) {
            return venvFallback
        }
        return nil
    }

    private func resolveViaWhich() -> URL? {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = ["which", "ogmac"]
        if let env = environment {
            process.environment = env
        }
        let outPipe = Pipe()
        process.standardOutput = outPipe
        process.standardError = Pipe()

        do {
            try process.run()
            process.waitUntilExit()
        } catch {
            return nil
        }

        guard process.terminationStatus == 0 else { return nil }
        let data = outPipe.fileHandleForReading.readDataToEndOfFile()
        guard let raw = String(data: data, encoding: .utf8) else { return nil }
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        return URL(fileURLWithPath: trimmed)
    }

    private func run(_ args: [String]) async throws {
        guard let binary = binaryPath else { throw RunnerError.binaryNotFound }

        return try await withCheckedThrowingContinuation { continuation in
            let process = Process()
            process.executableURL = binary
            process.arguments = args
            if let env = environment {
                process.environment = env
            }

            let stderrPipe = Pipe()
            process.standardError = stderrPipe
            let stdoutPipe = Pipe()
            process.standardOutput = stdoutPipe

            process.terminationHandler = { p in
                if p.terminationStatus != 0 {
                    let stderr = String(
                        data: stderrPipe.fileHandleForReading.readDataToEndOfFile(),
                        encoding: .utf8
                    ) ?? ""
                    continuation.resume(throwing: RunnerError.nonZeroExit(
                        code: p.terminationStatus,
                        stderr: stderr
                    ))
                } else {
                    continuation.resume()
                }
            }

            do {
                try process.run()
            } catch {
                continuation.resume(throwing: error)
            }
        }
    }

    func sync() async throws { try await run(["sync"]) }
    func pause() async throws { try await run(["pause"]) }
    func unpause() async throws { try await run(["unpause"]) }
    func resume() async throws { try await run(["resume"]) }
    func reset(yes: Bool) async throws {
        try await run(yes ? ["reset", "--yes"] : ["reset"])
    }
}
