package dev.flofriday.boulderbat

import android.graphics.Bitmap
import android.graphics.Canvas
import android.view.View
import android.widget.FrameLayout
import android.widget.RemoteViews
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.flofriday.boulderbat.data.*
import dev.flofriday.boulderbat.widget.*
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.time.Instant
import java.time.LocalDate
import kotlin.math.*

@RunWith(AndroidJUnit4::class)
class WidgetRenderingTest {
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    @Test fun selectionsAreIndependentAndEditingPersists() {
        val prefs = WidgetPreferences(context)
        val first = 900001; val second = 900002
        try {
            prefs.save(first, 262, PRODUCTION_SERVER)
            prefs.save(second, 284, "https://example.com")
            assertEquals(262, prefs.get(first)?.gym?.id); assertEquals(284, prefs.get(second)?.gym?.id)
            prefs.save(first, 265, PRODUCTION_SERVER)
            assertEquals(265, WidgetPreferences(context).get(first)?.gym?.id)
            assertEquals(284, WidgetPreferences(context).get(second)?.gym?.id)
            assertEquals("https://example.com", prefs.get(second)?.server)
        } finally { prefs.remove(first); prefs.remove(second) }
    }
    @Test fun renderAllSizesAndRemoteViewsWithForecastFixtures() {
        val day = LocalDate.of(2026, 10, 23)
        val now = day.atTime(15, 16).atZone(Vienna.zone).toInstant()
        fun value(hour: Double) = (sin((hour - 8) / 16 * PI).coerceAtLeast(0.0).pow(2) * 48)
        val readings = (0..29).map { index ->
            Reading(262, value(8 + index / 4.0), Vienna.start(day).plusSeconds(index * 900L))
        }
        val points = (0..35).map { index ->
            val at = now.plusSeconds(index * 900L).coerceAtMost(Vienna.end(day).minusSeconds(1))
            val capacity = value(15.2667 + index / 4.0)
            ForecastPoint(capacity, max(0.0, capacity - 10), min(100.0, capacity + 16), at)
        }.distinctBy { it.recordedAt }
        val snapshot = Snapshot(now, day, listOf(LiveReading(262, readings.last().capacity, now.minusSeconds(60), "https://boulderbar.net")),
            readings, Forecast(day, Vienna.end(day).minusSeconds(1), listOf(LocationForecast(262, "ok", null, points))))
        val dir = File(context.cacheDir, "widget-previews").apply { mkdirs() }
        listOf(180 to 180, 360 to 180, 360 to 340).forEach { (w, h) ->
            val bitmap = WidgetRenderer.render(Gym.all.first(), snapshot, w, h, 2f, now)
            assertEquals(w * 2, bitmap.width); assertEquals(h * 2, bitmap.height)
            val name = if (w == h) "small" else if (h < 200) "medium" else "large"
            File(dir, "widget-$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
            // Exercise the platform's RemoteViews inflation and bitmap transfer too.
            InstrumentationRegistry.getInstrumentation().runOnMainSync {
                val remote = RemoteViews(context.packageName, R.layout.gym_widget)
                remote.setImageViewBitmap(R.id.widget_image, bitmap)
                val host = FrameLayout(context)
                val view = remote.apply(context, host)
                view.measure(View.MeasureSpec.makeMeasureSpec(w * 2, View.MeasureSpec.EXACTLY), View.MeasureSpec.makeMeasureSpec(h * 2, View.MeasureSpec.EXACTLY))
                view.layout(0, 0, w * 2, h * 2)
                val output = Bitmap.createBitmap(w * 2, h * 2, Bitmap.Config.ARGB_8888)
                view.draw(Canvas(output))
                assertNotEquals(0, output.getPixel(w, h))
            }
        }
        // Expiry and missing readings must also produce a valid, explicitly stale widget.
        val stale = WidgetRenderer.render(Gym.all.first(), snapshot, 360, 180, 2f, Vienna.end(day).plusSeconds(60))
        File(dir, "widget-stale.png").outputStream().use { stale.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }
}
