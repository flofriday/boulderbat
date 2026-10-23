# Boulderbat for Apple platforms

Native SwiftUI + Swift Charts clients for the existing Boulderbat API. No model or
Python runtime runs on the device.

| Platform | Minimum | Experience |
| --- | --- | --- |
| iPhone / iPad | iOS / iPadOS 17 | Live cards, history, typical week, Home / Lock Screen widgets |
| Mac | macOS 14 | Native sidebar, resizable charts, desktop / Notification Center widgets |
| Apple Watch | watchOS 10 | Independent network access, live locations, daily graph and forecast, configurable complications / Smart Stack widget |
| Apple Vision Pro | visionOS 26 | Native resizable SwiftUI window and spatial widgets |

TV is intentionally excluded: this is a personal, glanceable occupancy tool.

## Open and run

Open **Boulderbat.xcodeproj**, select **Boulderbat**, then choose My Mac, an iPhone,
iPad, or Vision Pro destination. The iOS app embeds the watch companion and its
widget extension. Use **BoulderbatWatch** to run directly on a Watch destination.

Select your own development team under Signing & Capabilities for the app and
extension targets before installing on physical devices or archiving. The bundle
IDs start with `dev.flofriday.boulderbat`. Debug builds add `.debug` to keep their
widget registrations separate from the installed Release app. Change the shared
`BOULDERBAT_APP_BUNDLE_IDENTIFIER` setting if needed; companion IDs follow it.
No App Groups, API keys, paid dependencies, or third-party SDKs are required.

Production (`https://boulderbat.flofriday.dev`) is the default server. Change it in
Settings, or pass these launch arguments in the scheme for local development:

```
--api-base-url http://127.0.0.1:8000
```

The Mac and iOS simulator can use localhost. A physical device needs a reachable
HTTPS server (or a local `.local` hostname); localhost means that device itself.
Local networking is permitted without allowing arbitrary insecure internet traffic.
The server must expose the date-based `/history?date=YYYY-MM-DD` API.

`--demo` explicitly enables deterministic preview data for design work. Network
failures never silently substitute demo data.

## Features

- Stocks-inspired live cards: large occupancy, status, recorded sparkline, dashed
  forecast and an 80% interval. Tap a location to open its history.
- History: native date picker and day navigation; all / Vienna / individual gym
  selection; 08:00–midnight charts, chart selection and interval details. Predictions
  appear only for today. Missing periods longer than 15 minutes remain visible.
- Typical week: eight-week weekday/hour heat map with per-cell capacity and sample
  counts, location selection and an observation count.
- Manual and foreground minute refresh; cached data remains visible on network
  failures. Forecast failures preserve recorded occupancy. API responses are
  validated and decoded using UTC timestamps; all displayed times use Vienna.
- Keyboard refresh on Mac, Dynamic Type, native accessibility and light/dark support.

## Widgets

Add **Gym** under Boulderbat in the system widget gallery. Edit the widget to select
any of the eight locations. Each widget can also specify its API server, so local
widget testing doesn't require a shared App Group or signing entitlement.

Small, medium, and large widgets show the current *recorded* capacity with history
and forecast; the large version includes axes. The medium graph uses the full widget
height behind the header. Larger sizes have a status pill at the top right, with
a solid dark background in full color and translucent styling in glass/tinted mode;
the small widget keeps only the title, occupancy, and chart when
data is fresh. A dot marks the last recorded sample, before the dashed forecast.
Lock Screen
and watch accessory families provide compact capacity / graph views. Tapping a
widget opens that gym's history via `boulderbat://history?gym=262` (Debug uses
`boulderbat-debug`). The location parameter uses string options because the current
SDK's AppEnum decoding discarded saved selections. Both legacy gym IDs and current
display names remain supported.
The system-hosted widget editor uses the system accent rather than the app's yellow,
so location selections stay readable on its light gray form rows.

Widgets fetch their own data and retain a disk cache in their extension container.
They request a reload at the next `:01`, `:16`, `:31`, or `:46` boundary (with at
least five minutes between requests). **WidgetKit controls the actual refresh
schedule**, particularly on battery; this isn't a promise of minute-level updates.
Reading timestamps are available to accessibility without visible update-time labels.
All sizes mark cached/stale data with a short status such as “Saved data”. Timeline entries
pre-schedule stale labels and remove forecasts at local midnight even if the next
network refresh is deferred. Forecasts are
never displayed for a different local day. Forecast values are never presented as
live observations.

For watchOS 10/11, the widget provider offers preconfigured recommendations for
each location; newer systems can edit App Intent widget parameters directly.

To inspect without installing, open `App/WidgetLayoutPreviews.swift` in Xcode and
choose **Editor → Canvas**, then Resume. On Mac, the **Small layout**, **Medium layout**,
and **Large layout** tabs render the actual SwiftUI views without a widget host. With
an iOS destination, `Widgets/BoulderbatWidgets.swift` also offers three WidgetKit
previews that exercise system containers.
The macOS layout previews don't verify system tinting, configuration, or refresh behavior.

You can also open `Screenshots/index.html` in a browser to compare all three sizes.
The checked-in widget screenshots are **preview fixtures**, not live occupancy.
To render all three desktop/Home Screen sizes from the actual shared views:

```sh
xcrun swiftc -D WIDGET_PREVIEW Shared/*.swift Widgets/*.swift Tools/RenderWidgets.swift -o /tmp/boulderbat-render-widgets
/tmp/boulderbat-render-widgets /tmp/boulderbat-widget-previews
```

This also writes `index.html` into the output directory for a local preview gallery.
The monochrome preview approximates system color remapping, not the actual glass host.

To verify all location mappings and three real API selections:

```sh
xcrun swiftc -D WIDGET_PREVIEW Shared/*.swift Widgets/*.swift Tools/VerifyWidgetSelection.swift -o /tmp/boulderbat-verify-selection
/tmp/boulderbat-verify-selection
```

## Build and test

The shared Foundation / chart code is also a dependency-free Swift package:

```sh
swift test
xcodebuild -project Boulderbat.xcodeproj -scheme Boulderbat -destination 'generic/platform=macOS' CODE_SIGNING_ALLOWED=NO build
xcodebuild -project Boulderbat.xcodeproj -scheme Boulderbat -destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO build
xcodebuild -project Boulderbat.xcodeproj -scheme Boulderbat -destination 'generic/platform=visionOS Simulator' CODE_SIGNING_ALLOWED=NO build
```

Unit tests cover JSON contracts, partial forecast failure, Vienna dates and DST,
shifted refresh boundaries, graph gaps, uncertainty bounds, and forecast date
isolation. Physical-device signing, distribution, and widget installation still
require your Apple development account and device setup.

For a locally signed macOS Release build suitable for desktop widget testing:

```sh
xcodebuild -project Boulderbat.xcodeproj -scheme Boulderbat -configuration Release -destination 'generic/platform=macOS' -derivedDataPath /tmp/boulderbat-release-build CODE_SIGN_IDENTITY=- CODE_SIGN_STYLE=Manual CODE_SIGNING_ALLOWED=YES build
```

This uses ad-hoc signing; distribution still needs appropriate signing and notarization.

`generate_project.py` reproducibly generates the checked-in Xcode project using
Python's standard library. Run it after adding Swift source files in the known
source directories; opening/building the checked-in project doesn't need Python.
