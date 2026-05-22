import { useEffect, useMemo, useState } from "react"
import { LineChart, Line, XAxis, YAxis, CartesianGrid } from "recharts"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
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

const RANGES = [
  { value: "6h", label: "Last 6 h", hours: 6 },
  { value: "24h", label: "Last 24 h", hours: 24 },
  { value: "7d", label: "Last 7 days", hours: 24 * 7 },
  { value: "30d", label: "Last 30 days", hours: 24 * 30 },
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

function formatTick(ts: number, rangeHours: number) {
  const d = new Date(ts)
  if (rangeHours <= 24) {
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false })
  }
  return d.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })
}

function formatTooltipLabel(ts: string | number) {
  return new Date(Number(ts)).toLocaleString([], {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
  })
}

export function HistoryView() {
  const [range, setRange] = useState("24h")
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set(GYMS.map(g => g.id)))
  const [readings, setReadings] = useState<Reading[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const rangeHours = RANGES.find(r => r.value === range)!.hours

  useEffect(() => {
    setLoading(true)
    const end = new Date()
    const start = new Date(end.getTime() - rangeHours * 3600_000)
    const fmt = (d: Date) => d.toISOString().replace(".000", "")
    const params = new URLSearchParams({ start: fmt(start), end: fmt(end) })

    fetch(`/history?${params}`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(d => { setReadings(d); setError(null) })
      .catch(e => setError(e instanceof Error ? e.message : "Failed to fetch"))
      .finally(() => setLoading(false))
  }, [range, rangeHours])

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

  return (
    <div className="space-y-4">
      <Select value={range} onValueChange={setRange}>
        <SelectTrigger className="w-36">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {RANGES.map(r => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}
        </SelectContent>
      </Select>

      <div className="flex flex-wrap gap-2">
        {GYMS.map(g => {
          const active = selectedIds.has(g.id)
          return (
            <button
              key={g.id}
              onClick={() => toggle(g.id)}
              aria-pressed={active}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm transition-colors",
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
        <CardHeader>
          <CardTitle className="text-base">
            {allSelected ? "All gyms" : `${selectedIds.size} gym${selectedIds.size === 1 ? "" : "s"}`} — {RANGES.find(r => r.value === range)?.label}
          </CardTitle>
        </CardHeader>
        <CardContent>
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
                  domain={["dataMin", "dataMax"]}
                  tickFormatter={ts => formatTick(ts, rangeHours)}
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
