import Foundation
import CryptoKit

struct APIClient: Sendable {
    static let production = URL(string: "https://boulderbat.flofriday.dev")!
    let baseURL: URL
    var session: URLSession = .shared

    static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .custom { decoder in
            let value = try decoder.singleValueContainer().decode(String.self)
            let formatter = ISO8601DateFormatter()
            if let date = formatter.date(from: value) { return date }
            formatter.formatOptions.insert(.withFractionalSeconds)
            guard let date = formatter.date(from: value) else {
                throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath, debugDescription: "Invalid timestamp"))
            }
            return date
        }
        return decoder
    }
    func get<T: Decodable & Sendable>(_ path: String, query: [URLQueryItem] = []) async throws -> T {
        var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
        components.queryItems = query.isEmpty ? nil : query
        var request = URLRequest(url: components.url!)
        request.timeoutInterval = 40
        request.cachePolicy = .reloadIgnoringLocalCacheData
        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard (200..<300).contains(response.statusCode) else { throw APIError.http(response.statusCode) }
        return try Self.decoder().decode(T.self, from: data)
    }
    func live() async throws -> [LiveReading] { try await get("live") }
    func history(day: String, gym: Int? = nil) async throws -> [Reading] {
        var query = [URLQueryItem(name: "date", value: day)]
        if let gym { query.append(.init(name: "location_id", value: String(gym))) }
        return try await get("history", query: query)
    }
    func prediction(gym: Int? = nil) async throws -> ForecastResponse {
        try await get("prediction", query: gym.map { [.init(name: "location_id", value: String($0))] } ?? [])
    }
    func week(gym: Int) async throws -> TypicalWeek {
        try await get("typical-week", query: [.init(name: "location_id", value: String(gym))])
    }
    func dashboard(gym: Int? = nil, now: Date = .now) async throws -> DashboardSnapshot {
        let day = Vienna.day(now)
        async let live = live()
        async let history = history(day: day, gym: gym)
        async let prediction = optionalPrediction(gym: gym)
        let (locations, readings, forecast) = try await (live, history, prediction)
        return .init(fetchedAt: .now, day: day, live: locations, readings: readings,
                     forecast: forecast.0, forecastError: forecast.1)
    }
    private func optionalPrediction(gym: Int?) async -> (ForecastResponse?, String?) {
        do { return (try await prediction(gym: gym), nil) }
        catch { return (nil, "Forecast temporarily unavailable") }
    }
}

enum APIError: LocalizedError {
    case invalidResponse, http(Int)
    var errorDescription: String? {
        switch self {
        case .invalidResponse: return "The server returned an invalid response."
        case .http(let status): return "The server returned HTTP \(status). Please try again."
        }
    }
}

struct SnapshotCache {
    static func url(server: URL, gym: Int? = nil) -> URL {
        let hash = SHA256.hash(data: Data(server.absoluteString.utf8)).map { String(format: "%02x", $0) }.joined()
        return FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Boulderbat", isDirectory: true)
            .appendingPathComponent("\(hash)-\(gym ?? 0).json")
    }
    static func save(_ value: DashboardSnapshot, server: URL, gym: Int? = nil) {
        let path = url(server: server, gym: gym)
        do {
            try FileManager.default.createDirectory(at: path.deletingLastPathComponent(), withIntermediateDirectories: true)
            try JSONEncoder().encode(value).write(to: path, options: .atomic)
        } catch { /* A cache failure must not hide fresh network data. */ }
    }
    static func load(server: URL, gym: Int? = nil) -> DashboardSnapshot? {
        guard let data = try? Data(contentsOf: url(server: server, gym: gym)) else { return nil }
        return try? JSONDecoder().decode(DashboardSnapshot.self, from: data)
    }
}
