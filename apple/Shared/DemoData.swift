import Foundation

// Deterministic preview/gallery fixtures. Live requests never fall back to demo data.
enum DemoData {
    static func snapshot(now: Date = .now) -> DashboardSnapshot {
        let day = Vienna.day(now)
        let range = Vienna.chartRange(day)
        let displayNow = max(range.lowerBound.addingTimeInterval(3600), min(now, range.upperBound.addingTimeInterval(-3600)))
        var readings: [Reading] = []
        var forecasts: [LocationForecast] = []
        var live: [LiveReading] = []
        for (index, gym) in Gym.all.enumerated() {
            func occupancy(_ time: Date) -> Double {
                let hour = time.timeIntervalSince(range.lowerBound) / 3600
                let peak = 8.7 + Double(index % 3) * 0.55
                return max(0, min(100, (40 + Double(index) * 5) * exp(-pow((hour - peak) / 3.6, 2)) + 13 * exp(-pow((hour - 3) / 1.5, 2))))
            }
            var time = range.lowerBound
            while time <= displayNow {
                readings.append(.init(locationId: gym.id, title: gym.title, capacity: occupancy(time), recordedAt: time))
                time = time.addingTimeInterval(300)
            }
            live.append(.init(id: gym.id, title: gym.title, url: URL(string: gym.id == 1001 ? "https://blockfabrik.at" : "https://boulderbar.net")!, capacity: occupancy(displayNow), recordedAt: displayNow))
            var points: [ForecastPoint] = []
            time = displayNow
            while time < range.upperBound {
                let value = occupancy(time)
                points.append(.init(capacity: value, p10: max(0, value - 8), p90: min(100, value + 13), recordedAt: time))
                time = time.addingTimeInterval(900)
            }
            let end = range.upperBound.addingTimeInterval(-1)
            points.append(.init(capacity: 0, p10: 0, p90: 1, recordedAt: end))
            forecasts.append(.init(locationId: gym.id, title: gym.title, status: "ok", reason: nil, points: points))
        }
        return .init(fetchedAt: displayNow, day: day, live: live, readings: readings,
                     forecast: .init(date: day, timezone: "Europe/Vienna", model: "Timestral-5M", generatedAt: displayNow, contextEnd: displayNow, validUntil: range.upperBound.addingTimeInterval(-1), locations: forecasts), forecastError: nil)
    }
    static var week: TypicalWeek {
        .init(cells: (8..<24).flatMap { hour in (0..<7).map { day in
            WeekCell(weekday: day, hour: hour, averageCapacity: max(0, 62 * exp(-pow((Double(hour) - 18) / 3.5, 2)) + Double(day % 3) * 4), sampleCount: 96)
        } }, weekCount: 8)
    }
}
