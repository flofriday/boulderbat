package dev.flofriday.boulderbat

import com.sun.net.httpserver.HttpServer
import dev.flofriday.boulderbat.data.*
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import java.net.InetSocketAddress
import java.time.Instant
import java.time.LocalDate

class CoreTest {
    private val day = LocalDate.of(2026, 10, 23)
    private val gym = Gym.all.first()
    private fun at(hour: Int, minute: Int = 0) = day.atTime(hour, minute).atZone(Vienna.zone).toInstant()
    @Test fun viennaDatesAndDstUseLocalCalendar() {
        assertEquals(LocalDate.of(2026, 10, 24), Vienna.day(Instant.parse("2026-10-23T22:01:00Z")))
        val spring = LocalDate.of(2026, 3, 29)
        val autumn = LocalDate.of(2026, 10, 25)
        assertEquals("2026-03-29T06:00:00Z", Vienna.start(spring).toString())
        assertEquals("2026-10-25T07:00:00Z", Vienna.start(autumn).toString())
        assertEquals(16 * 3600L, java.time.Duration.between(Vienna.start(autumn), Vienna.end(autumn)).seconds)
    }
    @Test fun refreshWaitsForQuarterHourPlusOneMinute() {
        assertEquals(Instant.parse("2026-10-23T13:16:00Z"), Vienna.nextRefresh(Instant.parse("2026-10-23T13:15:59Z")))
        assertEquals(Instant.parse("2026-10-23T13:31:00Z"), Vienna.nextRefresh(Instant.parse("2026-10-23T13:16:00Z")))
    }
    @Test fun missingReadingsBreakTheRecordedLine() {
        val readings = listOf(Reading(gym.id, 20.0, at(9)), Reading(gym.id, 30.0, at(9, 15)), Reading(gym.id, 40.0, at(10)))
        val line = GraphData.series(gym, day, readings, null)
        assertEquals(listOf(2, 1), line.recorded.map { it.size })
        assertEquals(at(10), line.lastRecorded?.at)
    }
    @Test fun forecastConnectorAndIntervalsStaySeparateFromRecordedData() {
        val forecast = LocationForecast(gym.id, "ok", null, listOf(ForecastPoint(45.0, 30.0, 65.0, at(15, 16))))
        val line = GraphData.series(gym, day, listOf(Reading(gym.id, 40.0, at(15, 15))), forecast)
        assertEquals(1, line.recorded.flatten().size)
        assertEquals(2, line.predicted.flatten().size)
        assertNull(line.predicted.flatten().first().lower)
        assertEquals(30.0, line.predicted.flatten().last().lower!!, 0.0)
        assertEquals(at(15, 15), line.lastRecorded?.at)
    }
    @Test fun longGapDoesNotGainAnInventedConnector() {
        val forecast = LocationForecast(gym.id, "ok", null, listOf(ForecastPoint(45.0, 30.0, 65.0, at(16))))
        val line = GraphData.series(gym, day, listOf(Reading(gym.id, 40.0, at(15))), forecast)
        assertEquals(1, line.predicted.flatten().size)
    }
    @Test fun anotherGymAndTomorrowNeverEnterTodaysGraph() {
        val readings = listOf(Reading(263, 30.0, at(12)), Reading(gym.id, 90.0, Vienna.end(day)))
        val forecast = LocationForecast(gym.id, "ok", null, listOf(ForecastPoint(99.0, 80.0, 100.0, Vienna.end(day))))
        val line = GraphData.series(gym, day, readings, forecast)
        assertTrue(line.recorded.isEmpty()); assertTrue(line.predicted.isEmpty())
    }
    @Test fun expiredAndYesterdayForecastsAreHidden() {
        val location = LocationForecast(gym.id, "ok", null, emptyList())
        val snapshot = Snapshot(at(15), day, emptyList(), emptyList(), Forecast(day, at(16), listOf(location)))
        assertNotNull(snapshot.forecast(gym.id, at(15, 30)))
        assertNull(snapshot.forecast(gym.id, at(16, 1)))
        assertNull(snapshot.forecast(gym.id, Vienna.end(day)))
    }
    @Test fun nullTargetsStayMissingAndFractionalUtcTimesDecode() {
        val readings = JsonCodec.history("""[{"location_id":262,"capacity":null,"recorded_at":"2026-10-23T13:15:00Z"},{"location_id":262,"capacity":42.5,"recorded_at":"2026-10-23T13:16:00.123456Z"}]""")
        assertEquals(1, readings.size); assertEquals(42.5, readings.single().capacity, 0.0)
        assertEquals(123456000, readings.single().recordedAt.nano)
    }
    @Test fun serverValidationRejectsCredentialsAndUnsafeSchemes() {
        assertEquals(PRODUCTION_SERVER, normalizeServer(" $PRODUCTION_SERVER/ "))
        for (url in listOf("http://example.com", "https://user:password@example.com", "file:///tmp/test", "https://example.com?a=b")) {
            assertTrue(url, runCatching { normalizeServer(url) }.isFailure)
        }
        assertEquals("http://10.0.2.2:8000", normalizeServer("http://10.0.2.2:8000", true))
        assertTrue(runCatching { normalizeServer("http://10.0.2.2:8000") }.isFailure)
    }
    @Test fun failedForecastDoesNotHideRecordedData() = verifyOptionalForecast(503, "unavailable")
    @Test fun malformedForecastDoesNotHideRecordedData() = verifyOptionalForecast(200, "not valid JSON")
    private fun verifyOptionalForecast(status: Int, prediction: String) = runBlocking {
        val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
        server.createContext("/") { exchange ->
            val forecast = exchange.requestURI.path == "/prediction"
            val bytes = (if (forecast) prediction else "[]").toByteArray()
            exchange.sendResponseHeaders(if (forecast) status else 200, bytes.size.toLong())
            exchange.responseBody.use { it.write(bytes) }
        }
        server.start()
        try {
            val loaded = Api("http://127.0.0.1:${server.address.port}").dashboard()
            assertTrue(loaded.snapshot.live.isEmpty()); assertTrue(loaded.snapshot.readings.isEmpty())
            assertNull(loaded.snapshot.forecast); assertNotNull(loaded.snapshot.forecastError)
            assertNull(JsonCodec.snapshot(loaded.cacheJson).forecast)
        } finally { server.stop(0) }
    }
}
