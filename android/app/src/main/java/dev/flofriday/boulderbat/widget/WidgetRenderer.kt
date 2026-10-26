package dev.flofriday.boulderbat.widget

import android.graphics.*
import android.text.TextPaint
import android.text.TextUtils
import dev.flofriday.boulderbat.data.*
import dev.flofriday.boulderbat.ui.CapacityChartRenderer
import java.time.Instant
import java.time.format.DateTimeFormatter

object WidgetRenderer {
    fun render(gym: Gym, snapshot: Snapshot?, widthDp: Int, heightDp: Int, scale: Float,
               now: Instant = Instant.now()): Bitmap {
        val w = widthDp.toFloat(); val h = heightDp.toFloat()
        val bitmap = Bitmap.createBitmap((w * scale).toInt().coerceAtLeast(1), (h * scale).toInt().coerceAtLeast(1), Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap); canvas.scale(scale, scale)
        val paint = Paint(Paint.ANTI_ALIAS_FLAG)
        val background = RectF(0f, 0f, w, h)
        paint.shader = LinearGradient(0f, 0f, w, h, intArrayOf(0xFF292F33.toInt(), 0xFF111719.toInt()), null, Shader.TileMode.CLAMP)
        canvas.drawRoundRect(background, 26f, 26f, paint); paint.shader = null
        val wide = w >= 280; val large = wide && h >= 260
        val live = snapshot?.live(gym.id)
        val day = snapshot?.day ?: Vienna.day(now)
        val stale = snapshot?.let { it.isStale(now) || it.isReadingStale(gym.id, now) } ?: true
        val series = listOf(GraphData.series(gym, day, snapshot?.readings.orEmpty(), snapshot?.forecast(gym.id, now)))
        val warning = when { day != Vienna.day(now) -> day.format(DateTimeFormatter.ofPattern("d MMM")); stale && live != null -> "Saved reading"; live == null -> "No readings"; else -> null }
        val chartBottom = h - if (warning != null) 28 else 12
        val chartBounds = when {
            large -> RectF(12f, 144f, w - 40, chartBottom)
            wide -> RectF(w * 0.36f, 48f, w - 12, chartBottom)
            else -> RectF(14f, minOf(88f, h * 0.5f), w - 14, chartBottom)
        }
        CapacityChartRenderer.draw(canvas, chartBounds, day, series, now, !large, true, 1f)
        fun text(value: String, x: Float, baseline: Float, size: Float, color: Int, bold: Boolean = false, maxWidth: Float = w - x - 16) {
            val p = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
                this.color = color; textSize = size
                typeface = Typeface.create("sans-serif", if (bold) Typeface.BOLD else Typeface.NORMAL)
            }
            canvas.drawText(TextUtils.ellipsize(value, p, maxWidth, TextUtils.TruncateAt.END).toString(), x, baseline, p)
        }
        text(gym.title, 18f, 30f, if (wide) 17f else 15f, Color.WHITE, true, if (wide && !stale) w - 118 else w - 36)
        if (wide) text(gym.provider, 18f, 48f, 12f, 0xFFA8B1B6.toInt())
        text(live?.let { "${it.capacity.toInt()}%" } ?: "—", 18f,
            if (large) 122f else if (wide) h - 30f else minOf(80f, h * 0.48f),
            if (wide) 48f else 36f, Color.WHITE, true,
            if (wide && !large) w * 0.36f - 18 else w - 36)
        if (wide && live != null && !stale) {
            val label = occupancyLabel(live.capacity)
            val quiet = live.capacity < 40
            paint.color = if (quiet) 0xFF203D34.toInt() else 0xFF49392C.toInt()
            canvas.drawRoundRect(RectF(w - 100, 16f, w - 16, 44f), 14f, 14f, paint)
            text(label, w - 88, 34f, 12f, if (quiet) 0xFF58D6A3.toInt() else 0xFFFFD46E.toInt(), true, 70f)
        }
        warning?.let { text(it, 18f, h - 10f, 10f, 0xFFCED6DB.toInt()) }
        return bitmap
    }
}
