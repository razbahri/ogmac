import XCTest
@testable import Ogmac

final class LaunchAtLoginTests: XCTestCase {
    @MainActor
    func testGetterDoesNotCrash() {
        let l = LaunchAtLogin()
        _ = l.isEnabled
    }
}
