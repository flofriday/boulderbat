import XCTest
@testable import BoulderbatCore

final class CoreTests: XCTestCase {
    func testViennaCalendarAndDST() throws {
        let decoder = APIClient.decoder()
        let sample = try decoder.decode(LiveReading.self, from: Data(#"{"id":262,"title":"Gym","url":"https://example.org","capacity":27,"recorded_at":"2026-10-23T22:30:00Z"}"#.utf8))
        XCTAssertEqual(Vienna.day(sample.recordedAt), "2026-10-24")
        XCTAssertEqual(sample.capacity, 27)
        for (day, hours) in [("2026-03-29", 23), ("2026-10-25", 25)] {
            let start = try XCTUnwrap(Vienna.date(day))
            XCTAssertEqual(Vienna.addingDays(1, to: start).timeIntervalSince(start), Double(hours * 3600))
            XCTAssertEqual(Vienna.chartRange(day).upperBound.timeIntervalSince(Vienna.chartRange(day).lowerBound), 16 * 3600)
        }
        XCTAssertNil(Vienna.date("2026-02-30"))
        XCTAssertEqual(Vienna.day(Vienna.addingDays(1, to: Vienna.date("2026-12-31")!)), "2027-01-01")
    }
    func testRefreshBoundariesHaveOneMinuteOffset() {
        let parse = ISO8601DateFormatter()
        for (time, next) in [("15:15:59", "15:16:00"), ("15:16:00", "15:31:00"), ("23:59:00", "00:01:00")] {
            let input = parse.date(from: "2026-10-23T\(time)Z")!
            let result = Vienna.nextRefresh(after: input)
            let output = parse.string(from: result)
            XCTAssertTrue(output.contains(next))
            XCTAssertGreaterThan(result, input)
        }
    }
    func testGapsAreNotConnectedAndUncertaintyIsPreserved() {
        let start = Vienna.chartRange("2026-10-23").lowerBound
        let readings = [0.0, 300, 1800].map { offset in Reading(locationId: 262, title: "Gym", capacity: 20, recordedAt: start.addingTimeInterval(offset)) }
        let forecast = LocationForecast(locationId: 262, title: "Gym", status: "ok", reason: nil,
            points: [.init(capacity: 30, p10: 10, p90: 50, recordedAt: start.addingTimeInterval(2100))])
        let points = GraphData.points(gym: 262, readings: readings, forecast: forecast, range: Vienna.chartRange("2026-10-23"))
        XCTAssertEqual(points.count, 5)
        XCTAssertEqual(points[0].segment, points[1].segment)
        XCTAssertNotEqual(points[1].segment, points[2].segment)
        XCTAssertTrue(points[3].predicted)
        XCTAssertNil(points[3].lower)
        XCTAssertEqual(points[4].lower, 10)
        XCTAssertEqual(points[4].upper, 50)
        let missing = GraphData.points(gym: 262, readings: Array(readings.prefix(1)), forecast: forecast, range: Vienna.chartRange("2026-10-23"))
        XCTAssertEqual(missing.count, 2) // No connector across a 35-minute outage.
    }
    func testYesterdayForecastIsNeverUsedForToday() {
        let yesterday = Vienna.date("2026-10-22")!
        let snapshot = DemoData.snapshot(now: yesterday.addingTimeInterval(12 * 3600))
        XCTAssertNil(snapshot.prediction(262, now: Vienna.addingDays(1, to: yesterday)))
        XCTAssertNotNil(snapshot.prediction(262, now: yesterday))
    }
    func testOptionalPredictionFailureDoesNotHideRecordedData() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [TestURLProtocol.self]
        let api = APIClient(baseURL: URL(string: "https://example.test")!, session: URLSession(configuration: configuration))
        let snapshot = try await api.dashboard(now: Vienna.date("2026-10-23")!)
        XCTAssertEqual(snapshot.live.count, 1)
        XCTAssertEqual(snapshot.readings.count, 1)
        XCTAssertNil(snapshot.forecast)
        XCTAssertNotNil(snapshot.forecastError)
    }
}

final class TestURLProtocol: URLProtocol, @unchecked Sendable {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let path = request.url!.path
        let status = path == "/prediction" ? 503 : 200
        let body: String
        if path == "/live" { body = #"[{"id":262,"title":"Gym","url":"https://example.org","capacity":27,"recorded_at":"2026-10-23T10:00:00Z"}]"# }
        else if path == "/history" {
            assert(URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems == [URLQueryItem(name: "date", value: "2026-10-23")])
            body = #"[{"location_id":262,"title":"Gym","capacity":27,"recorded_at":"2026-10-23T10:00:00Z"}]"#
        } else { body = "{}" }
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8)); client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}
