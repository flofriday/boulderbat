import SwiftUI
import WidgetKit

@main
struct BoulderbatApp: App {
    @State private var store = AppStore()
    init() {
        // A newly installed build should replace the previous widget timelines.
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "0"
        if UserDefaults.standard.string(forKey: "widgetBuildVersion") != version {
            WidgetCenter.shared.reloadTimelines(ofKind: "BoulderbatCapacity")
            UserDefaults.standard.set(version, forKey: "widgetBuildVersion")
        }
    }
    var body: some Scene {
        WindowGroup {
            RootView().environment(store)
                .frame(minWidth: minimumWidth, minHeight: minimumHeight)
        }
        #if os(macOS)
        .defaultSize(width: 1120, height: 820)
        .commands { CommandGroup(after: .newItem) { Button("Refresh", systemImage: "arrow.clockwise") { Task { await store.refresh() } }.keyboardShortcut("r", modifiers: .command) } }
        #endif
    }
    private var minimumWidth: CGFloat? {
        #if os(macOS)
        760
        #else
        nil
        #endif
    }
    private var minimumHeight: CGFloat? {
        #if os(macOS)
        600
        #else
        nil
        #endif
    }
}

enum AppTab: String, CaseIterable, Identifiable {
    case live, history, week
    var id: String { rawValue }
    var title: String { switch self { case .live: "Live"; case .history: "History"; case .week: "Typical week" } }
    var symbol: String { switch self { case .live: "waveform.path.ecg"; case .history: "scroll"; case .week: "tablecells" } }
}

struct RootView: View {
    @Environment(AppStore.self) private var store
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.colorScheme) private var colorScheme
    @State private var tab: AppTab = .live
    @State private var selectedGym = 262
    @State private var selectedDate = Date.now
    @State private var settings = false
    var body: some View {
        Group {
            #if os(macOS) || os(visionOS)
            NavigationSplitView {
                List(AppTab.allCases) { item in
                    Button { tab = item } label: { Label(item.title, systemImage: item.symbol).frame(maxWidth: .infinity, alignment: .leading) }
                        .buttonStyle(.plain).padding(.vertical, 4)
                        .listRowBackground(tab == item ? BatStyle.yellow.opacity(0.16) : Color.clear)
                        .accessibilityAddTraits(tab == item ? .isSelected : [])
                }
                    .navigationTitle("Boulderbat")
                    .navigationSplitViewColumnWidth(min: 180, ideal: 210)
            } detail: { NavigationStack { content.navigationTitle(tab.title).toolbar { toolbar } } }
            #else
            TabView(selection: $tab) {
                ForEach(AppTab.allCases) { item in
                    NavigationStack { panel(item).navigationTitle(item.title).toolbar { toolbar } }
                        .tabItem { Label(item.title, systemImage: item.symbol) }.tag(item)
                }
            }
            #endif
        }
        .tint(colorScheme == .dark ? BatStyle.yellow : Color(hex: 0x8F6500))
        .sheet(isPresented: $settings) { SettingsView().environment(store) }
        .task(id: scenePhase) {
            guard scenePhase == .active else { return }
            while !Task.isCancelled {
                await store.refresh()
                do { try await Task.sleep(for: .seconds(60)) } catch { break }
            }
        }
        .onOpenURL { url in
            guard url.scheme == AppIdentity.urlScheme else { return }
            let params = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
            if let value = params.first(where: { $0.name == "gym" })?.value, let gym = Int(value), Gym.all.contains(where: { $0.id == gym }) { selectedGym = gym }
            if let value = params.first(where: { $0.name == "date" })?.value, let date = Vienna.date(value), date <= .now { selectedDate = date }
            else { selectedDate = .now }
            tab = .history
        }
    }
    private var content: some View { panel(tab) }
    @ViewBuilder private func panel(_ tab: AppTab) -> some View {
        switch tab {
        case .live: LiveScreen { gym in selectedGym = gym; selectedDate = .now; self.tab = .history }
        case .history: HistoryScreen(selectedGym: $selectedGym, selectedDate: $selectedDate)
        case .week: WeekScreen(selectedGym: $selectedGym)
        }
    }
    @ToolbarContentBuilder private var toolbar: some ToolbarContent {
        ToolbarItemGroup(placement: .automatic) {
            Button { Task { await store.refresh() } } label: { Image(systemName: "arrow.clockwise") }
                .help("Refresh occupancy").disabled(store.refreshing)
            Button { settings = true } label: { Image(systemName: "gearshape") }.help("Settings")
        }
    }
}

struct SettingsView: View {
    @Environment(AppStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var server = ""
    var body: some View {
        NavigationStack {
            Form {
                Section("Data source") {
                    TextField("API base URL", text: $server)
                        .autocorrectionDisabled()
                    Text("All chart times use Europe/Vienna. The app uses the same public API as the website; forecasting runs on the server.").font(.caption).foregroundStyle(.secondary)
                    Button("Use production server") { server = APIClient.production.absoluteString }
                }
                Section("About") {
                    Link("API documentation", destination: store.api.baseURL.appendingPathComponent("docs"))
                    Link("Source code", destination: URL(string: "https://github.com/flofriday/boulderbat")!)
                    Text("Widgets can use their own server URL in Edit Widget. Widget refresh timing is managed by the system.").font(.caption).foregroundStyle(.secondary)
                }
            }
            .formStyle(.grouped).navigationTitle("Settings")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { Task { await store.changeServer(server) }; dismiss() }
                        .disabled(!validServer)
                }
            }
        }.frame(minWidth: 340, minHeight: 360).onAppear { server = store.server }
    }
    private var validServer: Bool {
        guard let url = URL(string: server.trimmingCharacters(in: .whitespacesAndNewlines)), let host = url.host else { return false }
        return url.scheme == "https" || (url.scheme == "http" && (host == "localhost" || host == "127.0.0.1" || host.hasSuffix(".local")))
    }
}
