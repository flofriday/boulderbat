package dev.flofriday.boulderbat.widget

import android.appwidget.AppWidgetManager
import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.lifecycleScope
import dev.flofriday.boulderbat.BuildConfig
import dev.flofriday.boulderbat.data.*
import dev.flofriday.boulderbat.ui.BoulderbatTheme
import dev.flofriday.boulderbat.ui.GymPicker
import kotlinx.coroutines.launch

class WidgetConfigureActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState); enableEdgeToEdge()
        setResult(RESULT_CANCELED)
        val id = intent.getIntExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, AppWidgetManager.INVALID_APPWIDGET_ID)
        if (id == AppWidgetManager.INVALID_APPWIDGET_ID) { finish(); return }
        val existing = WidgetPreferences(this).get(id)
        setContent {
            BoulderbatTheme {
                var gym by rememberSaveable { mutableIntStateOf(existing?.gym?.id ?: Gym.all.first().id) }
                var server by rememberSaveable { mutableStateOf(existing?.server ?: Repository(this).server) }
                var error by remember { mutableStateOf<String?>(null) }
                var saving by remember { mutableStateOf(false) }
                Surface(Modifier.fillMaxSize()) {
                    Column(Modifier.windowInsetsPadding(WindowInsets.safeDrawing).verticalScroll(rememberScrollState()).padding(24.dp), verticalArrangement = Arrangement.spacedBy(20.dp)) {
                        Text("Choose your gym", style = MaterialTheme.typography.headlineMedium)
                        Text("Live occupancy, today's graph and forecast. Each widget has its own location.")
                        GymPicker(gym) { gym = it }
                        OutlinedTextField(server, { server = it; error = null }, label = { Text("API server") }, singleLine = true, isError = error != null, modifier = Modifier.fillMaxWidth())
                        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                        Text("Resize the widget for a larger graph. Tap the graph to open history; tap the edit button to change gyms.", style = MaterialTheme.typography.bodyMedium)
                        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            OutlinedButton(onClick = { finish() }) { Text("Cancel") }
                            Button(enabled = !saving, onClick = {
                                try {
                                    val normalized = normalizeServer(server, BuildConfig.DEBUG)
                                    val config = WidgetConfig(Gym.find(gym)!!, normalized)
                                    WidgetPreferences(this@WidgetConfigureActivity).save(id, gym, normalized)
                                    saving = true
                                    lifecycleScope.launch {
                                        GymWidgetProvider.render(this@WidgetConfigureActivity, id, config, Repository(this@WidgetConfigureActivity).cached(normalized))
                                        WidgetWork.schedule(this@WidgetConfigureActivity); WidgetWork.refresh(this@WidgetConfigureActivity)
                                        setResult(RESULT_OK, Intent().putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, id)); finish()
                                    }
                                } catch (e: IllegalArgumentException) { error = e.message }
                            }) { Text("Save widget") }
                        }
                    }
                }
            }
        }
    }
}
