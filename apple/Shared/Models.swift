import Foundation

enum AppIdentity {
    static var urlScheme: String {
        Bundle.main.object(forInfoDictionaryKey: "BoulderbatURLScheme") as? String ?? "boulderbat"
    }
}

struct Gym: Identifiable, Hashable, Codable, Sendable {
    let id: Int
    let title: String
    let city: String
    let provider: String
    let hex: UInt32
    static let all: [Gym] = [
        .init(id: 262, title: "Hannovergasse", city: "Wien", provider: "Boulderbar", hex: 0xF69B36),
        .init(id: 263, title: "Hauptbahnhof", city: "Wien", provider: "Boulderbar", hex: 0xB56BE8),
        .init(id: 264, title: "Seestadt", city: "Wien", provider: "Boulderbar", hex: 0xF25F8C),
        .init(id: 265, title: "Wienerberg", city: "Wien", provider: "Boulderbar", hex: 0x668CFF),
        .init(id: 1001, title: "Blockfabrik", city: "Wien", provider: "Blockfabrik", hex: 0x57CFB1),
        .init(id: 284, title: "St. Pölten", city: "St. Pölten", provider: "Boulderbar", hex: 0x73BDA3),
        .init(id: 260, title: "Linz", city: "Linz", provider: "Boulderbar", hex: 0x65B6FF),
        .init(id: 261, title: "Salzburg", city: "Salzburg", provider: "Boulderbar", hex: 0xD7C777)
    ]
    static func find(_ id: Int) -> Gym { all.first { $0.id == id } ?? all[0] }
}

struct LiveReading: Codable, Identifiable, Sendable {
    let id: Int
    let title: String
    let url: URL
    let capacity: Double
    let recordedAt: Date
}
struct Reading: Codable, Sendable {
    let locationId: Int
    let title: String
    let capacity: Double
    let recordedAt: Date
}
struct ForecastPoint: Codable, Sendable {
    let capacity: Double
    let p10: Double
    let p90: Double
    let recordedAt: Date
}
struct LocationForecast: Codable, Sendable {
    let locationId: Int
    let title: String
    let status: String
    let reason: String?
    let points: [ForecastPoint]
}
struct ForecastResponse: Codable, Sendable {
    let date: String
    let timezone: String
    let model: String
    let generatedAt: Date
    let contextEnd: Date
    let validUntil: Date
    let locations: [LocationForecast]
}
struct WeekCell: Codable, Identifiable, Sendable {
    let weekday: Int
    let hour: Int
    let averageCapacity: Double
    let sampleCount: Int
    var id: String { "\(weekday)-\(hour)" }
}
struct TypicalWeek: Codable, Sendable {
    let cells: [WeekCell]
    let weekCount: Int
}
struct DashboardSnapshot: Codable, Sendable {
    var fetchedAt: Date
    var day: String
    var live: [LiveReading]
    var readings: [Reading]
    var forecast: ForecastResponse?
    var forecastError: String?
    func location(_ id: Int) -> LiveReading? { live.first { $0.id == id } }
    func prediction(_ id: Int, now: Date = .now) -> LocationForecast? {
        guard day == Vienna.day(now), forecast?.date == day else { return nil }
        return forecast?.locations.first { $0.locationId == id }
    }
}

enum Vienna {
    static let zone = TimeZone(identifier: "Europe/Vienna")!
    static var calendar: Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = zone
        return calendar
    }
    static func day(_ date: Date) -> String {
        let parts = calendar.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", parts.year!, parts.month!, parts.day!)
    }
    static func date(_ day: String) -> Date? {
        let formatter = DateFormatter()
        formatter.calendar = calendar
        formatter.timeZone = zone
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.isLenient = false
        guard let date = formatter.date(from: day), self.day(date) == day else { return nil }
        return date
    }
    static func addingDays(_ amount: Int, to date: Date) -> Date {
        calendar.date(byAdding: .day, value: amount, to: date)!
    }
    static func chartRange(_ day: String) -> ClosedRange<Date> {
        let midnight = date(day) ?? calendar.startOfDay(for: .now)
        return calendar.date(bySettingHour: 8, minute: 0, second: 0, of: midnight)!...addingDays(1, to: midnight)
    }
    static func time(_ date: Date) -> String {
        {
            let formatter = DateFormatter()
            formatter.locale = Locale(identifier: "en_US_POSIX")
            formatter.timeZone = zone
            formatter.dateFormat = "HH:mm"
            return formatter.string(from: date)
        }()
    }
    static func nextRefresh(after date: Date) -> Date {
        let timestamp = date.timeIntervalSince1970
        return Date(timeIntervalSince1970: (floor((timestamp - 60) / 900) + 1) * 900 + 60)
    }
}

enum Occupancy {
    static func label(_ value: Double) -> String { value < 40 ? "Quiet" : value < 70 ? "Moderate" : "Busy" }
}

struct GraphPoint: Identifiable, Sendable {
    let id: String
    let date: Date
    let value: Double
    let lower: Double?
    let upper: Double?
    let segment: String
    let predicted: Bool
}

enum GraphData {
    static func points(gym: Int, readings: [Reading], forecast: LocationForecast?, range: ClosedRange<Date>) -> [GraphPoint] {
        let recorded = readings.filter { $0.locationId == gym && range.contains($0.recordedAt) }
            .sorted { $0.recordedAt < $1.recordedAt }
        var result: [GraphPoint] = []
        var segment = 0
        var previous: Date?
        for (index, row) in recorded.enumerated() {
            if let previous, row.recordedAt.timeIntervalSince(previous) > 900 { segment += 1 }
            result.append(.init(id: "a\(gym)-\(index)", date: row.recordedAt, value: row.capacity,
                                lower: nil, upper: nil, segment: "\(gym)-a\(segment)", predicted: false))
            previous = row.recordedAt
        }
        let future = forecast?.status == "ok" ? (forecast?.points ?? []).filter { range.contains($0.recordedAt) }.sorted { $0.recordedAt < $1.recordedAt } : []
        if let last = recorded.last, let first = future.first,
           first.recordedAt > last.recordedAt, first.recordedAt.timeIntervalSince(last.recordedAt) <= 900 {
            result.append(.init(id: "c\(gym)", date: last.recordedAt, value: last.capacity,
                                lower: nil, upper: nil, segment: "\(gym)-f", predicted: true))
        }
        result += future.enumerated().map { index, row in
            GraphPoint(id: "f\(gym)-\(index)", date: row.recordedAt, value: row.capacity,
                       lower: row.p10, upper: row.p90, segment: "\(gym)-f", predicted: true)
        }
        return result
    }
}
