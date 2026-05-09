import SwiftUI

enum IconState: String, Equatable {
    case healthy
    case warning
    case error
    case autoDisabled
    case paused
    case syncing
    case needsLogin

    var systemImageName: String {
        switch self {
        case .healthy:      return "app.fill"
        case .warning:      return "app.badge"
        case .error:        return "app.badge.fill"
        case .autoDisabled: return "app.badge.fill"  // same glyph; tint differs
        case .paused:       return "app"
        case .syncing:      return "arrow.triangle.2.circlepath"
        case .needsLogin:   return "app.dashed"
        }
    }

    var tint: Color {
        switch self {
        case .healthy:                  return .accentColor
        case .warning:                  return .yellow
        case .error, .autoDisabled:     return .red
        case .paused, .needsLogin:      return .secondary
        case .syncing:                  return .accentColor
        }
    }
}
