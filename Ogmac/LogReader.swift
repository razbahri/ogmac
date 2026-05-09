import Foundation

protocol LogReading {
    func tail(maxRuns: Int) async throws -> [SyncRun]
}

struct LogReader: LogReading {
    let logPath: URL

    init(logPath: URL) {
        self.logPath = logPath
    }

    func tail(maxRuns: Int = 50) async throws -> [SyncRun] {
        let lines = collectLines()
        let runs = parse(lines: lines)
        return Array(runs.suffix(maxRuns))
    }

    private func collectLines() -> [String] {
        var allLines: [String] = []
        for i in stride(from: 10, through: 1, by: -1) {
            let rotated = logPath.appendingPathExtension("\(i)")
            if let content = try? String(contentsOf: rotated, encoding: .utf8) {
                allLines.append(contentsOf: content.components(separatedBy: "\n"))
            }
        }
        if let content = try? String(contentsOf: logPath, encoding: .utf8) {
            allLines.append(contentsOf: content.components(separatedBy: "\n"))
        }
        return allLines
    }

    private struct ParsedLine {
        let timestamp: Date
        let marker: String
        let rest: String
    }

    private func parseLine(_ raw: String, formatter: DateFormatter) -> ParsedLine? {
        // Production format: "2026-05-09T06:44:22Z INFO  ogmac.cli marker rest..."
        // (20-char ISO timestamp with literal Z, then space, then 5-char
        // padded levelname, then space, then logger name, then marker, then args.)
        guard raw.count >= 20 else { return nil }
        let prefix = String(raw.prefix(20))
        guard let ts = formatter.date(from: prefix) else { return nil }

        let levelTokens = [" INFO ", " ERROR", " WARNI", " DEBUG"]
        var afterLevel: String? = nil
        for token in levelTokens {
            if let r = raw.range(of: token) {
                // skip past the level token + any padding spaces before the logger name
                let after = raw[r.upperBound...]
                afterLevel = String(after.drop(while: { $0 == " " }))
                break
            }
        }
        guard let al = afterLevel else { return nil }

        // al = "ogmac.cli sync.start window=..."
        let parts = al.split(separator: " ", maxSplits: 1, omittingEmptySubsequences: true)
        guard parts.count >= 2 else { return nil }
        let markerAndRest = String(parts[1])
        let markerEnd = markerAndRest.firstIndex(of: " ") ?? markerAndRest.endIndex
        let marker = String(markerAndRest[..<markerEnd])
        let rest = markerEnd < markerAndRest.endIndex
            ? String(markerAndRest[markerAndRest.index(after: markerEnd)...])
            : ""
        return ParsedLine(timestamp: ts, marker: marker, rest: rest)
    }

    private func parseKV(_ s: String) -> [String: String] {
        var result: [String: String] = [:]
        for token in s.split(separator: " ") {
            let kv = token.split(separator: "=", maxSplits: 1)
            if kv.count == 2 {
                result[String(kv[0])] = String(kv[1])
            }
        }
        return result
    }

    private func parse(lines: [String]) -> [SyncRun] {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss'Z'"
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")

        var parsed: [ParsedLine] = []
        for line in lines {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            guard !trimmed.isEmpty else { continue }
            if let pl = parseLine(trimmed, formatter: formatter) {
                parsed.append(pl)
            }
        }

        var runs: [SyncRun] = []
        var i = 0

        while i < parsed.count {
            let pl = parsed[i]

            guard pl.marker == "sync.start" else {
                i += 1
                continue
            }

            let startedAt = pl.timestamp
            var counts: ReconcileCounts? = nil
            var result: SyncResult? = nil
            var durationMs: Int? = nil
            var j = i + 1

            while j < parsed.count {
                let cur = parsed[j]
                if cur.marker == "sync.start" {
                    result = .failure(reason: "incomplete")
                    break
                } else if cur.marker == "sync.success" {
                    let kv = parseKV(cur.rest)
                    durationMs = kv["duration_ms"].flatMap { Int($0) }
                    result = .success
                    j += 1
                    break
                } else if cur.marker == "sync.failure" {
                    let kv = parseKV(cur.rest)
                    result = .failure(reason: kv["type"] ?? "unknown")
                    j += 1
                    break
                } else if cur.marker == "reconcile" {
                    let kv = parseKV(cur.rest)
                    counts = ReconcileCounts(
                        create: kv["create"].flatMap { Int($0) } ?? 0,
                        update: kv["update"].flatMap { Int($0) } ?? 0,
                        delete: kv["delete"].flatMap { Int($0) } ?? 0,
                        skip: kv["skip"].flatMap { Int($0) } ?? 0
                    )
                }
                j += 1
            }

            runs.append(SyncRun(
                startedAt: startedAt,
                result: result ?? .failure(reason: "incomplete"),
                durationMs: durationMs,
                counts: counts
            ))
            i = j
        }

        return runs
    }
}
