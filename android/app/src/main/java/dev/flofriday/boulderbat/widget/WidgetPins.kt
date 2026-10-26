package dev.flofriday.boulderbat.widget

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.widget.RemoteViews
import dev.flofriday.boulderbat.R
import dev.flofriday.boulderbat.data.*

object WidgetPins {
    fun supported(context: Context) = AppWidgetManager.getInstance(context).isRequestPinAppWidgetSupported
    fun request(context: Context, gym: Gym, server: String, snapshot: Snapshot?): Boolean {
        val manager = AppWidgetManager.getInstance(context)
        if (!manager.isRequestPinAppWidgetSupported) return false
        val callback = Intent(context, WidgetPinnedReceiver::class.java)
            .putExtra("gym", gym.id).putExtra("server", server)
        // The launcher fills in EXTRA_APPWIDGET_ID. This mutable intent is restricted
        // to our explicit, non-exported receiver and carries no credentials.
        val pending = PendingIntent.getBroadcast(context, System.nanoTime().toInt(), callback,
            PendingIntent.FLAG_ONE_SHOT or PendingIntent.FLAG_MUTABLE)
        val preview = RemoteViews(context.packageName, R.layout.gym_widget)
        preview.setImageViewBitmap(R.id.widget_image, WidgetRenderer.render(gym, snapshot, 360, 180, 2f))
        return manager.requestPinAppWidget(ComponentName(context, GymWidgetProvider::class.java),
            Bundle().apply { putParcelable(AppWidgetManager.EXTRA_APPWIDGET_PREVIEW, preview) }, pending)
    }
}

class WidgetPinnedReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val id = intent.getIntExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, AppWidgetManager.INVALID_APPWIDGET_ID)
        val gym = Gym.find(intent.getIntExtra("gym", -1)) ?: return
        val server = intent.getStringExtra("server") ?: return
        if (id == AppWidgetManager.INVALID_APPWIDGET_ID) return
        val prefs = WidgetPreferences(context)
        if (prefs.get(id) == null) prefs.save(id, gym.id, server)
        WidgetWork.schedule(context); WidgetWork.refresh(context)
    }
}
