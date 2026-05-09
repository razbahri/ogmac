import Foundation

struct StateSnapshot {
    let lastSuccessAt: Date?
    let consecutiveFailures: Int
    let disabled: Bool
    let paused: Bool
    let disableReason: String?
}
