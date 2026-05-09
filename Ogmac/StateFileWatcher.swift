import Foundation

/// Watches `state.db` for write/delete/rename events and invokes `onChange`
/// each time the daemon updates the file. Uses GCD's
/// `DispatchSourceFileSystemObject` so wake-ups happen only on real activity
/// — no periodic polling.
///
/// Debounces rapid bursts (some writes happen as multiple page flushes) by
/// ignoring events within 200ms of a previous fire.
final class StateFileWatcher {
    private let path: String
    private let onChange: () async -> Void
    private var source: DispatchSourceFileSystemObject?
    private var fd: Int32 = -1
    private var lastFiredAt: Date = .distantPast
    private let queue = DispatchQueue(label: "com.ogmac.state-watcher")

    init(path: String, onChange: @escaping () async -> Void) {
        self.path = path
        self.onChange = onChange
    }

    deinit { source?.cancel() }

    /// Start watching. If the file doesn't exist yet, returns false; caller
    /// can fall back to a timer or retry once the file appears.
    @discardableResult
    func start() -> Bool {
        stop()
        let opened = open(path, O_EVTONLY)
        guard opened >= 0 else {
            DebugLog.write("StateFileWatcher.open failed path=\(path) errno=\(errno)")
            return false
        }
        fd = opened

        let s = DispatchSource.makeFileSystemObjectSource(
            fileDescriptor: fd,
            eventMask: [.write, .delete, .rename, .extend],
            queue: queue
        )

        s.setEventHandler { [weak self] in
            guard let self else { return }
            let now = Date()
            if now.timeIntervalSince(self.lastFiredAt) < 0.2 { return }
            self.lastFiredAt = now
            DebugLog.write("StateFileWatcher event")
            Task { await self.onChange() }
        }

        s.setCancelHandler { [fd] in
            if fd >= 0 { close(fd) }
        }

        source = s
        s.resume()
        DebugLog.write("StateFileWatcher started fd=\(fd) path=\(path)")
        return true
    }

    func stop() {
        source?.cancel()
        source = nil
        fd = -1
    }
}
