import { useEffect, useMemo, useState } from "react"
import { LineChart, Line, XAxis, YAxis, CartesianGrid } from "recharts"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart"
import { Button } from "@/components/ui/button"
import { searchParams, updateUrl } from "@/lib/url-state"

// `label` must match the `title` returned by the API — lines are keyed by title.
const GYMS = [
  { id: "262", label: "Hannovergasse", color: "hsl(var(--chart-3))" },
  { id: "263", label: "Hauptbahnhof", color: "hsl(var(--chart-4))" },
  { id: "264", label: "Seestadt", color: "hsl(var(--chart-5))" },
  { id: "265", label: "Wienerberg", color: "hsl(221.2 83.2% 40%)" },
  { id: "284", label: "St. Pölten", color: "hsl(160 60% 30%)" },
  { id: "260", label: "Linz", color: "hsl(var(--chart-1))" },
  { id: "261", label: "Salzburg", color: "hsl(var(--chart-2))" },
]

const DAY_START_HOUR = 8
const DAY_RANGE_LABEL = "08:00–00:00"

// Quick-select presets shown as chips alongside the individual gyms.
const PRESETS = [
  { id: "all", label: "All", ids: GYMS.map(g => g.id) },
  { id: "wien", label: "Wien", ids: ["262", "263", "264", "265"] },
]

const CHART_CONFIG = Object.fromEntries(GYMS.map(g => [g.label, { label: g.label, color: g.color }]))

// Polling cadence is 5 min — break the line if there's a > 15 min gap.
const GAP_THRESHOLD_MS = 15 * 60 * 1000

interface Reading {
  location_id: number
  title: string
  capacity: number
  recorded_at: string
}

interface ChartPoint {
  ts: number
  [key: string]: number | null
}

function buildChartData(readings: Reading[], selectedIds: Set<string>): { data: ChartPoint[]; keys: string[] } {
  const keys = GYMS.filter(g => selectedIds.has(g.id)).map(g => g.label)
  const byTime: Record<string, ChartPoint> = {}

  for (const r of readings) {
    if (!selectedIds.has(String(r.location_id))) continue
    const ts = new Date(r.recorded_at).getTime()
    if (!byTime[r.recorded_at]) byTime[r.recorded_at] = { ts }
    byTime[r.recorded_at][r.title] = r.capacity
  }

  const sorted = Object.values(byTime).sort((a, b) => a.ts - b.ts)

  const withGaps: ChartPoint[] = []
  for (let i = 0; i < sorted.length; i++) {
    withGaps.push(sorted[i])
    const next = sorted[i + 1]
    if (next && next.ts - sorted[i].ts > GAP_THRESHOLD_MS) {
      const nullPoint: ChartPoint = { ts: sorted[i].ts + 1 }
      for (const k of keys) nullPoint[k] = null
      withGaps.push(nullPoint)
    }
  }

  return { data: withGaps, keys }
}

function formatTick(ts: number) {
  const d = new Date(ts)
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false })
}

function formatTooltipLabel(ts: string | number) {
  return new Date(Number(ts)).toLocaleString([], {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
  })
}

function selectionEquals(selected: Set<string>, ids: string[]) {
  return selected.size === ids.length && ids.every(id => selected.has(id))
}

function toDateValue(date: Date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

function dateFromValue(value: string) {
  const [year, month, day] = value.split("-").map(Number)
  return new Date(year, month - 1, day)
}

function shiftDate(value: string, days: number) {
  const date = dateFromValue(value)
  date.setDate(date.getDate() + days)
  return toDateValue(date)
}

function dayRange(value: string) {
  const date = dateFromValue(value)
  const start = new Date(date.getFullYear(), date.getMonth(), date.getDate(), DAY_START_HOUR)
  const end = new Date(date.getFullYear(), date.getMonth(), date.getDate() + 1)
  return { start, end }
}

function formatDayLabel(value: string, today: string) {
  if (value === today) return "Today"
  if (value === shiftDate(today, -1)) return "Yesterday"
  return dateFromValue(value).toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" })
}

function dayFromUrl(today: string) {
  const value = searchParams().get("d") ?? searchParams().get("date")
  if (!value || value > today || Number.isNaN(dateFromValue(value).getTime())) return today
  return value
}

function gymIdsFromUrl() {
  const value = searchParams().get("g") ?? searchParams().get("gyms")
  if (!value) return new Set(GYMS.map(gym => gym.id))

  const validIds = value.split(",").filter(id => GYMS.some(gym => gym.id === id))
  return validIds.length > 0 ? new Set(validIds) : new Set(GYMS.map(gym => gym.id))
}

export function HistoryView() {
  const [today] = useState(() => toDateValue(new Date()))
  const [selectedDay, setSelectedDay] = useState(() => dayFromUrl(today))
  const [selectedIds, setSelectedIds] = useState<Set<string>>(gymIdsFromUrl)
  const [readings, setReadings] = useState<Reading[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const { start, end } = useMemo(() => dayRange(selectedDay), [selectedDay])
  const selectedDayLabel = formatDayLabel(selectedDay, today)
  const allSelected = selectedIds.size === GYMS.length

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
      setLoading(true)
      setSelectedDay(current => current === nextDay ? current : nextDay)
      setSelectedIds(current => selectionEquals(current, [...nextIds]) ? current : nextIds)
    }
    window.addEventListener("popstate", syncSelection)
    return () => window.removeEventListener("popstate", syncSelection)
  }, [allSelected, selectedDay, selectedIds, today])

  useEffect(() => {
    let cancelled = false
    const fmt = (d: Date) => d.toISOString().replace(".000", "")
    const params = new URLSearchParams({ start: fmt(start), end: fmt(end) })

    fetch(`/history?${params}`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(d => {
        if (cancelled) return
        setReadings(d)
        setError(null)
      })
      .catch(e => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to fetch")
      })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [start, end])

  const { data, keys } = useMemo(() => buildChartData(readings, selectedIds), [readings, selectedIds])

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
    if (day === selectedDay) return
    setLoading(true)
    setSelectedDay(day)
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
        <CardHeader className="px-4 sm:px-6">
          <CardTitle className="text-base">
            {allSelected ? "All gyms" : `${selectedIds.size} gym${selectedIds.size === 1 ? "" : "s"}`} — {selectedDayLabel}, {DAY_RANGE_LABEL}
          </CardTitle>
        </CardHeader>
        <CardContent className="px-2 sm:px-6">
          {loading && <p className="text-sm text-muted-foreground py-12 text-center">Loading…</p>}
          {error && <p className="text-sm text-destructive py-12 text-center">Error: {error}</p>}
          {!loading && !error && data.length === 0 && (
            <p className="text-sm text-muted-foreground py-12 text-center">No data for this range.</p>
          )}
          {!loading && !error && data.length > 0 && (
            <ChartContainer config={CHART_CONFIG} className="h-72 w-full">
              <LineChart data={data} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="ts"
                  type="number"
                  scale="time"
                  domain={[start.getTime(), end.getTime()]}
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
                {keys.map(key => (
                  <Line
                    key={key}
                    type="monotone"
                    dataKey={key}
                    stroke={CHART_CONFIG[key]?.color}
                    strokeWidth={2}
                    dot={false}
                  />
                ))}
              </LineChart>
            </ChartContainer>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
