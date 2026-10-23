import SwiftUI
import WidgetKit

// Preview the shared widget views inside the app target. macOS doesn't support
// WidgetKit-hosted Canvas previews in the widget extension itself.
#if DEBUG
@MainActor private func widgetPreviewEntry() -> CapacityEntry {
    let now = Vienna.calendar.date(bySettingHour: 15, minute: 16, second: 0, of: .now)!
    return CapacityEntry(date: now, gym: Gym.all[0], snapshot: DemoData.snapshot(now: now), isPreview: true)
}

#Preview("Small layout") {
    CapacityWidgetLayoutPreview(entry: widgetPreviewEntry(), family: .systemSmall)
}
#Preview("Medium layout") {
    CapacityWidgetLayoutPreview(entry: widgetPreviewEntry(), family: .systemMedium)
}
#Preview("Large layout") {
    CapacityWidgetLayoutPreview(entry: widgetPreviewEntry(), family: .systemLarge)
}
#Preview("Monochrome pill layout") {
    CapacityWidgetLayoutPreview(entry: widgetPreviewEntry(), family: .systemMedium, renderingMode: .accented)
}
#endif
