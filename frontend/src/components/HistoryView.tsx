import { useEffect, useMemo, useState } from "react"
import { ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid, ReferenceLine } from "recharts"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart"
import { Button } from "@/components/ui/button"
import { searchParams, updateUrl } from "@/lib/url-state"
import { chartData, dayRange, HISTORY_TIMEZONE, shiftDate, validDay, viennaDay } from "@/lib/history-chart"
import type { PredictionResponse, Reading } from "@/lib/history-chart"

// `label` must match the `title` returned by the API — lines are keyed by title.
const GYMS = [
  { id: "262", label: "Hannovergasse", color: "hsl(var(--chart-3))" },
  { id: "263", label: "Hauptbahnhof", color: "hsl(var(--chart-4))" },
  { id: "264", label: "Seestadt", color: "hsl(var(--chart-5))" },
  { id: "265", label: "Wienerberg", color: "hsl(221.2 83.2% 40%)" },
  { id: "1001", label: "Blockfabrik", color: "hsl(30 90% 45%)" },
  { id: "284", label: "St. Pölten", color: "hsl(160 60% 30%)" },
  { id: "260", label: "Linz", color: "hsl(var(--chart-1))" },
  { id: "261", label: "Salzburg", color: "hsl(var(--chart-2))" },
]

// Quick-select presets shown as chips alongside the individual gyms.
const PRESETS = [
  { id: "all", label: "All", ids: GYMS.map(g => g.id) },
  { id: "wien", label: "Wien", ids: ["262", "263", "264", "265", "1001"] },
]

const CHART_CONFIG = Object.fromEntries(GYMS.flatMap(g => [
  [`observed_${g.id}`, { label: `${g.label} · recorded`, color: g.color }],
  [`prediction_${g.id}`, { label: `${g.label} · predicted`, color: g.color, rangeKey: `uncertainty_${g.id}` }],
]))

function formatTick(ts: number) {
  const d = new Date(ts)
  return d.toLocaleTimeString([], { timeZone: HISTORY_TIMEZONE, hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
}

function formatTooltipLabel(ts: string | number) {
  return new Date(Number(ts)).toLocaleString([], {
    timeZone: HISTORY_TIMEZONE, month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  })
}

function selectionEquals(selected: Set<string>, ids: string[]) {
  return selected.size === ids.length && ids.every(id => selected.has(id))
}

function dateFromValue(value: string) {
  return new Date(`${value}T12:00:00Z`)
}

function formatDayLabel(value: string, today: string) {
  if (value === today) return "Today"
  if (value === shiftDate(today, -1)) return "Yesterday"
  return dateFromValue(value).toLocaleDateString([], { timeZone: HISTORY_TIMEZONE, weekday: "short", month: "short", day: "numeric" })
}

function dayFromUrl(today: string) {
  const value = searchParams().get("d") ?? searchParams().get("date")
  if (!value || value > today || !validDay(value)) return today
  return value
}

function gymIdsFromUrl() {
  const value = searchParams().get("g") ?? searchParams().get("gyms")
  if (!value) return new Set(GYMS.map(gym => gym.id))

  const validIds = value.split(",").filter(id => GYMS.some(gym => gym.id === id))
  return validIds.length > 0 ? new Set(validIds) : new Set(GYMS.map(gym => gym.id))
}

export function HistoryView() {
  const [now, setNow] = useState(() => new Date())
  const today = viennaDay(now)
  // null follows today across midnight, while a deliberately selected historical day stays put.
  const [dateSelection, setDateSelection] = useState<string | null>(() => {
    const day = dayFromUrl(today)
    return day === today ? null : day
  })
  const selectedDay = dateSelection ?? today
  const [selectedIds, setSelectedIds] = useState<Set<string>>(gymIdsFromUrl)
  const [readings, setReadings] = useState<Reading[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [forecastState, setForecastState] = useState<{
    day: string; data?: PredictionResponse; error?: string; loading: boolean
  } | null>(null)

  const { start, end } = useMemo(() => dayRange(selectedDay), [selectedDay])
  const selectedDayLabel = formatDayLabel(selectedDay, today)
  const allSelected = selectedIds.size === GYMS.length
  const isToday = selectedDay === today
  const forecast = isToday && forecastState?.day === today ? forecastState : null
  const prediction = forecast?.data?.date === today ? forecast.data : undefined
  const selectedGyms = GYMS.filter(g => selectedIds.has(g.id))

  useEffect(() => {
    const interval = window.setInterval(() => setNow(new Date()), 30_000)
    return () => window.clearInterval(interval)
  }, [])

  useEffect(() => {
    const params = searchParams()
    const gymIds = allSelected ? null : [...selectedIds].join(",")
    if (
      params.get("d") !== selectedDay ||
      params.get("g") !== gymIds ||
      params.has("date") ||
      params.has("gyms") ||
      params.has("gym")
    ) {
      updateUrl({
        d: selectedDay,
        g: gymIds,
        date: null,
        gyms: null,
        gym: null,
      }, true)
    }

    const syncSelection = () => {
      const nextDay = dayFromUrl(today)
      const nextIds = gymIdsFromUrl()
      if (nextDay !== selectedDay) setLoading(true)
      setDateSelection(nextDay === today ? null : nextDay)
      setSelectedIds(current => selectionEquals(current, [...nextIds]) ? current : nextIds)
    }
    window.addEventListener("popstate", syncSelection)
    return () => window.removeEventListener("popstate", syncSelection)
  }, [allSelected, selectedDay, selectedIds, today])

  useEffect(() => {
    const controller = new AbortController()
    const fmt = (d: Date) => d.toISOString().replace(".000", "")
    const params = new URLSearchParams({ start: fmt(start), end: fmt(end) })

    function refreshHistory() {
      fetch(`/history?${params}`, { signal: controller.signal })
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(d => {
        if (controller.signal.aborted) return
        setReadings(d)
        setError(null)
      })
      .catch(e => {
        if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Failed to fetch")
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    }
    refreshHistory()
    const interval = isToday ? window.setInterval(refreshHistory, 60_000) : undefined

    return () => { controller.abort(); window.clearInterval(interval) }
  }, [start, end, isToday])

  useEffect(() => {
    if (!isToday) return
    const controller = new AbortController()
    async function refreshPrediction() {
      setForecastState(current => ({ day: selectedDay, data: current?.day === selectedDay ? current.data : undefined, loading: true }))
      try {
        const response = await fetch("/prediction", { signal: controller.signal })
        if (!response.ok) throw new Error("Today's prediction is temporarily unavailable.")
        const data: PredictionResponse = await response.json()
        if (!controller.signal.aborted) setForecastState({ day: selectedDay, data, loading: false })
      } catch (error) {
        if (!controller.signal.aborted) setForecastState({ day: selectedDay, error: error instanceof Error ? error.message : "Could not load prediction.", loading: false })
      }
    }
    const initial = window.setTimeout(() => { void refreshPrediction() }, 0)
    const interval = window.setInterval(() => { void refreshPrediction() }, 60_000)
    return () => { controller.abort(); window.clearTimeout(initial); window.clearInterval(interval) }
  }, [isToday, selectedDay])

  const { data, observed, future, connectors, lastReading } = useMemo(() => chartData(readings, prediction, selectedIds), [readings, prediction, selectedIds])
  const unavailable = prediction?.locations.filter(location => selectedIds.has(String(location.location_id)) && location.status === "unavailable") ?? []
  const forecastStart = prediction ? Math.max(lastReading ?? Date.parse(prediction.generated_at), start.getTime()) : 0
  const hasPrediction = future.length > 0

  function toggle(id: string) {
    // From the "all" state, a click isolates to just that gym.
    if (selectedIds.size === GYMS.length) {
      setSelectedIds(new Set([id]))
      updateUrl({ g: id })
      return
    }

    const next = new Set(selectedIds)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    // Clearing the last selection falls back to all.
    const selected = next.size === 0 ? new Set(GYMS.map(g => g.id)) : next
    setSelectedIds(selected)
    updateUrl({ g: selected.size === GYMS.length ? null : [...selected].join(",") })
  }

  function selectDay(day: string) {
    if (!validDay(day) || day > today || day === selectedDay) return
    setLoading(true)
    setDateSelection(day === today ? null : day)
    updateUrl({ d: day })
  }

  function selectGymIds(ids: string[]) {
    const nextIds = new Set(ids)
    if (selectionEquals(selectedIds, ids)) return
    setSelectedIds(nextIds)
    updateUrl({ g: ids.length === GYMS.length ? null : ids.join(",") })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="icon"
          onClick={() => selectDay(shiftDate(selectedDay, -1))}
          aria-label="Previous day"
        >
          <ChevronLeft className="size-4" />
        </Button>
        <label className="flex h-10 items-center gap-2 rounded-md border px-3 text-sm font-medium">
          <span className="text-muted-foreground">{selectedDayLabel}</span>
          <input
            type="date"
            value={selectedDay}
            max={today}
            onChange={event => selectDay(event.target.value)}
            aria-label="Select day"
            className="w-32 bg-transparent text-foreground outline-none"
          />
        </label>
        <Button
          variant="outline"
          size="icon"
          onClick={() => selectDay(shiftDate(selectedDay, 1))}
          disabled={selectedDay === today}
          aria-label="Next day"
        >
          <ChevronRight className="size-4" />
        </Button>
        {selectedDay !== today && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => selectDay(today)}
          >
            Today
          </Button>
        )}
      </div>

      <div className="flex items-center gap-2 overflow-x-auto pb-1 -mx-4 px-4 sm:mx-0 sm:px-0 sm:flex-wrap sm:overflow-visible sm:pb-0">
        {PRESETS.map(p => {
          const active = selectionEquals(selectedIds, p.ids)
          return (
            <Button
              key={p.id}
              onClick={() => selectGymIds(p.ids)}
              aria-pressed={active}
              variant={active ? "secondary" : "outline"}
              size="sm"
              className="shrink-0 rounded-full"
            >
              {p.label}
            </Button>
          )
        })}
        <span className="mx-1 h-5 w-px shrink-0 bg-border" />
        {GYMS.map(g => {
          const active = selectedIds.has(g.id)
          return (
            <Button
              key={g.id}
              onClick={() => toggle(g.id)}
              aria-pressed={active}
              variant={active ? "secondary" : "outline"}
              size="sm"
              className="shrink-0 rounded-full"
            >
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-full border"
                style={active
                  ? { backgroundColor: g.color, borderColor: g.color }
                  : { backgroundColor: "transparent", borderColor: "currentColor" }}
              />
              {g.label}
            </Button>
          )
        })}
      </div>

      <Card>
        <CardContent className="px-2 py-3 sm:px-3">
          {loading && <p className="text-sm text-muted-foreground py-12 text-center">Loading…</p>}
          {error && <p className="text-sm text-destructive py-12 text-center">Error: {error}</p>}
          {!loading && !error && data.length === 0 && (
            <p className="text-sm text-muted-foreground py-12 text-center">No data for this range.</p>
          )}
          {!loading && !error && data.length > 0 && (
            <ChartContainer config={CHART_CONFIG} className="h-80 w-full sm:h-96" aria-label={isToday ? "Occupancy chart: solid lines are recorded, dashed lines are predicted, colored bands show the 80% prediction range" : "Recorded occupancy chart"}>
              <ComposedChart data={data} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="ts"
                  type="number"
                  scale="time"
                  domain={[start.getTime(), end.getTime()]}
                  ticks={[0, 4, 8, 12, 16].map(hour => start.getTime() + hour * 60 * 60 * 1000)}
                  allowDataOverflow
                  tickFormatter={formatTick}
                  tick={{ fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  minTickGap={50}
                />
                <YAxis
                  domain={[0, 100]}
                  tickFormatter={v => `${v}%`}
                  tick={{ fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                />
                <ChartTooltip content={<ChartTooltipContent labelFormatter={formatTooltipLabel} />} />
                {selectedGyms.map(gym => (
                  <Area key={`uncertainty_${gym.id}`} data={future} type="monotone"
                    dataKey={`uncertainty_${gym.id}`} stroke="none" fill={gym.color}
                    fillOpacity={selectedGyms.length === 1 ? 0.16 : selectedGyms.length <= 3 ? 0.1 : 0.06}
                    tooltipType="none" activeDot={false} isAnimationActive={false} />
                ))}
                {hasPrediction && forecastStart > start.getTime() && <ReferenceLine x={forecastStart} stroke="hsl(var(--muted-foreground))" strokeDasharray="3 3" label={{ value: "Now", position: "insideTopLeft", fill: "hsl(var(--muted-foreground))", fontSize: 11 }} />}
                {connectors.map(connector => (
                  <Line key={`connector_${connector.location_id}`} data={connector.data} type="linear"
                    dataKey="capacity" stroke={GYMS.find(gym => gym.id === String(connector.location_id))?.color}
                    strokeWidth={2} strokeDasharray="6 4" dot={false} activeDot={false}
                    tooltipType="none" isAnimationActive={false} />
                ))}
                {selectedGyms.map(gym => (
                  <Line
                    key={`observed_${gym.id}`}
                    data={observed}
                    type="monotone"
                    dataKey={`observed_${gym.id}`}
                    stroke={gym.color}
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                ))}
                {selectedGyms.map(gym => (
                  <Line key={`prediction_${gym.id}`} data={future} type="monotone"
                    dataKey={`prediction_${gym.id}`} stroke={gym.color} strokeWidth={2}
                    strokeDasharray="6 4" dot={false} isAnimationActive={false} />
                ))}
              </ComposedChart>
            </ChartContainer>
          )}
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 px-2 pt-2 text-xs text-muted-foreground sm:px-0">
            <span className="inline-flex items-center gap-2"><span className="w-6 border-t-2 border-foreground/60" />Recorded</span>
            {isToday && <span className="inline-flex items-center gap-2"><span className="w-6 border-t-2 border-dashed border-foreground/60" />Predicted · until midnight</span>}
            {isToday && <span className="inline-flex items-center gap-2" title="The model's 10th–90th percentile prediction interval">
              <span className="h-3 w-6 rounded-sm opacity-20" style={{ backgroundColor: selectedGyms.length === 1 ? selectedGyms[0].color : "hsl(var(--muted-foreground))" }} />80% range
            </span>}
            {isToday && <span className="sm:ml-auto" role="status">
              {forecast?.loading || !forecast ? "Updating prediction…" : prediction && hasPrediction ? `Updated ${formatTick(Date.parse(prediction.generated_at))}` : ""}
            </span>}
          </div>
          {isToday && forecast?.error && <p className="px-2 pb-3 text-sm text-muted-foreground" role="status">{forecast.error} You can still browse recorded history.</p>}
          {isToday && unavailable.length > 0 && <div className="space-y-1 px-2 pb-3 text-xs text-muted-foreground" role="status">
            {unavailable.map(location => <p key={location.location_id}>{location.title}: {location.reason}</p>)}
          </div>}
        </CardContent>
      </Card>
    </div>
  )
}
