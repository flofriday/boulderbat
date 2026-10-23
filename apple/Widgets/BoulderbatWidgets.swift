import SwiftUI
import WidgetKit
import AppIntents
import OSLog

enum GymChoice: String, CaseIterable, Sendable {
    case hannovergasse, hauptbahnhof, seestadt, wienerberg, blockfabrik, stpoelten, linz, salzburg
    var gym: Gym {
        Gym.find([Self.hannovergasse: 262, .hauptbahnhof: 263, .seestadt: 264, .wienerberg: 265, .blockfabrik: 1001, .stpoelten: 284, .linz: 260, .salzburg: 261][self]!)
    }
    static func resolve(_ value: String?) -> GymChoice {
        guard let value else { return .hannovergasse }
        // Accept identifiers saved by the earlier AppEnum configuration as well.
        return Self(rawValue: value) ?? allCases.first { $0.gym.title == value } ?? .hannovergasse
    }
}

struct GymOptionsProvider: DynamicOptionsProvider {
    func results() async throws -> [String] { GymChoice.allCases.map { $0.gym.title } }
}

struct GymWidgetIntent: WidgetConfigurationIntent {
    static var title: LocalizedStringResource = "Choose your gym"
    static var description = IntentDescription("Recorded occupancy and today's forecast for your favourite gym.")
    // String options avoid SDK 27's AppEnum decoding regression while retaining
    // the same location picker and accepting existing saved identifiers.
    @Parameter(title: "Location", optionsProvider: GymOptionsProvider()) var location: String?
    @Parameter(title: "API server") var server: String?
    var selectedGym: Gym { GymChoice.resolve(location).gym }
    var serverURL: String {
        let value = server?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return value.isEmpty ? APIClient.production.absoluteString : value
    }
    static var parameterSummary: some ParameterSummary {
        Summary { \.$location; \.$server }
    }
}

struct CapacityProvider: AppIntentTimelineProvider {
    func placeholder(in context: Context) -> CapacityEntry {
        .init(date: .now, gym: Gym.all[0], snapshot: DemoData.snapshot(), isPreview: true)
    }
    func snapshot(for configuration: GymWidgetIntent, in context: Context) async -> CapacityEntry {
        if context.isPreview { return .init(date: .now, gym: configuration.selectedGym, snapshot: DemoData.snapshot(), isPreview: true) }
        return await load(configuration)
    }
    func timeline(for configuration: GymWidgetIntent, in context: Context) async -> Timeline<CapacityEntry> {
        let entry = await load(configuration)
        let next = max(Vienna.nextRefresh(after: .now), Date.now.addingTimeInterval(300))
        var entries = [entry]
        let midnight = Vienna.addingDays(1, to: Vienna.calendar.startOfDay(for: entry.date))
        // Pre-schedule stale/midnight states even if WidgetKit defers networking.
        if let reading = entry.snapshot?.location(entry.gym.id) {
            let expires = reading.recordedAt.addingTimeInterval(901)
            if expires > entry.date && expires < midnight {
                entries.append(.init(date: expires, gym: entry.gym, snapshot: entry.snapshot, offline: entry.offline))
            }
        }
        entries.append(.init(date: midnight, gym: entry.gym, snapshot: entry.snapshot, offline: entry.offline))
        return Timeline(entries: entries, policy: .after(next))
    }
    func recommendations() -> [AppIntentRecommendation<GymWidgetIntent>] {
        GymChoice.allCases.map { choice in
            let intent = GymWidgetIntent(); intent.location = choice.gym.title
            return AppIntentRecommendation(intent: intent, description: choice.gym.title)
        }
    }
    func load(_ configuration: GymWidgetIntent) async -> CapacityEntry {
        let gym = configuration.selectedGym
        Logger(subsystem: "dev.flofriday.boulderbat", category: "WidgetConfiguration")
            .info("Loading gym \(gym.id, privacy: .public), selection \(configuration.location ?? "unset", privacy: .public)")
        guard let server = URL(string: configuration.serverURL), let scheme = server.scheme,
              ["http", "https"].contains(scheme), server.host != nil else {
            return .init(date: .now, gym: gym, snapshot: nil, offline: true)
        }
        do {
            let snapshot = try await APIClient(baseURL: server).dashboard(gym: gym.id)
            SnapshotCache.save(snapshot, server: server, gym: gym.id)
            return .init(date: .now, gym: gym, snapshot: snapshot)
        } catch {
            return .init(date: .now, gym: gym, snapshot: SnapshotCache.load(server: server, gym: gym.id), offline: true)
        }
    }
}

struct BoulderbatCapacityWidget: Widget {
    let kind = "BoulderbatCapacity"
    var body: some WidgetConfiguration {
        AppIntentConfiguration(kind: kind, intent: GymWidgetIntent.self, provider: CapacityProvider()) { entry in
            CapacityWidgetView(entry: entry)
        }
        .configurationDisplayName("Gym")
        .description("Live occupancy, today's graph and forecast with an 80% prediction range.")
        .supportedFamilies(families)
    }
    private var families: [WidgetFamily] {
        #if os(watchOS)
        [.accessoryCircular, .accessoryRectangular, .accessoryInline]
        #elseif os(iOS)
        [.systemSmall, .systemMedium, .systemLarge, .accessoryCircular, .accessoryRectangular, .accessoryInline]
        #else
        [.systemSmall, .systemMedium, .systemLarge]
        #endif
    }
}

#if !WIDGET_PREVIEW
@main
struct BoulderbatWidgetBundle: WidgetBundle {
    var body: some Widget { BoulderbatCapacityWidget() }
}

#endif

#if !WIDGET_PREVIEW && DEBUG
#if os(watchOS)
#Preview(as: .accessoryRectangular) { BoulderbatCapacityWidget() } timeline: { CapacityEntry(date: .now, gym: Gym.all[0], snapshot: DemoData.snapshot(), isPreview: true) }
#elseif os(iOS)
#Preview("Small", as: .systemSmall) { BoulderbatCapacityWidget() } timeline: { CapacityEntry(date: .now, gym: Gym.all[0], snapshot: DemoData.snapshot(), isPreview: true) }
#Preview("Medium", as: .systemMedium) { BoulderbatCapacityWidget() } timeline: { CapacityEntry(date: .now, gym: Gym.all[0], snapshot: DemoData.snapshot(), isPreview: true) }
#Preview("Large", as: .systemLarge) { BoulderbatCapacityWidget() } timeline: { CapacityEntry(date: .now, gym: Gym.all[0], snapshot: DemoData.snapshot(), isPreview: true) }
#endif
#endif
