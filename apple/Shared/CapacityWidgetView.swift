import SwiftUI
import WidgetKit

struct CapacityEntry: TimelineEntry {
    let date: Date
    let gym: Gym
    let snapshot: DashboardSnapshot?
    var offline = false
    var isPreview = false
}

struct CapacityWidgetView: View {
    @Environment(\.widgetFamily) private var systemFamily
    @Environment(\.widgetRenderingMode) private var systemRenderingMode
    let entry: CapacityEntry
    var previewFamily: WidgetFamily? = nil
    var previewRenderingMode: WidgetRenderingMode? = nil
    private var family: WidgetFamily { previewFamily ?? systemFamily }
    private var renderingMode: WidgetRenderingMode { previewRenderingMode ?? systemRenderingMode }
    private var live: LiveReading? { entry.snapshot?.location(entry.gym.id) }
    private var stale: Bool { entry.offline || live.map { entry.date.timeIntervalSince($0.recordedAt) > 900 } ?? true }
    private var link: URL { URL(string: "\(AppIdentity.urlScheme)://history?gym=\(entry.gym.id)")! }
    var body: some View {
        Group {
            #if os(watchOS) || os(iOS)
            switch family {
            case .accessoryCircular:
                Gauge(value: live?.capacity ?? 0, in: 0...100) {
                    Image(systemName: "mountain.2.fill")
                } currentValueLabel: { Text(live.map { "\(Int($0.capacity))" } ?? "—") }
                    .gaugeStyle(.accessoryCircular).tint(entry.gym.color)
            case .accessoryInline:
                Text("\(entry.gym.title) · \(live.map { "\(Int($0.capacity))%" } ?? "Unavailable")")
            case .accessoryRectangular:
                VStack(alignment: .leading, spacing: 2) {
                    Text(entry.gym.title).font(.headline).widgetAccentable()
                    HStack {
                        Text(live.map { "\(Int($0.capacity))%" } ?? "—").font(.title2.bold())
                        if let snapshot = entry.snapshot { miniChart(snapshot).frame(height: 30) }
                    }
                    Text(dataWarning ?? live.map { Occupancy.label($0.capacity) } ?? "Open app to refresh").font(.caption2)
                }
            default: systemView
            }
            #else
            systemView
            #endif
        }
        .widgetURL(link)
        .containerBackground(for: .widget) {
            LinearGradient(colors: [Color(hex: 0x2B2E33), Color(hex: 0x101315)], startPoint: .topLeading, endPoint: .bottomTrailing)
        }
    }
    private var isSmall: Bool {
        #if os(watchOS)
        false
        #else
        family == .systemSmall
        #endif
    }
    private var isMedium: Bool {
        #if os(watchOS)
        false
        #else
        family == .systemMedium
        #endif
    }
    private var systemView: some View {
        Group {
            if isSmall {
                VStack(alignment: .leading, spacing: 8) {
                    title
                    value
                    if let snapshot = entry.snapshot {
                        miniChart(snapshot).frame(maxWidth: .infinity, maxHeight: .infinity)
                    }
                    if let dataWarning { Text(dataWarning).font(.system(size: 9)).foregroundStyle(.secondary) }
                }
            } else if isMedium {
                // The chart uses the full height; metadata floats above its upper edge.
                HStack(alignment: .bottom, spacing: 12) {
                    value.padding(.top, 50)
                    if let snapshot = entry.snapshot {
                        miniChart(snapshot).frame(maxWidth: .infinity, maxHeight: .infinity)
                    } else { Spacer(minLength: 0) }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomLeading)
                .overlay(alignment: .top) { header }
            } else {
                VStack(alignment: .leading, spacing: 8) {
                    header
                    value
                    if let snapshot = entry.snapshot {
                        CapacityChart(day: snapshot.day, gyms: [entry.gym], readings: snapshot.readings,
                                      forecasts: snapshot.prediction(entry.gym.id, now: entry.date).map { [$0] } ?? [], showsLastRecordedSample: true, now: entry.date)
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                            .allowsHitTesting(false)
                    } else { Spacer(minLength: 0) }
                }
            }
        }
        .environment(\.colorScheme, .dark)
        .accessibilityElement(children: .combine)
        .accessibilityValue(freshness)
    }
    private var title: some View {
        Text(entry.gym.title).font(.headline).lineLimit(1).minimumScaleFactor(0.7)
    }
    private var header: some View {
        HStack(alignment: .top, spacing: 8) {
            VStack(alignment: .leading, spacing: 3) {
                title
                Text(entry.gym.provider).font(.caption).foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
            VStack(alignment: .trailing, spacing: 3) {
                if let live {
                    if renderingMode == .fullColor {
                        StatusPill(value: live.capacity)
                            .background(Color(hex: 0x191E20), in: Capsule())
                            .fixedSize()
                    } else {
                        // Glass/tinted widgets map opaque colors to white. Preserve
                        // opacity so the capsule doesn't cover its white label.
                        Label(Occupancy.label(live.capacity), systemImage: live.capacity < 40 ? "leaf.fill" : "person.2.fill")
                            .font(.caption.weight(.semibold)).foregroundStyle(.white)
                            .padding(.horizontal, 10).padding(.vertical, 5)
                            .background(.white.opacity(0.12), in: Capsule())
                            .overlay(Capsule().stroke(.white.opacity(0.18), lineWidth: 0.5))
                            .fixedSize()
                    }
                }
                if let dataWarning { Text(dataWarning).font(.system(size: 9)).foregroundStyle(.secondary) }
            }
            .lineLimit(1).minimumScaleFactor(0.8)
        }
    }
    private var dataWarning: String? {
        guard live != nil else { return "Unavailable" }
        if entry.snapshot?.day != Vienna.day(entry.date) { return "Previous day" }
        return stale ? "Saved data" : nil
    }
    private var freshness: String {
        guard let live else { return "Unavailable" }
        let label = entry.snapshot?.day != Vienna.day(entry.date) ? "Previous day" : stale ? "Saved" : "Updated"
        return "\(label) \(Vienna.time(live.recordedAt))"
    }
    private var value: some View {
        Text(live.map { "\(Int($0.capacity))%" } ?? "—")
            .font(.system(size: isSmall ? 32 : 45, weight: .semibold, design: .rounded))
            .tracking(-1.5).monospacedDigit()
            .lineLimit(1).minimumScaleFactor(0.75)
    }
    private func miniChart(_ snapshot: DashboardSnapshot) -> some View {
        CapacityChart(day: snapshot.day, gyms: [entry.gym], readings: snapshot.readings,
                      forecasts: snapshot.prediction(entry.gym.id, now: entry.date).map { [$0] } ?? [], compact: true, showsLastRecordedSample: true, now: entry.date)
            .allowsHitTesting(false)
    }
}

// Plain SwiftUI layout previews work on Mac without installing a widget host.
// WidgetKit previews on iOS additionally exercise the system container/timeline.
#if !os(watchOS) && (DEBUG || WIDGET_PREVIEW)
struct CapacityWidgetLayoutPreview: View {
    let entry: CapacityEntry
    let family: WidgetFamily
    var renderingMode: WidgetRenderingMode = .fullColor
    private var size: CGSize {
        switch family {
        case .systemSmall: CGSize(width: 170, height: 170)
        case .systemLarge: CGSize(width: 360, height: 380)
        default: CGSize(width: 360, height: 170)
        }
    }
    private var content: some View {
        CapacityWidgetView(entry: entry, previewFamily: family, previewRenderingMode: renderingMode)
            .frame(width: size.width - 32, height: size.height - 32)
    }
    var body: some View {
        Group {
            if renderingMode == .fullColor { content }
            else {
                // Approximate the system's white remapping while preserving alpha.
                Color.white.frame(width: size.width - 32, height: size.height - 32)
                    .mask(content)
            }
        }
            .padding(16)
            .background(LinearGradient(colors: [Color(hex: 0x2B2E33), Color(hex: 0x101315)], startPoint: .topLeading, endPoint: .bottomTrailing))
            .clipShape(RoundedRectangle(cornerRadius: 24))
            .environment(\.colorScheme, .dark)
    }
}
#endif

