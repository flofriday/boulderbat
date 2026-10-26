# Boulderbat for Android

Native Kotlin, Jetpack Compose / Material 3, and Android home-screen widgets for
Android 8.0 (API 26) and later. Phones and tablets share the same app; wide windows
use a navigation rail and multiple live-card columns. Forecasting stays on the
existing server—there is no model or Python runtime on the device.

## Open and build

Open this `android/` directory in Android Studio and let Gradle sync. Use Studio's
bundled JDK (17 or newer) and install Android SDK 36. Create `local.properties` with
your SDK location if Studio doesn't create it automatically:

```properties
sdk.dir=/path/to/Android/sdk
```

The checked-in wrapper pins Gradle 9.4.1; AGP 9.2.1 provides built-in Kotlin, with
the matching Kotlin 2.2.10 Compose compiler. AndroidX versions are pinned too.

```sh
./gradlew assembleDebug
./gradlew testDebugUnitTest lintDebug
./gradlew connectedDebugAndroidTest
./gradlew assembleRelease
```

Debug APK: `app/build/outputs/apk/debug/app-debug.apk` (development signed).
Release APK: `app/build/outputs/apk/release/app-release-unsigned.apk` (optimized with
R8, **unsigned**). Configure your own release signing in Studio before distributing.
Debug uses `dev.flofriday.boulderbat.debug`; Release uses `dev.flofriday.boulderbat`.
No API keys, paid libraries, account, or location permission are required.

## Screens

- **Live:** all eight gyms, current recorded occupancy, status pills, today's
  recorded/forecast graphs, and 80% uncertainty bands. Tap a card for history.
- **History:** date-only navigation up to today, All / Wien / individual locations,
  08:00–midnight graphs, a Now marker, and touch selection showing exact recorded
  values or forecast bounds. Gaps longer than 15 minutes remain gaps. A dot marks
  the last actual sample; recent samples connect to the dashed forecast.
- **Typical week:** the web app's pale-yellow-to-red heatmap, gym picker, sample
  counts, and cell details. Tap a cell to inspect its average and observation count.
- **Settings:** custom API server and live widget previews. Production defaults to
  `https://boulderbat.flofriday.dev`. All dates and chart times use Europe/Vienna.

The app refreshes once a minute while visible and supports manual refresh. Failed
forecast requests preserve recorded data. Cached readings are shown after network
failures and marked when stale. Yesterday's or expired forecasts are never included
when rendering a chart. No network failure substitutes demo data.

Release permits HTTPS only. Debug additionally permits HTTP for `10.0.2.2`, localhost,
and `127.0.0.1`; `10.0.2.2` reaches the host machine from an Android emulator. The
configured server must provide `/live`, `/history?date=YYYY-MM-DD`, `/prediction`,
and `/typical-week?location_id=…`.

## Widgets

Use **Settings → choose a gym → Add widget**, then confirm in the launcher. You can
also long-press the home screen and select **Widgets → Boulderbat → Gym**. Each
instance stores its own gym and server. The pencil button opens **Edit gym**; launchers
supporting widget reconfiguration also expose it on long-press.

Resize the widget for small, wide, or large layouts. Larger layouts include a
top-right status pill; the large graph includes percentage axes. Solid recorded
lines, the last-sample dot, dashed predictions, and the central 80% interval match
the app. Tap the graph to open the selected gym's history. No update-time labels
are shown; stale readings and previous dates have short notices.

Widgets use native RemoteViews with a bitmap produced by the **same Canvas chart
renderer as the app**. This supports real forecast graphs on Android launchers
without embedding a browser. The bitmap has an accessibility description containing
the gym, actual capacity, recording time/date, and graph explanation.

One WorkManager job requests refreshes every 15 minutes, initially aligned with
the next `:01`, `:16`, `:31`, or `:46` boundary. Widgets sharing a server share a
single fetch and disk snapshot. Configuration, resizing, and app refreshes update
widgets too. Android controls actual execution: Doze, battery restrictions, and
launcher behavior can delay it. These are static launcher snapshots; if a refresh
is deferred across midnight, the old bitmap remains until Android permits another
update. At the next render, day/expiry guards remove its forecast and identify old data.

`screenshots/index.html` compares the exact native-rendered widget layouts without
installing the app. Its images use explicit test fixtures, not current occupancy.
Settings previews use the current network/cache snapshot instead.

## Tests and implementation

`CoreTest` checks Vienna dates/DST, refresh boundaries, missing observations,
forecast connectors, gym/date isolation, expiry, JSON decoding, server validation,
and HTTP/malformed forecast failures. `WidgetRenderingTest` checks independent
instance preferences, edits, all widget sizes, and real RemoteViews inflation.
Tests make no production writes.

The instrumented renderer writes PNGs to the debug app's `cache/widget-previews/`.
To export them before Gradle uninstalls the tested app, run the installed test APK
directly and pull the output:

```sh
./gradlew assembleDebug assembleDebugAndroidTest
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb install -r app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
adb shell am instrument -w dev.flofriday.boulderbat.debug.test/androidx.test.runner.AndroidJUnitRunner
adb exec-out run-as dev.flofriday.boulderbat.debug cat cache/widget-previews/widget-medium.png > screenshots/widget-medium.png
```

Keep app/server test data separate when testing custom endpoints. Widgets currently
use the same fixed eight-location catalog as the Apple app. Wear OS, Android TV,
Play Store distribution, and real-device battery/launcher testing are separate work.
