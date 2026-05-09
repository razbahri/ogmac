import Foundation

enum RunnerError: Error {
    case binaryNotFound
    case nonZeroExit(code: Int32, stderr: String)
}
