import SwiftUI
import WidgetKit
import AppKit

@main
struct RenderWidgets {
    @MainActor static func main() throws {
        let directory = CommandLine.arguments.dropFirst().first ?? "/private/tmp/boulderbat-widget-previews"
        try FileManager.default.createDirectory(atPath: directory, withIntermediateDirectories: true)
        let now = Vienna.date("2026-10-23")!.addingTimeInterval(15 * 3600 + 16 * 60)
        let snapshot = DemoData.snapshot(now: now)
        let entry = CapacityEntry(date: now, gym: Gym.all[0], snapshot: snapshot, isPreview: true)
        let sizes: [(String, WidgetFamily)] = [("small", .systemSmall), ("medium", .systemMedium), ("large", .systemLarge)]
        for (name, family) in sizes {
            let view = CapacityWidgetLayoutPreview(entry: entry, family: family)
            try render(view, to: URL(fileURLWithPath: directory).appendingPathComponent("widget-\(name).png"))
            print("Rendered \(name) widget")
        }
        let comparison = HStack(alignment: .top, spacing: 20) {
            VStack(alignment: .trailing, spacing: 20) {
                CapacityWidgetLayoutPreview(entry: entry, family: .systemMedium)
                CapacityWidgetLayoutPreview(entry: entry, family: .systemSmall)
            }
            CapacityWidgetLayoutPreview(entry: entry, family: .systemLarge)
        }.padding(24).background(Color(hex: 0x1C2228))
        try render(comparison, to: URL(fileURLWithPath: directory).appendingPathComponent("widget-gallery.png"))
        try render(CapacityWidgetLayoutPreview(entry: entry, family: .systemMedium, renderingMode: .accented),
                   to: URL(fileURLWithPath: directory).appendingPathComponent("widget-monochrome-layout.png"))
        let gallery = """
        <!doctype html>
        <html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
        <title>Boulderbat widget previews</title>
        <style>
        body { margin: 0; padding: 32px; background: #1c2228; color: #f2f4f6; font: 16px system-ui; }
        h1 { font-size: 24px; margin: 0 0 8px; } p { color: #b6c1cb; max-width: 65ch; line-height: 1.5; }
        main { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 32px; margin-top: 28px; }
        figure { margin: 0; } img { display: block; max-width: 100%; height: auto; }
        figcaption { color: #b6c1cb; margin: 12px 0; } a { color: inherit; }
        </style>
        <h1>Boulderbat widgets</h1>
        <p>Rendered from the actual SwiftUI views. These are fixed sample readings, not live occupancy.
        No app installation is needed. System tinting and WidgetKit refresh behavior require host testing.</p>
        <main>
        <figure><a href="widget-small.png"><img src="widget-small.png" width="170" height="170" alt="Small occupancy widget"></a><figcaption>Small</figcaption></figure>
        <figure><a href="widget-medium.png"><img src="widget-medium.png" width="360" height="170" alt="Medium occupancy widget"></a><figcaption>Medium</figcaption></figure>
        <figure><a href="widget-large.png"><img src="widget-large.png" width="360" height="380" alt="Large occupancy widget"></a><figcaption>Large</figcaption></figure>
        <figure><a href="widget-monochrome-layout.png"><img src="widget-monochrome-layout.png" width="360" height="170" alt="Monochrome layout with translucent status pill"></a><figcaption>Monochrome layout approximation</figcaption></figure>
        </main></html>
        """
        try gallery.write(to: URL(fileURLWithPath: directory).appendingPathComponent("index.html"), atomically: true, encoding: .utf8)
    }
    @MainActor private static func render<V: View>(_ view: V, to url: URL) throws {
        let renderer = ImageRenderer(content: view)
        renderer.scale = 2
        guard let image = renderer.cgImage,
              let data = NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:]) else {
            throw NSError(domain: "WidgetRender", code: 1)
        }
        try data.write(to: url)
    }
}
