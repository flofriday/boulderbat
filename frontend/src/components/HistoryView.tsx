import { useEffect, useState } from "react"
import { LineChart, Line, XAxis, YAxis, CartesianGrid } from "recharts"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

const LOCATIONS = [
  { id: "all", label: "All locations" },
  { id: "260", label: "Linz" },
  { id: "261", label: "Salzburg" },
  { id: "262", label: "Hannovergasse" },
  { id: "263", label: "Hauptbahnhof" },
  { id: "264", label: "Seestadt" },
  { id: "265", label: "Wienerberg" },
  { id: "284", label: "St. Pölten" },
]

const RANGES = [
  { value: "6h", label: "Last 6 h", hours: 6 },
  { value: "24h", label: "Last 24 h", hours: 24 },
  { value: "7d", label: "Last 7 days", hours: 24 * 7 },
  { value: "30d", label: "Last 30 days", hours: 24 * 30 },
]

const LOCATION_COLORS: Record<string, string> = {
  "260": "hsl(var(--chart-1))",
  "261": "hsl(var(--chart-2))",
  "262": "hsl(var(--chart-3))",
  "263": "hsl(var(--chart-4))",
  "264": "hsl(var(--chart-5))",
  "265": "hsl(221.2 83.2% 40%)",
  "284": "hsl(160 60% 30%)",
}

interface Reading {
  location_id: number
  title: string
  capacity: number
  recorded_at: string
}

interface ChartPoint {
  time: string
  [key: string]: string | number
}

function buildChartData(readings: Reading[], locationId: string): { data: ChartPoint[]; keys: string[] } {
  const byTime: Record<string, ChartPoint> = {}
  const keySet = new Set<string>()

  for (const r of readings) {
    const label = locationId === "all" ? r.title : "Capacity"
    keySet.add(label)
    const time = new Date(r.recorded_at).toLocaleString([], {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    })
    if (!byTime[r.recorded_at]) byTime[r.recorded_at] = { time }
    byTime[r.recorded_at][label] = r.capacity
  }

  return {
    data: Object.values(byTime).sort((a, b) => a.time < b.time ? -1 : 1),
    keys: Array.from(keySet),
  }
}

export function HistoryView() {
  const [range, setRange] = useState("24h")
  const [locationId, setLocationId] = useState("all")
  const [readings, setReadings] = useState<Reading[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    const rangeHours = RANGES.find(r => r.value === range)!.hours
    const end = new Date()
    const start = new Date(end.getTime() - rangeHours * 3600_000)
    const fmt = (d: Date) => d.toISOString().replace(".000", "")
    const params = new URLSearchParams({ start: fmt(start), end: fmt(end) })
    if (locationId !== "all") params.set("location_id", locationId)

    fetch(`/history?${params}`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(d => { setReadings(d); setError(null) })
      .catch(e => setError(e instanceof Error ? e.message : "Failed to fetch"))
      .finally(() => setLoading(false))
  }, [range, locationId])

  const { data, keys } = buildChartData(readings, locationId)

  const chartConfig = Object.fromEntries(
    LOCATIONS.filter(l => l.id !== "all").map((l, i) => [
      l.label,
      { label: l.label, color: LOCATION_COLORS[l.id] || `hsl(var(--chart-${(i % 5) + 1}))` },
    ])
  )
  if (locationId !== "all") {
    chartConfig["Capacity"] = { label: "Capacity", color: "hsl(var(--chart-1))" }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3">
        <Select value={range} onValueChange={setRange}>
          <SelectTrigger className="w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {RANGES.map(r => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={locationId} onValueChange={setLocationId}>
          <SelectTrigger className="w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {LOCATIONS.map(l => <SelectItem key={l.id} value={l.id}>{l.label}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {locationId === "all" ? "All locations" : LOCATIONS.find(l => l.id === locationId)?.label} — {RANGES.find(r => r.value === range)?.label}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading && <p className="text-sm text-muted-foreground py-12 text-center">Loading…</p>}
          {error && <p className="text-sm text-destructive py-12 text-center">Error: {error}</p>}
          {!loading && !error && data.length === 0 && (
            <p className="text-sm text-muted-foreground py-12 text-center">No data for this range.</p>
          )}
          {!loading && !error && data.length > 0 && (
            <ChartContainer config={chartConfig} className="h-72 w-full">
              <LineChart data={data} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="time"
                  tick={{ fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  minTickGap={60}
                />
                <YAxis
                  domain={[0, 100]}
                  tickFormatter={v => `${v}%`}
                  tick={{ fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                />
                <ChartTooltip content={<ChartTooltipContent />} />
                {keys.map((key, i) => (
                  <Line
                    key={key}
                    type="monotone"
                    dataKey={key}
                    stroke={chartConfig[key]?.color || `hsl(var(--chart-${(i % 5) + 1}))`}
                    strokeWidth={2}
                    dot={false}
                    connectNulls
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
