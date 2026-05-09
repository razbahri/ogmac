import Foundation

struct ReconcileCounts: Equatable {
    let create: Int
    let update: Int
    let delete: Int
    let skip: Int
}

enum SyncResult: Equatable {
    case success
    case failure(reason: String)
}

struct SyncRun {
    let startedAt: Date
    let result: SyncResult
    let durationMs: Int?
    let counts: ReconcileCounts?
}
