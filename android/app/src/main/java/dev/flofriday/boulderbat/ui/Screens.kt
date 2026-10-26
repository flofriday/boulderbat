@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
package dev.flofriday.boulderbat.ui

import android.app.DatePickerDialog
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import dev.flofriday.boulderbat.*
import dev.flofriday.boulderbat.R
import dev.flofriday.boulderbat.data.*
import dev.flofriday.boulderbat.widget.WidgetRenderer
import dev.flofriday.boulderbat.widget.WidgetPins
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.StateFlow
import java.time.Instant
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import kotlin.math.abs

private enum class Tab(val label: String, val icon: ImageVector) {
    Live("Live", Icons.Default.Home), History("History", Icons.AutoMirrored.Filled.List),
    Week("Typical week", Icons.Default.DateRange)
}

@Composable
fun BoulderbatRoot(model: AppViewModel, link: StateFlow<Pair<Int, Long>?>) {
    val state by model.state.collectAsStateWithLifecycle()
    val deepLink by link.collectAsStateWithLifecycle()
    var tab by rememberSaveable { mutableIntStateOf(0) }
    var gym by rememberSaveable { mutableIntStateOf(262) }
    var dayString by rememberSaveable { mutableStateOf(Vienna.day().toString()) }
    var settings by rememberSaveable { mutableStateOf(false) }
    val day = LocalDate.parse(dayString)
    val today = Vienna.day(state.now)
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    LaunchedEffect(lifecycle, model) {
        lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            while (true) { delay(60_000); model.refresh() }
        }
    }
    LaunchedEffect(deepLink) { deepLink?.let { gym = it.first; dayString = Vienna.day().toString(); tab = 1 } }
    var previousToday by remember { mutableStateOf(today) }
    LaunchedEffect(today) {
        if (dayString == previousToday.toString()) dayString = today.toString()
        previousToday = today
    }
    BoxWithConstraints {
        val wide = maxWidth >= 840.dp
        Row {
            if (wide) NavigationRail(Modifier.fillMaxHeight().width(100.dp).padding(top = 32.dp)) {
                Tab.entries.forEachIndexed { index, item -> NavigationRailItem(
                    selected = tab == index, onClick = { tab = index },
                    icon = { Icon(item.icon, item.label) }, label = { Text(item.label) }) }
            }
            Scaffold(modifier = Modifier.weight(1f), containerColor = MaterialTheme.colorScheme.background,
                topBar = {
                    TopAppBar(title = { Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Image(androidx.compose.ui.res.painterResource(R.drawable.ic_boulderbat), null, Modifier.size(32.dp).clip(RoundedCornerShape(8.dp)))
                        Text("Boulderbat", fontWeight = FontWeight.Bold)
                    } }, actions = {
                        IconButton(onClick = {
                            model.refreshNow()
                            if (tab == 1 && day != today) model.history(day)
                            if (tab == 2) model.week(gym)
                        }, enabled = !state.loading) { Icon(Icons.Default.Refresh, "Refresh") }
                        IconButton(onClick = { settings = true }) { Icon(Icons.Default.Settings, "Settings") }
                    })
                }, bottomBar = {
                    if (!wide) NavigationBar {
                        Tab.entries.forEachIndexed { index, item -> NavigationBarItem(
                            selected = tab == index, onClick = { tab = index },
                            icon = { Icon(item.icon, null) }, label = { Text(item.label) }) }
                    }
                }
            ) { padding ->
                Column(Modifier.padding(padding).fillMaxSize()) {
                    if (state.loading) LinearProgressIndicator(Modifier.fillMaxWidth())
                    state.error?.let { Notice(it, onRetry = model::refreshNow) }
                    when (tab) {
                        0 -> LiveScreen(state) { id -> gym = id; dayString = today.toString(); tab = 1 }
                        1 -> HistoryScreen(state, day, gym, { dayString = it.toString() }, model::history)
                        2 -> WeekScreen(state, gym, { gym = it }, model::week)
                    }
                }
            }
        }
    }
    if (settings) SettingsDialog(state, model::setServer) { settings = false }
}

@Composable
private fun LiveScreen(state: AppState, onGym: (Int) -> Unit) {
    Column(Modifier.fillMaxSize()) {
        Text("Find the best time to hang out at the gym", Modifier.padding(horizontal = 20.dp, vertical = 12.dp),
            style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 6.dp), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("${Gym.all.size} locations", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text("Vienna time", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        LazyVerticalGrid(columns = GridCells.Adaptive(320.dp), contentPadding = PaddingValues(16.dp),
            horizontalArrangement = Arrangement.spacedBy(14.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            items(Gym.all, key = { it.id }) { gym -> LiveCard(gym, state.snapshot, state.now) { onGym(gym.id) } }
        }
    }
}

@Composable
private fun LiveCard(gym: Gym, snapshot: Snapshot?, now: Instant, onClick: () -> Unit) {
    val live = snapshot?.live(gym.id)
    val day = snapshot?.day ?: Vienna.day(now)
    val series = remember(snapshot, gym, now) { listOf(GraphData.series(gym, day, snapshot?.readings.orEmpty(), snapshot?.forecast(gym.id, now))) }
    val stale = snapshot?.let { it.isStale(now) || it.isReadingStale(gym.id, now) } ?: true
    Box(Modifier.fillMaxWidth().height(216.dp).clip(RoundedCornerShape(26.dp))
        .background(Brush.linearGradient(listOf(Color(0xFF282E32), Color(0xFF111719)))).clickable(onClick = onClick)
        .padding(18.dp)) {
        CapacityChart(day, series, now, Modifier.matchParentSize().padding(start = 112.dp, top = 48.dp), compact = true, dark = true)
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Box(Modifier.size(6.dp).background(Color(gym.color), CircleShape))
                    Text(gym.title, color = Color.White, fontWeight = FontWeight.SemiBold, fontSize = 16.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                Text("${gym.provider} · ${gym.city}", color = Color(0xFFA8B1B6), fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp))
            }
            if (live != null && !stale) StatusPill(live.capacity)
        }
        Column(Modifier.align(Alignment.BottomStart).padding(bottom = 12.dp)) {
            Text(live?.let { "${it.capacity.toInt()}%" } ?: "—", color = Color.White, fontSize = 48.sp, fontWeight = FontWeight.Bold)
            if (stale) Text(if (live == null) "No readings" else "Saved reading", color = Color(0xFFCED6DB), style = MaterialTheme.typography.labelSmall)
        }
        if (day != Vienna.day(now)) Text(day.format(DateTimeFormatter.ofPattern("d MMM")), Modifier.align(Alignment.BottomEnd), color = Color(0xFFCED6DB), fontSize = 10.sp)
    }
}

@Composable
fun StatusPill(value: Double) {
    val color = when { value < 40 -> Quiet; value < 70 -> Color(0xFFFFD46E); else -> Color(0xFFFF8FA5) }
    Text(occupancyLabel(value), color = color, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold,
        modifier = Modifier.clip(RoundedCornerShape(50)).background(if (value < 40) Color(0xFF203D34) else Color(0xFF49392C))
            .padding(horizontal = 12.dp, vertical = 7.dp))
}

@Composable
private fun GymChips(selected: Set<Int>, onChange: (Set<Int>) -> Unit) {
    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        FilterChip(selected == Gym.all.map { it.id }.toSet(), { onChange(Gym.all.map { it.id }.toSet()) }, label = { Text("All") })
        val vienna = Gym.all.filter { it.city == "Wien" }.map { it.id }.toSet()
        FilterChip(selected == vienna, { onChange(vienna) }, label = { Text("Wien") })
        Gym.all.forEach { gym -> FilterChip(gym.id in selected, {
            val next = if (selected.size == Gym.all.size) setOf(gym.id) else if (gym.id in selected) selected - gym.id else selected + gym.id
            onChange(next.ifEmpty { Gym.all.map { it.id }.toSet() })
        }, label = { Text(gym.title) }, leadingIcon = { Box(Modifier.size(7.dp).background(Color(gym.color), CircleShape)) }) }
    }
}

@Composable
private fun HistoryScreen(state: AppState, day: LocalDate, initialGym: Int, onDay: (LocalDate) -> Unit, load: (LocalDate) -> Unit) {
    val context = LocalContext.current
    val today = Vienna.day(state.now)
    var selectedIds by rememberSaveable(initialGym) { mutableStateOf(listOf(initialGym)) }
    var selectedTime by remember(day) { mutableStateOf<Instant?>(null) }
    val ids = selectedIds.toSet()
    LaunchedEffect(day, state.server) { load(day) }
    val readings = if (day == today) state.snapshot?.takeIf { it.day == day }?.readings.orEmpty()
        else if (state.historyDay == day) state.history else emptyList()
    val series = remember(day, readings, ids, state.snapshot, state.now) {
        Gym.all.filter { it.id in ids }.map { gym -> GraphData.series(gym, day, readings,
            if (day == today) state.snapshot?.forecast(gym.id, state.now) else null) }
    }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            IconButton(onClick = { onDay(day.minusDays(1)) }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Previous day") }
            OutlinedButton(onClick = {
                DatePickerDialog(context, { _, y, m, d -> onDay(LocalDate.of(y, m + 1, d)) }, day.year, day.monthValue - 1, day.dayOfMonth).apply {
                    // DatePicker uses the device zone, but the selected fields are Vienna calendar dates.
                    datePicker.maxDate = today.atTime(23, 59).atZone(java.time.ZoneId.systemDefault()).toInstant().toEpochMilli()
                }.show()
            }) { Text(day.format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))) }
            IconButton(onClick = { onDay(day.plusDays(1)) }, enabled = day < today) { Icon(Icons.AutoMirrored.Filled.ArrowForward, "Next day") }
            Spacer(Modifier.weight(1f)); TextButton(onClick = { onDay(today) }, contentPadding = PaddingValues(4.dp)) { Text("Today") }
        }
        GymChips(ids) { selectedIds = it.toList() }
        if (state.historyLoading && day != today) LinearProgressIndicator(Modifier.fillMaxWidth())
        if (day != today) state.historyError?.let { Notice(it) { load(day) } }
        Surface(shape = RoundedCornerShape(20.dp), tonalElevation = 1.dp) {
            Column(Modifier.padding(10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                CapacityChart(day, series, state.now, Modifier.fillMaxWidth().height(300.dp),
                    dark = isSystemInDarkTheme(), selected = selectedTime, onSelection = { selectedTime = it })
                Legend()
                Text("08:00–midnight · Vienna time", style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(horizontal = 4.dp, vertical = 6.dp))
            }
        }
        selectedTime?.let { time ->
            Text(Vienna.time(time), fontWeight = FontWeight.SemiBold)
            series.forEach { line ->
                val point = (line.recorded.flatten() + line.predicted.flatten()).minByOrNull { abs(it.at.epochSecond - time.epochSecond) }
                if (point != null && abs(point.at.epochSecond - time.epochSecond) <= 450) {
                    Text("${line.gym.title}: ${"%.1f".format(point.value)}%" +
                        if (point.lower != null) " predicted · 80% range ${"%.1f".format(point.lower)}–${"%.1f".format(point.upper)}%" else " recorded",
                        style = MaterialTheme.typography.bodySmall)
                }
            }
        }
        if (readings.isEmpty() && !state.loading && !state.historyLoading) Text("No readings for this day.", Modifier.padding(12.dp))
        Gym.all.filter { it.id in ids }.forEach { gym ->
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Box(Modifier.size(8.dp).background(Color(gym.color), CircleShape)); Text(gym.title, style = MaterialTheme.typography.bodyMedium)
            }
            if (day == today) state.snapshot?.forecast(gym.id, state.now)?.takeIf { it.status != "ok" }?.let {
                Text(it.reason ?: "Prediction unavailable", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        if (day == today) state.snapshot?.forecastError?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
    }
}

@Composable private fun Legend() {
    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 4.dp), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
        Text("━ Recorded", style = MaterialTheme.typography.labelSmall)
        Text("┄ Predicted", style = MaterialTheme.typography.labelSmall)
        Text("▰ 80% range", style = MaterialTheme.typography.labelSmall)
    }
}

@Composable
fun GymPicker(gym: Int, onGym: (Int) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    Box {
        OutlinedButton(onClick = { expanded = true }) { Text(Gym.find(gym)?.title ?: "Choose location"); Icon(Icons.Default.ArrowDropDown, null) }
        DropdownMenu(expanded, { expanded = false }) {
            Gym.all.forEach { location -> DropdownMenuItem(text = { Text(location.title) },
                onClick = { onGym(location.id); expanded = false }) }
        }
    }
}

@Composable
private fun WeekScreen(state: AppState, gym: Int, onGym: (Int) -> Unit, load: (Int) -> Unit) {
    var highlighted by remember(gym, state.server) { mutableStateOf<WeekCell?>(null) }
    val days = listOf("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    LaunchedEffect(gym, state.server) { load(gym) }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        GymPicker(gym, onGym)
        Text("Typical week", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Text("Average occupancy by weekday and hour in Vienna time.", color = MaterialTheme.colorScheme.onSurfaceVariant)
        if (state.weekLoading) LinearProgressIndicator(Modifier.fillMaxWidth())
        state.weekError?.let { Notice(it) { load(gym) } }
        state.week?.takeIf { state.weekGym == gym }?.let { week ->
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(20.dp)).background(MaterialTheme.colorScheme.surface).padding(12.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Row(Modifier.fillMaxWidth().padding(bottom = 8.dp)) {
                    Spacer(Modifier.width(24.dp))
                    days.forEach { Text(it, Modifier.weight(1f), textAlign = androidx.compose.ui.text.style.TextAlign.Center, fontSize = 11.sp, fontWeight = FontWeight.Medium) }
                }
                (8..23).forEach { hour -> Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text("%02d".format(hour), Modifier.width(24.dp), fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    (0..6).forEach { weekday ->
                        val cell = week.cells.firstOrNull { it.weekday == weekday && it.hour == hour }
                        Box(Modifier.weight(1f).height(28.dp).padding(horizontal = 1.5.dp).clip(RoundedCornerShape(3.dp))
                            .background(cell?.let { heatColor(it.capacity) } ?: MaterialTheme.colorScheme.surfaceVariant)
                            .clickable(enabled = cell != null) { highlighted = cell }
                            .semantics { contentDescription = "${days[weekday]} $hour:00: " + (cell?.let { "${it.capacity.toInt()} percent average, ${it.sampleCount} readings" } ?: "No readings") })
                    }
                } }
                Row(Modifier.padding(top = 12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                    Text("Quiet", fontSize = 11.sp)
                    listOf(0.0, 10.0, 20.0, 30.0, 40.0, 50.0).forEach { Box(Modifier.size(18.dp, 8.dp).background(heatColor(it), RoundedCornerShape(2.dp))) }
                    Text("Busy", fontSize = 11.sp); Spacer(Modifier.weight(1f)); Text("${week.weekCount} weeks", fontSize = 11.sp)
                }
            }
            highlighted?.let { Text("${days[it.weekday]} ${it.hour}:00 · ${"%.1f".format(it.capacity)}% average · ${it.sampleCount} readings", style = MaterialTheme.typography.bodySmall) }
            Text("Based on ${week.cells.sumOf { it.sampleCount }} observations from the latest eight local calendar weeks.",
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            if (week.cells.isEmpty()) Text("No weekly pattern yet.")
        }
    }
}

private fun heatColor(value: Double): Color {
    val t = (value / 50).coerceIn(0.0, 1.0)
    val l = 0.94 - t * 0.48
    val v = l + 0.95 * minOf(l, 1 - l)
    val s = if (v == 0.0) 0.0 else 2 * (1 - l / v)
    return Color.hsv(((48 - t * 48)).toFloat(), s.toFloat(), v.toFloat())
}

@Composable
private fun SettingsDialog(state: AppState, onServer: (String) -> Unit, onDismiss: () -> Unit) {
    val context = LocalContext.current
    var server by remember { mutableStateOf(state.server) }
    var error by remember { mutableStateOf<String?>(null) }
    var previews by remember { mutableStateOf(false) }
    var widgetGym by rememberSaveable { mutableIntStateOf(Gym.all.first().id) }
    AlertDialog(onDismissRequest = onDismiss, title = { Text("Settings") }, text = {
        Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedTextField(server, { server = it; error = null }, label = { Text("API server") }, singleLine = true, isError = error != null)
            error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            TextButton(onClick = { server = PRODUCTION_SERVER }) { Text("Use production server") }
            HorizontalDivider()
            Text("Home-screen widgets", fontWeight = FontWeight.SemiBold)
            Text("Long-press your home screen, choose Widgets, then Boulderbat. Choose a gym for each widget. Resize it for a larger graph.", style = MaterialTheme.typography.bodySmall)
            GymPicker(widgetGym) { widgetGym = it }
            if (WidgetPins.supported(context)) Button(onClick = {
                try {
                    val normalized = normalizeServer(server, BuildConfig.DEBUG)
                    if (!WidgetPins.request(context, Gym.find(widgetGym)!!, normalized,
                            state.snapshot.takeIf { normalized == state.server })) error = "Add the widget from your home screen instead."
                } catch (e: IllegalArgumentException) { error = e.message }
            }) { Text("Add widget") }
            TextButton(onClick = { previews = !previews }) { Text(if (previews) "Hide widget previews" else "Preview widgets") }
            if (previews) WidgetPreviews(state.snapshot, widgetGym, state.now)
            Text("Forecasts end at midnight. All chart times use Europe/Vienna.", style = MaterialTheme.typography.bodySmall)
        }
    }, confirmButton = { TextButton(onClick = {
        try { onServer(normalizeServer(server, BuildConfig.DEBUG)); onDismiss() }
        catch (e: IllegalArgumentException) { error = e.message }
    }) { Text("Save") } }, dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } })
}

@Composable private fun WidgetPreviews(snapshot: Snapshot?, gym: Int, now: Instant) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Current data · exact widget renderer", style = MaterialTheme.typography.labelSmall)
        listOf(180 to 180, 360 to 180, 360 to 340).forEach { (w, h) ->
            val bitmap = remember(snapshot, gym, now, w, h) { WidgetRenderer.render(Gym.find(gym)!!, snapshot, w, h, 2f, now) }
            Image(bitmap.asImageBitmap(), "${if (w == h) "Small" else if (h < 200) "Medium" else "Large"} widget preview",
                Modifier.widthIn(max = w.dp).fillMaxWidth().aspectRatio(w.toFloat() / h))
        }
    }
}

@Composable
private fun Notice(text: String, onRetry: () -> Unit) {
    Row(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.secondaryContainer).padding(horizontal = 16.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Text(text, Modifier.weight(1f), style = MaterialTheme.typography.bodySmall)
        TextButton(onClick = onRetry) { Text("Retry") }
    }
}
