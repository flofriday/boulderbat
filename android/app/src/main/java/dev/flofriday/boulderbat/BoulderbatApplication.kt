package dev.flofriday.boulderbat

import android.app.Application
import dev.flofriday.boulderbat.widget.WidgetWork

class BoulderbatApplication : Application() {
    override fun onCreate() { super.onCreate(); WidgetWork.schedule(this) }
}
