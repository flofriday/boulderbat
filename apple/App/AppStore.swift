import SwiftUI
import Observation

@MainActor @Observable
final class AppStore {
    var snapshot: DashboardSnapshot?
    var loading = false
    var refreshing = false
    var error: String?
    var server: String {
        didSet { UserDefaults.standard.set(server, forKey: "apiServer") }
    }
    private var requestID = UUID()
    var api: APIClient { APIClient(baseURL: URL(string: server) ?? APIClient.production) }
    init() {
        let args = ProcessInfo.processInfo.arguments
        if let index = args.firstIndex(of: "--api-base-url"), args.indices.contains(index + 1) {
            server = args[index + 1]
        } else { server = UserDefaults.standard.string(forKey: "apiServer") ?? APIClient.production.absoluteString }
        if args.contains("--demo") { snapshot = DemoData.snapshot() }
        else { snapshot = SnapshotCache.load(server: URL(string: server) ?? APIClient.production) }
    }
    func refresh() async {
        guard !refreshing else { return }
        if ProcessInfo.processInfo.arguments.contains("--demo") { snapshot = DemoData.snapshot(); return }
        refreshing = true
        loading = snapshot == nil
        let id = UUID(); requestID = id
        let api = api
        defer { if requestID == id { refreshing = false; loading = false } }
        do {
            let value = try await api.dashboard()
            guard requestID == id, api.baseURL.absoluteString == self.api.baseURL.absoluteString else { return }
            snapshot = value; error = nil
            SnapshotCache.save(value, server: api.baseURL)
        } catch is CancellationError { }
        catch { if requestID == id { self.error = error.localizedDescription } }
    }
    func changeServer(_ value: String) async {
        requestID = UUID(); refreshing = false
        server = value.trimmingCharacters(in: .whitespacesAndNewlines)
        snapshot = SnapshotCache.load(server: api.baseURL)
        error = nil
        await refresh()
    }
}
