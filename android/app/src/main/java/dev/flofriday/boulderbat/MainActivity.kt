package dev.flofriday.boulderbat

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import dev.flofriday.boulderbat.data.Gym
import dev.flofriday.boulderbat.data.normalizeServer
import dev.flofriday.boulderbat.ui.BoulderbatRoot
import dev.flofriday.boulderbat.ui.BoulderbatTheme
import kotlinx.coroutines.flow.MutableStateFlow

class MainActivity : ComponentActivity() {
    private val model: AppViewModel by viewModels()
    private val link = MutableStateFlow<Pair<Int, Long>?>(null)
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState); enableEdgeToEdge(); handleIntent(intent)
        setContent { BoulderbatTheme { BoulderbatRoot(model, link) } }
    }
    override fun onNewIntent(intent: Intent) { super.onNewIntent(intent); setIntent(intent); handleIntent(intent) }
    private fun handleIntent(intent: Intent) {
        val uri = intent.data
        if (uri?.scheme == "boulderbat" && uri.host == "history") {
            uri.getQueryParameter("gym")?.toIntOrNull()?.takeIf { Gym.find(it) != null }?.let {
                link.value = it to System.nanoTime()
            }
        }
        // Widget PendingIntents are explicit and preserve the widget's configured server.
        intent.getStringExtra("widget_server")?.let { server ->
            runCatching { model.setServer(normalizeServer(server, BuildConfig.DEBUG)) }
        }
    }
}
