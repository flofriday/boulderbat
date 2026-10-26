package dev.flofriday.boulderbat.widget

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.res.Configuration
import android.net.Uri
import android.os.Bundle
import android.widget.RemoteViews
import androidx.work.*
import dev.flofriday.boulderbat.MainActivity
import dev.flofriday.boulderbat.R
import dev.flofriday.boulderbat.data.*
import kotlinx.coroutines.CancellationException
import java.time.Duration
import java.time.Instant
import java.util.concurrent.TimeUnit

data class WidgetConfig(val gym: Gym, val server: String)

class WidgetPreferences(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences("widgets", Context.MODE_PRIVATE)
    fun get(id: Int): WidgetConfig? {
        val gym = Gym.find(prefs.getInt("gym-$id", -1)) ?: return null
        return WidgetConfig(gym, prefs.getString("server-$id", PRODUCTION_SERVER) ?: PRODUCTION_SERVER)
    }
    fun save(id: Int, gym: Int, server: String) {
        require(Gym.find(gym) != null)
        prefs.edit().putInt("gym-$id", gym).putString("server-$id", server).apply()
    }
    fun remove(id: Int) { prefs.edit().remove("gym-$id").remove("server-$id").apply() }
}

class GymWidgetProvider : AppWidgetProvider() {
    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        WidgetWork.schedule(context); WidgetWork.refresh(context)
    }
    override fun onAppWidgetOptionsChanged(context: Context, manager: AppWidgetManager, id: Int, options: Bundle) {
        // Render the cached snapshot at the new size without waiting for a network request.
        WidgetWork.refresh(context)
    }
    override fun onDeleted(context: Context, ids: IntArray) {
        ids.forEach { WidgetPreferences(context).remove(it) }
        WidgetWork.schedule(context)
    }
    override fun onDisabled(context: Context) { WidgetWork.schedule(context) }
    override fun onRestored(context: Context, oldWidgetIds: IntArray, newWidgetIds: IntArray) {
        val prefs = WidgetPreferences(context)
        oldWidgetIds.zip(newWidgetIds).forEach { (old, new) ->
            prefs.get(old)?.let { prefs.save(new, it.gym.id, it.server) }; prefs.remove(old)
        }
        WidgetWork.refresh(context)
    }
    companion object {
        fun ids(context: Context): IntArray = AppWidgetManager.getInstance(context).getAppWidgetIds(ComponentName(context, GymWidgetProvider::class.java))
        fun renderAll(context: Context, server: String, snapshot: Snapshot?) {
            val prefs = WidgetPreferences(context)
            ids(context).forEach { id -> prefs.get(id)?.takeIf { it.server == server }?.let { render(context, id, it, snapshot) } }
        }
        fun render(context: Context, id: Int, config: WidgetConfig, snapshot: Snapshot?) {
            val manager = AppWidgetManager.getInstance(context)
            val options = manager.getAppWidgetOptions(id)
            val landscape = context.resources.configuration.orientation == Configuration.ORIENTATION_LANDSCAPE
            val width = options.getInt(if (landscape) AppWidgetManager.OPTION_APPWIDGET_MAX_WIDTH else AppWidgetManager.OPTION_APPWIDGET_MIN_WIDTH, 320).coerceIn(140, 700)
            val height = options.getInt(if (landscape) AppWidgetManager.OPTION_APPWIDGET_MIN_HEIGHT else AppWidgetManager.OPTION_APPWIDGET_MAX_HEIGHT, 180).coerceIn(130, 500)
            val scale = context.resources.displayMetrics.density.coerceAtMost(2f)
            val bitmap = WidgetRenderer.render(config.gym, snapshot, width, height, scale)
            val views = RemoteViews(context.packageName, R.layout.gym_widget)
            views.setImageViewBitmap(R.id.widget_image, bitmap)
            val live = snapshot?.live(config.gym.id)
            views.setContentDescription(R.id.widget_image, "${config.gym.title}: " + (live?.let {
                "${it.capacity.toInt()} percent recorded at ${Vienna.time(it.recordedAt)}, ${snapshot.day}. "
            } ?: "No readings. ") + "Today's occupancy graph, dashed forecast and shaded 80 percent range. Tap for history.")
            val history = Intent(context, MainActivity::class.java)
                .setData(Uri.parse("boulderbat://history?gym=${config.gym.id}&widget=$id"))
                .putExtra("widget_server", config.server)
                .setFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            views.setOnClickPendingIntent(R.id.widget_image, PendingIntent.getActivity(context, id, history, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE))
            val edit = Intent(context, WidgetConfigureActivity::class.java)
                .setData(Uri.parse("boulderbat://widget/edit/$id"))
                .putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, id)
            views.setOnClickPendingIntent(R.id.widget_edit, PendingIntent.getActivity(context, id + 10000, edit, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE))
            manager.updateAppWidget(id, views)
        }
    }
}

object WidgetWork {
    private const val PERIODIC = "boulderbat-widgets-periodic"
    fun schedule(context: Context) {
        val manager = WorkManager.getInstance(context)
        if (GymWidgetProvider.ids(context).isEmpty()) { manager.cancelUniqueWork(PERIODIC); return }
        val delay = Duration.between(Instant.now(), Vienna.nextRefresh(Instant.now())).seconds.coerceAtLeast(0)
        val work = PeriodicWorkRequestBuilder<WidgetRefreshWorker>(15, TimeUnit.MINUTES)
            .setInitialDelay(delay, TimeUnit.SECONDS).build()
        manager.enqueueUniquePeriodicWork(PERIODIC, ExistingPeriodicWorkPolicy.KEEP, work)
    }
    fun refresh(context: Context) {
        WorkManager.getInstance(context).enqueueUniqueWork("boulderbat-widgets-refresh", ExistingWorkPolicy.REPLACE,
            OneTimeWorkRequestBuilder<WidgetRefreshWorker>().build())
    }
}

class WidgetRefreshWorker(context: Context, parameters: WorkerParameters) : CoroutineWorker(context, parameters) {
    override suspend fun doWork(): Result {
        val context = applicationContext; val prefs = WidgetPreferences(context); val repository = Repository(context)
        val groups = GymWidgetProvider.ids(context).toList().mapNotNull { id -> prefs.get(id)?.let { id to it } }.groupBy { it.second.server }
        var failed = false
        for ((server, _) in groups) {
            val cached = repository.cached(server)
            // Update freshness and day guards even if the following fetch is offline.
            GymWidgetProvider.renderAll(context, server, cached)
            try {
                val fresh = repository.refresh(server)
                // Re-read IDs/configurations: an edit or removal may have happened during the fetch.
                GymWidgetProvider.renderAll(context, server, fresh)
            } catch (e: CancellationException) { throw e }
            catch (_: Exception) { failed = true }
        }
        return if (failed && runAttemptCount < 2) Result.retry() else Result.success()
    }
}
