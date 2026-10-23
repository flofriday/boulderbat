# Native Apple app — continuation note

Updated 23 October 2026. Work paused at the user's request to wrap up.

## Latest widget fix — build 5

Build 5 follow-up: widget targets now explicitly clear the inherited global accent
color setting. The system-hosted gym selector uses its normal system accent instead
of the app's yellow (the form can be light while a dark appearance resolves the color).
The app's adaptive branding and widget graph colors are unchanged.
Build 5 is installed in Applications; its signature and compiled widget metadata
were verified. macOS Release and iOS Simulator builds (including watch targets) pass.
Reopening the system widget editor is still needed to visually confirm its tint.

Build 4 resolved the selection issue; the current locally signed build is installed
at `/Applications/Boulderbat.app`.
The Release artifact is `/private/tmp/boulderbat-release-build/Build/Products/Release/Boulderbat.app`.
The macOS Release and iOS Simulator build (including embedded watch targets) pass.

Gym selection now uses String options instead of AppEnum: native WidgetKit logs
showed saved enum selections arriving as the default or nil. String decoding
preserves both legacy identifiers and new display names. Installed provider logs
confirmed different gym IDs, and the user confirmed the heading follows selection.
`Tools/VerifyWidgetSelection.swift` checks all mappings and fetched live/history
data for Hannovergasse, St. Pölten, and Seestadt successfully.

Debug bundle IDs and deep links are separate from Release to avoid registration
collisions. The widget catalog name is Gym; the light-mode picker accent is darker.
The pill preserves opacity in glass/tinted mode. Its monochrome layout approximation
is exported alongside full-color previews; actual glass-host appearance still needs
visual confirmation. Earlier unsigned-build and installation notes below are historical.

## Later widget polish

The widgets now have larger charts, solid top-right status pills on medium and
large sizes, and no peak/legend/footer or update-time labels. Fresh small widgets
show only the location, percentage, and chart; short stale labels remain visible.
A dot marks the last recorded sample. Actual SwiftUI views
are shared between the app and extension in `Shared/CapacityWidgetView.swift`.

`Screenshots/index.html` and `Screenshots/widget-gallery.png` compare all three sizes
without installation. Regenerate them using `Tools/RenderWidgets.swift` as documented
in the README. These are sample-data renders, not live occupancy or WidgetKit host tests.

`App/WidgetLayoutPreviews.swift` adds plain SwiftUI Canvas previews for the app target.
The local Xcode Canvas currently asks for a missing watchOS 27 runtime even with
My Mac selected, so the exported gallery is the verified inspection path. Native
WidgetKit Canvas previews in the extension are limited to iOS/watchOS; macOS reports
that previewing widgets is unsupported. Resolve the Canvas destination/runtime issue
before claiming Canvas verification. The final macOS Release and iOS/watch builds pass.

## Implemented

Open `apple/Boulderbat.xcodeproj`. See `apple/README.md` for setup, build commands, and signing details.

- Native SwiftUI app for iPhone, iPad, macOS, and visionOS: Live, History, Typical week, location selection, and configurable API server.
- Stocks-inspired live cards and shared capacity charts: recorded occupancy, dashed forecasts, and the API's 80% uncertainty range.
- Watch companion with live occupancy and today's location chart.
- Configurable WidgetKit widgets, including small/medium/large charts, supported Lock Screen accessories, and watch complications/Smart Stack views.
- Widget deep links, cached/offline data, freshness labels, midnight handling, and refresh requests aligned with the backend's one-minute offset. WidgetKit controls the actual refresh schedule.
- Shared networking/models, explicit demo data, app icons, project generator, and a small Swift package test suite. No on-device forecasting or third-party Swift dependencies.

The default server is `https://boulderbat.flofriday.dev`. Demo data requires explicit `--demo`; failures do not silently substitute fixtures. Widget preview images in `apple/Screenshots/` use demo data.

## Verified

- Final unsigned Xcode builds passed for macOS, iOS Simulator, and visionOS Simulator, with no warnings/errors in the final logs. The iOS build also compiles and embeds the watch companion and watch widgets.
- Five shared Swift package tests passed, covering decoding/date boundaries, refresh timing, chart gaps and intervals, expired forecasts, and forecast-service failures preserving recorded data.
- Inspected the running Mac app against production: Live, today's History with forecasts, a previous day without forecasts, Typical week, and Settings.
- Installed and visually inspected an earlier build on an iPhone 15 Pro simulator (iOS 17.5). The history deep link opened successfully. The final build still needs reinstalling there after the last chart/widget refinements.
- Rendered and inspected the SwiftUI widget views in three sizes. This does not verify installation or timelines inside an actual WidgetKit host.
- `git diff --check` passed.

Final build logs: `/private/tmp/boulderbat-mac-final.log`, `/private/tmp/boulderbat-ios-final.log`, `/private/tmp/boulderbat-vision-final.log`.

## Continue with these checks

1. Reinstall the final iOS simulator build. Check history deep links, location selection, date navigation, chart selection, dark mode, large Dynamic Type, and iPad layouts.
2. Configure signing and install the widgets in actual macOS/iOS hosts. Verify every family, location/server configuration, deep links, offline/stale states, and midnight transitions. Confirm refresh behavior under WidgetKit's scheduling budget.
3. Test watchOS and visionOS at runtime when suitable simulator runtimes or devices are available. Builds pass, but watch pairing/complications and spatial widgets have not had runtime verification.
4. Verify a normal Xcode Run and device/archive signing. All targets currently have automatic signing with no development team selected; validation builds used `CODE_SIGNING_ALLOWED=NO`. Keep companion bundle identifiers consistent if changing the base identifier.
5. Add focused tests for app navigation/state cancellation and widget timeline freshness as needed. Current tests run through `swift test`, not an Xcode test target.
6. Review accessibility and narrow/large layouts on actual devices. The watch app currently provides a glance companion rather than the main app's full historical date navigation and weekly heatmap. The location catalog is fixed to the eight current web locations.

## Useful commands

```sh
swift test --package-path apple --scratch-path /private/tmp/boulderbat-swift-build
xcodebuild -project apple/Boulderbat.xcodeproj -scheme Boulderbat -destination 'generic/platform=macOS' -derivedDataPath /private/tmp/boulderbat-apple-build CODE_SIGNING_ALLOWED=NO build
```

The built Mac executable is `/private/tmp/boulderbat-apple-build/Build/Products/Debug/Boulderbat.app/Contents/MacOS/Boulderbat`.

## Session state and boundaries

- Xcode has the project open. The native Mac app was stopped for the final rebuild.
- The iPhone simulator may still be running the earlier installed build.
- The previous local web/backend preview was stopped; the native app was tested against production. Do not assume port 8000 currently belongs to this repository.
- Xcode MCP is now available; final Release validation used `xcodebuild`.
- No commit, push, app distribution, or production mutation was performed. Existing README edits were preserved.
