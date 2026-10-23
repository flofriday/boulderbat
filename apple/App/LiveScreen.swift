import SwiftUI

struct LiveScreen: View {
    @Environment(AppStore.self) private var store
    let openHistory: (Int) -> Void
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Text("Find the best time to hang out at the gym")
                    .font(.largeTitle.bold()).tracking(-1)
                if let error = store.error {
                    Label("Showing saved data · \(error)", systemImage: "wifi.slash").font(.callout).foregroundStyle(.secondary)
                }
                if store.loading { ProgressView("Checking the gyms…").frame(maxWidth: .infinity, minHeight: 160) }
                if let snapshot = store.snapshot {
                    HStack {
                        Label("\(snapshot.live.count) locations", systemImage: "location")
                        Spacer()
                        Text("Updated \(Vienna.time(snapshot.fetchedAt)) · Vienna time")
                    }.font(.caption).foregroundStyle(.secondary)
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 305), spacing: 18)], spacing: 18) {
                        ForEach(Gym.all) { gym in
                            if let reading = snapshot.location(gym.id) {
                                Button { openHistory(gym.id) } label: { LiveCapacityCard(gym: gym, reading: reading, snapshot: snapshot) }
                                    .buttonStyle(.plain)
                                    .accessibilityHint("Open occupancy history for \(gym.title)")
                            }
                        }
                    }
                    if let message = snapshot.forecastError { Label(message, systemImage: "cloud").font(.caption).foregroundStyle(.secondary) }
                    ChartLegend()
                } else if !store.loading {
                    ContentUnavailableView { Label("Couldn’t reach the gyms", systemImage: "wifi.slash") }
                        description: { Text(store.error ?? "Refresh to try again.") }
                        actions: { Button("Try again") { Task { await store.refresh() } } }
                }
            }.padding(24).frame(maxWidth: 1400)
        }.refreshable { await store.refresh() }
    }
}

struct LiveCapacityCard: View {
    let gym: Gym
    let reading: LiveReading
    let snapshot: DashboardSnapshot
    var body: some View {
        HStack(alignment: .bottom, spacing: 14) {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) { Circle().fill(gym.color).frame(width: 7, height: 7); Text(gym.title).font(.headline) }
                Text("\(gym.provider) · \(gym.city)").font(.caption).foregroundStyle(.secondary)
                Spacer(minLength: 16)
                VStack(alignment: .leading, spacing: 5) {
                    Text("\(reading.capacity, specifier: "%.0f")%")
                        .font(.system(size: 49, weight: .semibold, design: .rounded)).tracking(-2).monospacedDigit()
                    if Date.now.timeIntervalSince(reading.recordedAt) > 900 {
                        Text("Updated \(Vienna.time(reading.recordedAt)) · stale")
                            .font(.caption2).foregroundStyle(.secondary)
                    }
                }
            }
            CapacityChart(day: snapshot.day, gyms: [gym], readings: snapshot.readings,
                          forecasts: snapshot.prediction(gym.id).map { [$0] } ?? [], compact: true)
                .frame(maxWidth: .infinity, maxHeight: .infinity).allowsHitTesting(false)
        }
        .frame(height: 180)
        .overlay(alignment: .topTrailing) {
            StatusPill(value: reading.capacity)
                .background(Color(hex: 0x191E20), in: Capsule())
        }
        .padding(20).frame(maxWidth: .infinity, alignment: .leading)
        .background(LinearGradient(colors: [Color(hex: 0x292D32), Color(hex: 0x111416)], startPoint: .topLeading, endPoint: .bottomTrailing), in: RoundedRectangle(cornerRadius: 25))
        .overlay(RoundedRectangle(cornerRadius: 25).stroke(.white.opacity(0.10), lineWidth: 1))
        .environment(\.colorScheme, .dark)
    }
}
