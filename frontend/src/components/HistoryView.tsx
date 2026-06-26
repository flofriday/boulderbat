import { useEffect, useMemo, useState } from "react"
import { LineChart, Line, XAxis, YAxis, CartesianGrid } from "recharts"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart"
import { cn } from "@/lib/utils"

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

export function HistoryView() {
  const [today] = useState(() => toDateValue(new Date()))
  const [selectedDay, setSelectedDay] = useState(() => toDateValue(new Date()))
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set(GYMS.map(g => g.id)))
  const [readings, setReadings] = useState<Reading[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const { start, end } = useMemo(() => dayRange(selectedDay), [selectedDay])
  const selectedDayLabel = formatDayLabel(selectedDay, today)

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
    setSelectedIds(prev => {
      // From the "all" state, a click isolates to just that gym.
      if (prev.size === GYMS.length) return new Set([id])
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      // Clearing the last selection falls back to all.
      return next.size === 0 ? new Set(GYMS.map(g => g.id)) : next
    })
  }

  const allSelected = selectedIds.size === GYMS.length

  function selectDay(day: string) {
    if (day === selectedDay) return
    setLoading(true)
    setSelectedDay(day)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => selectDay(shiftDate(selectedDay, -1))}
          aria-label="Previous day"
          className="inline-flex size-10 items-center justify-center rounded-md border text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <ChevronLeft className="size-4" />
        </button>
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
        <button
          type="button"
          onClick={() => selectDay(shiftDate(selectedDay, 1))}
          disabled={selectedDay === today}
          aria-label="Next day"
          className="inline-flex size-10 items-center justify-center rounded-md border text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:pointer-events-none disabled:opacity-40"
        >
          <ChevronRight className="size-4" />
        </button>
        {selectedDay !== today && (
          <button
            type="button"
            onClick={() => selectDay(today)}
            className="text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            Today
          </button>
        )}
      </div>

      <div className="flex items-center gap-2 overflow-x-auto pb-1 -mx-4 px-4 sm:mx-0 sm:px-0 sm:flex-wrap sm:overflow-visible sm:pb-0">
        {PRESETS.map(p => {
          const active = selectionEquals(selectedIds, p.ids)
          return (
            <button
              key={p.id}
              onClick={() => setSelectedIds(new Set(p.ids))}
              aria-pressed={active}
              className={cn(
                "inline-flex shrink-0 items-center whitespace-nowrap rounded-full border px-3 py-1 text-sm transition-colors",
                active ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground"
              )}
            >
              {p.label}
            </button>
          )
        })}
        <span className="mx-1 h-5 w-px shrink-0 bg-border" />
        {GYMS.map(g => {
          const active = selectedIds.has(g.id)
          return (
            <button
              key={g.id}
              onClick={() => toggle(g.id)}
              aria-pressed={active}
              className={cn(
                "inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-3 py-1 text-sm transition-colors",
                active ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground"
              )}
            >
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-full border"
                style={active
                  ? { backgroundColor: g.color, borderColor: g.color }
                  : { backgroundColor: "transparent", borderColor: "currentColor" }}
              />
              {g.label}
            </button>
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
