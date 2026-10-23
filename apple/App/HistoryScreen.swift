import SwiftUI

struct HistoryScreen: View {
    @Environment(AppStore.self) private var store
    @Binding var selectedGym: Int
    @Binding var selectedDate: Date
    @State private var selected: Set<Int> = []
    @State private var readings: [Reading] = []
    @State private var loading = false
    @State private var error: String?
    private var day: String { Vienna.day(selectedDate) }
    private var today: Bool { day == Vienna.day(.now) }
    private var gyms: [Gym] { Gym.all.filter { selected.contains($0.id) } }
    private var visibleReadings: [Reading] { today ? store.snapshot?.readings ?? [] : readings }
    private var forecasts: [LocationForecast] {
        guard today, let forecast = store.snapshot?.forecast, forecast.date == day else { return [] }
        return forecast.locations
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                HStack {
                    Button { selectedDate = Vienna.addingDays(-1, to: selectedDate) } label: { Image(systemName: "chevron.left") }.accessibilityLabel("Previous day")
                    DatePicker("Date", selection: $selectedDate, in: ...Date.now, displayedComponents: .date).labelsHidden()
                        .environment(\.timeZone, Vienna.zone)
                    Button { selectedDate = Vienna.addingDays(1, to: selectedDate) } label: { Image(systemName: "chevron.right") }
                        .disabled(today).accessibilityLabel("Next day")
                    Spacer()
                    Button("Today") { selectedDate = .now }
                }.buttonStyle(.bordered)
                GymSelection(selected: $selected)
                if loading { ProgressView("Loading history…") }
                if let error { Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.secondary) }
                Surface {
                    VStack(alignment: .leading, spacing: 16) {
                        CapacityChart(day: day, gyms: gyms, readings: visibleReadings, forecasts: forecasts)
                            .frame(height: 330)
                        ChartLegend()
                        HStack {
                            Text("08:00–midnight · Vienna time")
                            Spacer()
                            if today { Text("Updated \(Vienna.time(store.snapshot?.fetchedAt ?? .now))") }
                        }.font(.caption2).foregroundStyle(.secondary)
                    }
                }
                if !loading && visibleReadings.isEmpty {
                    ContentUnavailableView("No readings for this day", systemImage: "chart.xyaxis.line", description: Text("Choose another date to explore occupancy."))
                }
                ForEach(gyms) { gym in
                    HStack {
                        Circle().fill(gym.color).frame(width: 9, height: 9)
                        Text(gym.title).font(.subheadline.weight(.medium))
                        Spacer()
                        if let reading = store.snapshot?.location(gym.id) { Link(destination: reading.url) { Image(systemName: "arrow.up.right.square") }.accessibilityLabel("Visit \(gym.title)") }
                    }
                    if let forecast = forecasts.first(where: { $0.locationId == gym.id }), forecast.status != "ok" {
                        Text(forecast.reason ?? "Prediction unavailable").font(.caption).foregroundStyle(.secondary)
                    }
                }
                if today, let message = store.snapshot?.forecastError { Label(message, systemImage: "cloud").font(.caption).foregroundStyle(.secondary) }
            }.padding(24).frame(maxWidth: 1400)
        }
        .onAppear { selected = [selectedGym] }
        .onChange(of: store.snapshot?.day) { oldDay, _ in
            if day == oldDay { selectedDate = .now }
        }
        .onChange(of: selectedGym) { _, gym in selected = [gym] }
        .task(id: day + store.server) {
            guard !today else { loading = false; error = nil; return }
            loading = true; error = nil; readings = []
            let requestedDay = day
            do {
                let values = try await store.api.history(day: requestedDay)
                guard !Task.isCancelled else { return }
                readings = values
            } catch { if !Task.isCancelled { self.error = error.localizedDescription } }
            if !Task.isCancelled { loading = false }
        }
    }
}

struct GymSelection: View {
    @Binding var selected: Set<Int>
    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                chip("All", active: selected.count == Gym.all.count) { selected = Set(Gym.all.map(\.id)) }
                chip("Wien", active: selected == Set(Gym.all.filter { $0.city == "Wien" }.map(\.id))) { selected = Set(Gym.all.filter { $0.city == "Wien" }.map(\.id)) }
                ForEach(Gym.all) { gym in
                    Button {
                        if selected.count == Gym.all.count { selected = [gym.id] }
                        else if selected.contains(gym.id) { selected.remove(gym.id); if selected.isEmpty { selected = Set(Gym.all.map(\.id)) } }
                        else { selected.insert(gym.id) }
                    } label: {
                        HStack(spacing: 6) { Circle().fill(gym.color).frame(width: 8, height: 8); Text(gym.title) }
                            .font(.caption.weight(.medium)).padding(.horizontal, 12).padding(.vertical, 9)
                            .background(selected.contains(gym.id) ? gym.color.opacity(0.16) : Color.secondary.opacity(0.08), in: Capsule())
                    }.buttonStyle(.plain).accessibilityAddTraits(selected.contains(gym.id) ? .isSelected : [])
                }
            }
        }
    }
    private func chip(_ title: String, active: Bool, action: @escaping () -> Void) -> some View {
        Button(title, action: action).font(.caption.weight(.semibold)).padding(.horizontal, 12).padding(.vertical, 9)
            .background(active ? BatStyle.yellow.opacity(0.3) : .secondary.opacity(0.08), in: Capsule()).buttonStyle(.plain)
    }
}
