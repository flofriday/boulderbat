package dev.flofriday.boulderbat.ui

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.view.MotionEvent
import android.view.View
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import dev.flofriday.boulderbat.data.*
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import kotlin.math.abs

/** The same native Canvas renderer draws the interactive app charts and widget bitmaps. */
object CapacityChartRenderer {
    fun draw(canvas: Canvas, bounds: RectF, day: LocalDate, series: List<GraphSeries>,
             now: Instant, compact: Boolean, dark: Boolean, scale: Float, selected: Instant? = null) {
        val paint = Paint(Paint.ANTI_ALIAS_FLAG)
        val muted = if (dark) Color.rgb(161, 171, 178) else Color.rgb(84, 100, 119)
        val grid = if (dark) 0x263E4B52 else 0xFFE5EAF0.toInt()
        val left = bounds.left + if (compact) 2 * scale else 38 * scale
        val top = bounds.top + 8 * scale
        val right = bounds.right - 6 * scale
        val bottom = bounds.bottom - 22 * scale
        if (right <= left || bottom <= top) return
        val start = Vienna.start(day); val end = Vienna.end(day)
        val seconds = Duration.between(start, end).seconds.toDouble()
        fun x(at: Instant) = left + (Duration.between(start, at).toMillis() / 1000.0 / seconds * (right - left)).toFloat()
        fun y(value: Double) = bottom - (value / 100 * (bottom - top)).toFloat()
        paint.textSize = 10 * scale
        paint.typeface = android.graphics.Typeface.create("sans-serif-medium", android.graphics.Typeface.NORMAL)
        if (!compact) {
            for (value in listOf(0, 25, 50, 75, 100)) {
                paint.color = grid; paint.strokeWidth = scale; paint.pathEffect = DashPathEffect(floatArrayOf(3 * scale, 4 * scale), 0f)
                canvas.drawLine(left, y(value.toDouble()), right, y(value.toDouble()), paint)
                paint.pathEffect = null; paint.color = muted; paint.textAlign = Paint.Align.RIGHT
                canvas.drawText("$value%", left - 7 * scale, y(value.toDouble()) + 3 * scale, paint)
            }
        }
        val hours = if (compact) listOf(8, 14, 20) else listOf(8, 12, 16, 20, 24)
        hours.forEach { hour ->
            val at = if (hour == 24) end else day.atTime(hour, 0).atZone(Vienna.zone).toInstant()
            paint.color = muted; paint.textAlign = when (hour) { 8 -> Paint.Align.LEFT; 24 -> Paint.Align.RIGHT; else -> Paint.Align.CENTER }
            canvas.drawText(if (hour == 24) "00:00" else "%02d:00".format(hour), x(at), bounds.bottom - 4 * scale, paint)
        }
        canvas.save(); canvas.clipRect(left - scale, top, right + scale, bottom + 3 * scale)
        series.forEach { line ->
            val color = line.gym.color.toInt()
            line.predicted.forEach { segment ->
                val points = segment.filter { it.lower != null && it.upper != null }
                if (points.size > 1) {
                    val path = Path().apply {
                        moveTo(x(points.first().at), y(points.first().upper!!))
                        points.drop(1).forEach { lineTo(x(it.at), y(it.upper!!)) }
                        points.reversed().forEach { lineTo(x(it.at), y(it.lower!!)) }; close()
                    }
                    paint.style = Paint.Style.FILL; paint.color = color; paint.alpha = if (dark) 30 else 24
                    canvas.drawPath(path, paint); paint.alpha = 255
                }
            }
            fun stroke(segments: List<List<GraphPoint>>, predicted: Boolean) {
                paint.color = color; paint.style = Paint.Style.STROKE; paint.strokeWidth = (if (compact) 1.8f else 2.2f) * scale
                paint.strokeJoin = Paint.Join.ROUND; paint.strokeCap = Paint.Cap.ROUND
                paint.pathEffect = if (predicted) DashPathEffect(floatArrayOf(5 * scale, 4 * scale), 0f) else null
                segments.forEach { segment ->
                    val path = Path()
                    segment.forEachIndexed { index, point ->
                        if (index == 0) path.moveTo(x(point.at), y(point.value)) else path.lineTo(x(point.at), y(point.value))
                    }
                    canvas.drawPath(path, paint)
                    if (segment.size == 1) { paint.style = Paint.Style.FILL; canvas.drawCircle(x(segment[0].at), y(segment[0].value), 2 * scale, paint); paint.style = Paint.Style.STROKE }
                }
                paint.pathEffect = null
            }
            stroke(line.recorded, false); stroke(line.predicted, true)
            line.lastRecorded?.let {
                paint.style = Paint.Style.FILL; paint.color = color
                canvas.drawCircle(x(it.at), y(it.value), 2.8f * scale, paint)
            }
        }
        if (day == Vienna.day(now) && now >= start && now < end) {
            paint.color = muted; paint.strokeWidth = scale; paint.pathEffect = DashPathEffect(floatArrayOf(3 * scale, 4 * scale), 0f)
            canvas.drawLine(x(now), top, x(now), bottom, paint); paint.pathEffect = null
            if (!compact) { paint.textAlign = Paint.Align.LEFT; paint.textSize = 10 * scale; canvas.drawText("Now", (x(now) + 4 * scale).coerceAtMost(right - 24 * scale), top + 12 * scale, paint) }
        }
        selected?.let {
            paint.color = muted; paint.strokeWidth = scale
            canvas.drawLine(x(it), top, x(it), bottom, paint)
        }
        canvas.restore()
    }
}

class CapacityChartView(context: Context) : View(context) {
    private val chartBounds = RectF()
    var day: LocalDate = Vienna.day()
    var series: List<GraphSeries> = emptyList()
    var now: Instant = Instant.now()
    var compact = false
    var dark = false
    var selected: Instant? = null
    var selectionChanged: ((Instant) -> Unit)? = null
    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        chartBounds.set(0f, 0f, width.toFloat(), height.toFloat())
        CapacityChartRenderer.draw(canvas, chartBounds, day, series, now,
            compact, dark, resources.displayMetrics.density, selected)
    }
    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (compact || selectionChanged == null) return false
        if (event.action == MotionEvent.ACTION_DOWN || event.action == MotionEvent.ACTION_MOVE) {
            val scale = resources.displayMetrics.density
            val fraction = ((event.x - 38 * scale) / (width - 44 * scale)).coerceIn(0f, 1f)
            val instant = Vienna.start(day).plusSeconds((Duration.between(Vienna.start(day), Vienna.end(day)).seconds * fraction).toLong())
            val point = series.flatMap { it.recorded.flatten() + it.predicted.flatten() }
                .minByOrNull { abs(it.at.epochSecond - instant.epochSecond) }
            point?.let { selectionChanged?.invoke(it.at) }
            invalidate(); return true
        }
        if (event.action == MotionEvent.ACTION_UP) { performClick(); return true }
        return super.onTouchEvent(event)
    }
    override fun performClick(): Boolean { super.performClick(); return true }
}

@Composable
fun CapacityChart(day: LocalDate, series: List<GraphSeries>, now: Instant, modifier: Modifier,
                  compact: Boolean = false, dark: Boolean = false, selected: Instant? = null,
                  onSelection: ((Instant) -> Unit)? = null) {
    AndroidView(modifier = modifier, factory = { CapacityChartView(it) }, update = { view ->
        view.day = day; view.series = series; view.now = now; view.compact = compact; view.dark = dark
        view.selected = selected; view.selectionChanged = onSelection
        view.contentDescription = buildString {
            append("Occupancy from 08:00 to midnight, $day, Vienna time. Solid recorded, dashed predicted, shaded 80 percent range. ")
            series.forEach { line -> line.lastRecorded?.let { append("${line.gym.title}: last recorded ${it.value.toInt()} percent at ${Vienna.time(it.at)}. ") } }
        }
        view.invalidate()
    })
}
