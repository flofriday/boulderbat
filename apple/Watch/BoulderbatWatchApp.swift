import SwiftUI

@main
struct BoulderbatWatchApp: App {
    @State private var store = AppStore()
    var body: some Scene {
        WindowGroup { WatchRootView().environment(store) }
    }
}

struct WatchRootView: View {
    @Environment(AppStore.self) private var store
    @Environment(\.scenePhase) private var phase
    var body: some View {
        NavigationStack {
            List {
                if let error = store.error { Text("Saved data · \(error)").font(.caption2).foregroundStyle(.secondary) }
                ForEach(Gym.all) { gym in
                    if let reading = store.snapshot?.location(gym.id), let snapshot = store.snapshot {
                        NavigationLink { WatchGymDetail(gym: gym, reading: reading, snapshot: snapshot) } label: {
                            HStack {
                                VStack(alignment: .leading, spacing: 4) { Text(gym.title).font(.headline); Text(Occupancy.label(reading.capacity)).font(.caption2).foregroundStyle(BatStyle.status(reading.capacity)) }
                                Spacer(minLength: 4)
                                Text("\(reading.capacity, specifier: "%.0f")%").font(.title3.bold()).foregroundStyle(gym.color)
                            }
                        }
                    }
                }
                if store.snapshot == nil {
                    if store.loading { ProgressView() }
                    Button("Refresh") { Task { await store.refresh() } }
                }
            }.navigationTitle("Boulderbat")
                .refreshable { await store.refresh() }
        }
        .tint(BatStyle.yellow)
        .task(id: phase) {
            guard phase == .active else { return }
            while !Task.isCancelled {
                await store.refresh()
                do { try await Task.sleep(for: .seconds(60)) } catch { break }
            }
        }
    }
}
struct WatchGymDetail: View {
    let gym: Gym
    let reading: LiveReading
    let snapshot: DashboardSnapshot
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text("\(reading.capacity, specifier: "%.0f")%").font(.system(size: 44, weight: .semibold, design: .rounded)).foregroundStyle(gym.color)
                Text("\(Occupancy.label(reading.capacity)) · \(Vienna.time(reading.recordedAt))").font(.caption)
                CapacityChart(day: snapshot.day, gyms: [gym], readings: snapshot.readings,
                              forecasts: snapshot.prediction(gym.id).map { [$0] } ?? [], compact: true)
                    .frame(height: 110)
                Text("Solid: recorded\nDashed: predicted\nShading: 80% range").font(.caption2).foregroundStyle(.secondary)
                if let reason = snapshot.prediction(gym.id)?.reason { Text(reason).font(.caption2).foregroundStyle(.secondary) }
                Text("Vienna time").font(.caption2).foregroundStyle(.secondary)
            }
        }.navigationTitle(gym.title)
    }
}
