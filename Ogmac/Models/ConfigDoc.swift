import Foundation

struct ConfigDoc: Codable, Equatable {
    var outlook: OutlookDoc
    var google: GoogleDoc
    var sync: SyncDoc
    var privacy: PrivacyDoc
    var failure: FailureDoc

    struct OutlookDoc: Codable, Equatable {
        var account: String
        var sourceCalendar: String
        var readMethod: String

        enum CodingKeys: String, CodingKey {
            case account
            case sourceCalendar = "source_calendar"
            case readMethod = "read_method"
        }

        init(account: String = "", sourceCalendar: String = "", readMethod: String = "apple_calendar") {
            self.account = account
            self.sourceCalendar = sourceCalendar
            self.readMethod = readMethod
        }
    }

    struct GoogleDoc: Codable, Equatable {
        var account: String
        var clientSecretPath: String
        var targetCalendarId: String

        enum CodingKeys: String, CodingKey {
            case account
            case clientSecretPath = "client_secret_path"
            case targetCalendarId = "target_calendar_id"
        }

        init(account: String = "", clientSecretPath: String = "", targetCalendarId: String = "") {
            self.account = account
            self.clientSecretPath = clientSecretPath
            self.targetCalendarId = targetCalendarId
        }
    }

    struct SyncDoc: Codable, Equatable {
        var windowPastDays: Int
        var windowFutureDays: Int

        enum CodingKeys: String, CodingKey {
            case windowPastDays = "window_past_days"
            case windowFutureDays = "window_future_days"
        }

        init(windowPastDays: Int = 1, windowFutureDays: Int = 30) {
            self.windowPastDays = windowPastDays
            self.windowFutureDays = windowFutureDays
        }

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            windowPastDays = try container.decodeIfPresent(Int.self, forKey: .windowPastDays) ?? 1
            windowFutureDays = try container.decodeIfPresent(Int.self, forKey: .windowFutureDays) ?? 30
        }
    }

    struct PrivacyDoc: Codable, Equatable {
        var copySubject: Bool
        var copyLocation: Bool
        var copyBody: Bool
        var copyAttendees: Bool

        enum CodingKeys: String, CodingKey {
            case copySubject = "copy_subject"
            case copyLocation = "copy_location"
            case copyBody = "copy_body"
            case copyAttendees = "copy_attendees"
        }

        init(
            copySubject: Bool = true,
            copyLocation: Bool = true,
            copyBody: Bool = true,
            copyAttendees: Bool = false
        ) {
            self.copySubject = copySubject
            self.copyLocation = copyLocation
            self.copyBody = copyBody
            self.copyAttendees = copyAttendees
        }
    }

    struct FailureDoc: Codable, Equatable {
        var maxConsecutiveBeforeDisable: Int
        var notifyOnFailure: Bool

        enum CodingKeys: String, CodingKey {
            case maxConsecutiveBeforeDisable = "max_consecutive_before_disable"
            case notifyOnFailure = "notify_on_failure"
        }

        init(maxConsecutiveBeforeDisable: Int = 5, notifyOnFailure: Bool = true) {
            self.maxConsecutiveBeforeDisable = maxConsecutiveBeforeDisable
            self.notifyOnFailure = notifyOnFailure
        }
    }

    static let empty = ConfigDoc(
        outlook: OutlookDoc(),
        google: GoogleDoc(),
        sync: SyncDoc(),
        privacy: PrivacyDoc(),
        failure: FailureDoc()
    )

    static let canonical = ConfigDoc(
        outlook: OutlookDoc(account: "you@example.com", sourceCalendar: "default", readMethod: "apple_calendar"),
        google: GoogleDoc(account: "you@gmail.com", clientSecretPath: "", targetCalendarId: "abc123@group.calendar.google.com"),
        sync: SyncDoc(windowPastDays: 1, windowFutureDays: 30),
        privacy: PrivacyDoc(copySubject: true, copyLocation: true, copyBody: true, copyAttendees: false),
        failure: FailureDoc(maxConsecutiveBeforeDisable: 5, notifyOnFailure: true)
    )
}
