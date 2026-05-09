import XCTest
@testable import Ogmac

final class OgmacRunnerTests: XCTestCase {

    private func makeTempDir() throws -> URL {
        let dir = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    private func makeShim(
        in tempDir: URL,
        exitCode: Int32,
        stdout: String = "",
        stderr: String = ""
    ) throws -> URL {
        let shim = tempDir.appendingPathComponent("ogmac")
        var lines: [String] = ["#!/bin/sh"]
        if !stderr.isEmpty {
            lines.append("echo \"\(stderr)\" >&2")
        }
        if !stdout.isEmpty {
            lines.append("echo \"\(stdout)\"")
        }
        lines.append("exit \(exitCode)")
        let script = lines.joined(separator: "\n") + "\n"
        try script.write(to: shim, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o755],
            ofItemAtPath: shim.path
        )
        return shim
    }

    private func makeShimEchoArgs(in tempDir: URL, exitCode: Int32 = 0) throws -> URL {
        let shim = tempDir.appendingPathComponent("ogmac")
        let script = """
        #!/bin/sh
        echo "$@"
        exit \(exitCode)
        """
        try script.write(to: shim, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o755],
            ofItemAtPath: shim.path
        )
        return shim
    }

    private func envWithPath(_ dir: URL) -> [String: String] {
        var env = ProcessInfo.processInfo.environment
        let existing = env["PATH"] ?? "/usr/bin:/bin"
        env["PATH"] = "\(dir.path):\(existing)"
        return env
    }

    // MARK: - Case 1: sync() exit 0 → no throw

    func test_sync_exitZero_doesNotThrow() async throws {
        let dir = try makeTempDir()
        defer { try? FileManager.default.removeItem(at: dir) }
        try makeShim(in: dir, exitCode: 0)

        let runner = OgmacRunner(environment: envWithPath(dir))
        try await runner.sync()
    }

    // MARK: - Case 2: sync() exit 1 + stderr "boom" → throws nonZeroExit

    func test_sync_exitOne_throwsNonZeroExit() async throws {
        let dir = try makeTempDir()
        defer { try? FileManager.default.removeItem(at: dir) }
        try makeShim(in: dir, exitCode: 1, stderr: "boom")

        let runner = OgmacRunner(environment: envWithPath(dir))
        do {
            try await runner.sync()
            XCTFail("Expected throw")
        } catch RunnerError.nonZeroExit(let code, let stderr) {
            XCTAssertEqual(code, 1)
            XCTAssertTrue(stderr.contains("boom"), "stderr was: \(stderr)")
        }
    }

    // MARK: - Case 3: binaryPath nil → throws binaryNotFound

    func test_sync_noBinary_throwsBinaryNotFound() async throws {
        let emptyDir = try makeTempDir()
        defer { try? FileManager.default.removeItem(at: emptyDir) }

        var env = ProcessInfo.processInfo.environment
        env["PATH"] = emptyDir.path

        let noVenvRunner = OgmacRunner(
            fileManager: .default,
            environment: env,
            venvFallback: emptyDir.appendingPathComponent("nonexistent-ogmac")
        )

        do {
            try await noVenvRunner.sync()
            XCTFail("Expected throw")
        } catch RunnerError.binaryNotFound {
            // pass
        }
    }

    // MARK: - Case 4: PATH match wins over venv path

    func test_binaryPath_prefersPathOverVenv() async throws {
        let shimDir = try makeTempDir()
        defer { try? FileManager.default.removeItem(at: shimDir) }
        let shimURL = try makeShim(in: shimDir, exitCode: 0)

        let runner = OgmacRunner(environment: envWithPath(shimDir))
        let resolved = runner.binaryPath

        XCTAssertNotNil(resolved)
        XCTAssertEqual(resolved?.path, shimURL.path)
    }

    // MARK: - Case 5: reset(yes:) argument passing

    func test_reset_yes_true_passesYesFlag() async throws {
        let dir = try makeTempDir()
        defer { try? FileManager.default.removeItem(at: dir) }

        let outFile = dir.appendingPathComponent("args.txt")

        let shim = dir.appendingPathComponent("ogmac")
        let script = """
        #!/bin/sh
        echo "$@" > \(outFile.path)
        exit 0
        """
        try script.write(to: shim, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: shim.path)

        let runner = OgmacRunner(environment: envWithPath(dir))
        try await runner.reset(yes: true)

        let captured = try String(contentsOf: outFile, encoding: .utf8)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        XCTAssertEqual(captured, "reset --yes")
    }

    func test_reset_yes_false_omitsYesFlag() async throws {
        let dir = try makeTempDir()
        defer { try? FileManager.default.removeItem(at: dir) }

        let outFile = dir.appendingPathComponent("args.txt")

        let shim = dir.appendingPathComponent("ogmac")
        let script = """
        #!/bin/sh
        echo "$@" > \(outFile.path)
        exit 0
        """
        try script.write(to: shim, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: shim.path)

        let runner = OgmacRunner(environment: envWithPath(dir))
        try await runner.reset(yes: false)

        let captured = try String(contentsOf: outFile, encoding: .utf8)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        XCTAssertEqual(captured, "reset")
    }
}
