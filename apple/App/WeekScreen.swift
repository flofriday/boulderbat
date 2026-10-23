import SwiftUI

struct WeekScreen: View {
    @Environment(AppStore.self) private var store
    @Binding var selectedGym: Int
    @State private var week: TypicalWeek?
    @State private var loading = false
    @State private var error: String?
    @State private var highlighted: WeekCell?
    private let days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Picker("Location", selection: $selectedGym) { ForEach(Gym.all) { Text($0.title).tag($0.id) } }.pickerStyle(.menu)
                VStack(alignment: .leading, spacing: 5) {
                    Text("Typical week").font(.title.bold())
                    Text("Average occupancy by weekday and hour in Vienna time.").foregroundStyle(.secondary)
                }
                if loading { ProgressView("Finding the patterns…") }
                if let error { Label(error, systemImage: "wifi.slash").foregroundStyle(.secondary) }
                if let week {
                    Surface {
                        VStack(alignment: .leading, spacing: 16) {
                            Grid(horizontalSpacing: 4, verticalSpacing: 4) {
                                GridRow { Text(""); ForEach(days, id: \.self) { Text($0).font(.caption.weight(.medium)).frame(maxWidth: .infinity) } }
                                ForEach(8..<24) { hour in
                                    GridRow {
                                        Text(String(format: "%02d", hour)).font(.caption2.monospacedDigit()).foregroundStyle(.secondary).frame(width: 24)
                                        ForEach(0..<7) { day in
                                            let cell = week.cells.first { $0.weekday == day && $0.hour == hour }
                                            Button { highlighted = cell } label: {
                                                RoundedRectangle(cornerRadius: 4).fill(cell.map { heat($0.averageCapacity) } ?? Color.secondary.opacity(0.08)).frame(maxWidth: .infinity, minHeight: 21)
                                            }.buttonStyle(.plain)
                                                .accessibilityLabel("\(days[day]) \(hour):00: \(cell.map { "\(Int($0.averageCapacity)) percent, \($0.sampleCount) samples" } ?? "no readings")")
                                        }
                                    }
                                }
                            }
                            HStack(spacing: 6) {
                                Text("Quiet").foregroundStyle(.secondary)
                                ForEach([0.0, 10, 20, 30, 40, 50], id: \.self) { value in RoundedRectangle(cornerRadius: 3).fill(heat(value)).frame(width: 22, height: 10) }
                                Text("Busy").foregroundStyle(.secondary)
                                Spacer()
                                Text("\(week.weekCount) weeks").foregroundStyle(.secondary)
                            }.font(.caption2)
                            if let cell = highlighted { Text("\(days[cell.weekday]) \(cell.hour):00 · \(cell.averageCapacity, specifier: "%.0f")% average · \(cell.sampleCount) readings").font(.caption).foregroundStyle(.secondary) }
                        }
                    }
                    Text("Based on \(week.cells.reduce(0) { $0 + $1.sampleCount }.formatted()) observations from the latest eight local calendar weeks.").font(.caption).foregroundStyle(.secondary)
                    if week.cells.isEmpty { ContentUnavailableView("No weekly pattern yet", systemImage: "calendar", description: Text("Check back after more readings have been collected.")) }
                }
            }.padding(24).frame(maxWidth: 1000)
        }
        .task(id: String(selectedGym) + store.server) {
            week = nil; error = nil; highlighted = nil; loading = true
            defer { if !Task.isCancelled { loading = false } }
            if ProcessInfo.processInfo.arguments.contains("--demo") { week = DemoData.week; return }
            do { let value = try await store.api.week(gym: selectedGym); if !Task.isCancelled { week = value } }
            catch { if !Task.isCancelled { self.error = error.localizedDescription } }
        }
    }
    private func heat(_ value: Double) -> Color {
        // Match the web heatmap: HSL(48→0°, 95%, 94→46%), capped at 50% occupancy.
        // SwiftUI takes HSB, so convert lightness instead of keeping brightness constant.
        let intensity = min(max(value / 50, 0), 1)
        let lightness = 0.94 - intensity * 0.48
        let brightness = lightness + 0.95 * min(lightness, 1 - lightness)
        let saturation = 2 * (1 - lightness / brightness)
        return Color(hue: (48 - intensity * 48) / 360, saturation: saturation, brightness: brightness)
    }
}
