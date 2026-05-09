import Foundation
import SQLite3

protocol StateReading {
    func snapshot() async throws -> StateSnapshot
}

enum StateReaderError: Error {
    case openFailed(code: Int32, message: String)
    case prepareFailed(code: Int32, message: String)
}

struct StateReader: StateReading {
    let dbPath: String

    init(dbPath: String) {
        self.dbPath = dbPath
    }

    func snapshot() async throws -> StateSnapshot {
        DebugLog.write("StateReader.snapshot start path=\(dbPath)")
        // The daemon's state.db has journal_mode=WAL set in its metadata.
        // Even SQLITE_OPEN_READONLY tries to coordinate with -wal/-shm
        // sidecars (which may not exist in our process's view), failing
        // with SQLITE_CANTOPEN on prepare. The URI ?immutable=1 flag
        // tells SQLite to treat the file as a frozen snapshot and skip
        // all journal coordination. We get a snapshot at open time;
        // since we open a fresh connection per snapshot() call, polling
        // sees fresh data.
        let encoded = dbPath
            .addingPercentEncoding(withAllowedCharacters: .urlPathAllowed)
            ?? dbPath
        let uri = "file:\(encoded)?immutable=1"
        var db: OpaquePointer?
        let flags = SQLITE_OPEN_READONLY | SQLITE_OPEN_URI | SQLITE_OPEN_NOMUTEX
        let rc = sqlite3_open_v2(uri, &db, flags, nil)
        guard rc == SQLITE_OK, let db else {
            let msg = db.flatMap { String(cString: sqlite3_errmsg($0)) } ?? "unknown"
            DebugLog.write("StateReader.open FAILED rc=\(rc) msg=\(msg) uri=\(uri)")
            sqlite3_close(db)
            throw StateReaderError.openFailed(code: rc, message: msg)
        }
        defer { sqlite3_close(db) }
        DebugLog.write("StateReader.open ok")

        func value(for key: String) -> String? {
            // Inline the key as a SQL literal — the keys are static internal
            // strings, not user input, so injection isn't a concern. Avoids
            // a Swift/sqlite3_bind_text ABI issue where SQLITE_TRANSIENT
            // (a function pointer constant -1) can't be expressed cleanly.
            var stmt: OpaquePointer?
            let escaped = key.replacingOccurrences(of: "'", with: "''")
            let sql = "SELECT value FROM run_state WHERE key = '\(escaped)'"
            let prc = sqlite3_prepare_v2(db, sql, -1, &stmt, nil)
            guard prc == SQLITE_OK else {
                DebugLog.write("StateReader.prepare FAILED key=\(key) rc=\(prc) msg=\(String(cString: sqlite3_errmsg(db)))")
                return nil
            }
            defer { sqlite3_finalize(stmt) }
            let src = sqlite3_step(stmt)
            guard src == SQLITE_ROW else {
                DebugLog.write("StateReader.step no-row key=\(key) rc=\(src)")
                return nil
            }
            guard let cstr = sqlite3_column_text(stmt, 0) else {
                DebugLog.write("StateReader.column null key=\(key)")
                return nil
            }
            let val = String(cString: cstr)
            DebugLog.write("StateReader.value key=\(key) val=\(val)")
            return val
        }

        let lastSuccessRaw = value(for: "last_success_at")
        let lastSuccessAt: Date?
        if let raw = lastSuccessRaw {
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime]
            lastSuccessAt = formatter.date(from: raw)
        } else {
            lastSuccessAt = nil
        }

        let consecutiveFailures = value(for: "consecutive_failures").flatMap { Int($0) } ?? 0
        let disabled = value(for: "disabled") == "1"
        let paused = value(for: "paused") == "1"
        let disableReason = value(for: "disable_reason")

        return StateSnapshot(
            lastSuccessAt: lastSuccessAt,
            consecutiveFailures: consecutiveFailures,
            disabled: disabled,
            paused: paused,
            disableReason: disableReason
        )
    }
}
