package dev.flofriday.boulderbat

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import dev.flofriday.boulderbat.data.*
import dev.flofriday.boulderbat.widget.GymWidgetProvider
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.time.Instant
import java.time.LocalDate

data class AppState(
    val server: String = PRODUCTION_SERVER, val snapshot: Snapshot? = null,
    val loading: Boolean = false, val error: String? = null, val now: Instant = Instant.now(),
    val historyDay: LocalDate? = null, val history: List<Reading> = emptyList(),
    val historyLoading: Boolean = false, val historyError: String? = null,
    val weekGym: Int? = null, val week: TypicalWeek? = null,
    val weekLoading: Boolean = false, val weekError: String? = null,
)

class AppViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = Repository(application)
    private val mutable = MutableStateFlow(AppState(server = repository.server))
    val state = mutable.asStateFlow()
    private val refreshMutex = Mutex()
    private var historyJob: Job? = null
    private var weekJob: Job? = null
    init {
        viewModelScope.launch {
            val server = mutable.value.server
            val cached = repository.cached(server)
            if (mutable.value.server == server) mutable.update { it.copy(snapshot = cached) }
            refresh()
        }
    }
    suspend fun refresh() = refreshMutex.withLock {
        val server = mutable.value.server
        mutable.update { it.copy(loading = true, now = Instant.now()) }
        try {
            val snapshot = repository.refresh(server)
            if (mutable.value.server == server) {
                mutable.update { it.copy(snapshot = snapshot, error = null, now = Instant.now()) }
                GymWidgetProvider.renderAll(getApplication(), server, snapshot)
            }
        } catch (e: CancellationException) { throw e }
        catch (_: Exception) {
            if (mutable.value.server == server) mutable.update { it.copy(error = "Couldn’t refresh. Saved readings remain available.") }
        } finally { mutable.update { it.copy(loading = false) } }
    }
    fun refreshNow() { viewModelScope.launch { refresh() } }
    fun setServer(input: String) {
        repository.server = input
        if (repository.server == mutable.value.server) return
        historyJob?.cancel(); weekJob?.cancel()
        mutable.value = AppState(server = repository.server)
        viewModelScope.launch {
            val server = mutable.value.server
            val cached = repository.cached(server)
            if (mutable.value.server == server) mutable.update { it.copy(snapshot = cached) }
            refresh()
        }
    }
    fun history(day: LocalDate) {
        historyJob?.cancel()
        if (day == Vienna.day()) return
        val server = mutable.value.server
        mutable.update { it.copy(historyDay = day, history = emptyList(), historyLoading = true, historyError = null) }
        historyJob = viewModelScope.launch {
            try {
                val readings = Api(server).history(day)
                mutable.update { it.copy(history = readings, historyLoading = false) }
            } catch (e: CancellationException) { throw e }
            catch (_: Exception) { mutable.update { it.copy(historyLoading = false, historyError = "Couldn’t load this day. Try refreshing.") } }
        }
    }
    fun week(gym: Int) {
        weekJob?.cancel()
        val server = mutable.value.server
        mutable.update { it.copy(weekGym = gym, week = null, weekLoading = true, weekError = null) }
        weekJob = viewModelScope.launch {
            try {
                val value = Api(server).week(gym)
                mutable.update { it.copy(week = value, weekLoading = false) }
            } catch (e: CancellationException) { throw e }
            catch (_: Exception) { mutable.update { it.copy(weekLoading = false, weekError = "Couldn’t load the weekly pattern. Try again.") } }
        }
    }
}
