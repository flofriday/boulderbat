export const HISTORY_TIMEZONE = "Europe/Vienna"
export const GAP_THRESHOLD_MS = 15 * 60 * 1000

export interface Reading {
  location_id: number
  title: string
  capacity: number
  recorded_at: string
}

export interface PredictionResponse {
  date: string
  generated_at: string
  context_end: string
  valid_until: string
  locations: {
    location_id: number
    title: string
    status: "ok" | "unavailable"
    reason: string | null
    points: { recorded_at: string; capacity: number; p10: number; p90: number }[]
  }[]
}

export interface ChartPoint {
  ts: number
  [key: string]: number | null | [number, number]
}

export function viennaDay(date: Date) {
  return new Intl.DateTimeFormat("sv-SE", { timeZone: HISTORY_TIMEZONE }).format(date)
}

export function validDay(value: string) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) &&
    !Number.isNaN(Date.parse(`${value}T12:00:00Z`)) &&
    new Date(`${value}T12:00:00Z`).toISOString().slice(0, 10) === value
}

export function shiftDate(value: string, days: number) {
  const date = new Date(`${value}T12:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

function localTimestamp(value: string, hour: number) {
  const [year, month, day] = value.split("-").map(Number)
  const wallTime = Date.UTC(year, month - 1, day, hour)
  let timestamp = wallTime
  // Resolve the offset at this wall-clock time, including DST transition dates.
  const formatter = new Intl.DateTimeFormat("en-GB", {
    timeZone: HISTORY_TIMEZONE, year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
  })
  for (let i = 0; i < 3; i++) {
    const p = Object.fromEntries(formatter.formatToParts(timestamp).map(part => [part.type, part.value]))
    const localAsUTC = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute, +p.second)
    timestamp = wallTime - (localAsUTC - timestamp)
  }
  return new Date(timestamp)
}

export function dayRange(value: string) {
  return { start: localTimestamp(value, 8), end: localTimestamp(shiftDate(value, 1), 0) }
}

export function chartData(readings: Reading[], prediction: PredictionResponse | undefined, selectedIds: Set<string>) {
  const byTime = new Map<number, ChartPoint>()
  const latestReadings = new Map<number, { ts: number; capacity: number }>()
  for (const reading of readings) {
    if (!selectedIds.has(String(reading.location_id))) continue
    const ts = Date.parse(reading.recorded_at)
    const point = byTime.get(ts) ?? { ts }
    point[`observed_${reading.location_id}`] = reading.capacity
    byTime.set(ts, point)
    if (Number.isFinite(reading.capacity) && (!latestReadings.has(reading.location_id) || ts > latestReadings.get(reading.location_id)!.ts)) {
      latestReadings.set(reading.location_id, { ts, capacity: reading.capacity })
    }
  }
  const observed: ChartPoint[] = []
  const sorted = [...byTime.values()].sort((a, b) => a.ts - b.ts)
  for (let i = 0; i < sorted.length; i++) {
    observed.push(sorted[i])
    if (sorted[i + 1] && sorted[i + 1].ts - sorted[i].ts > GAP_THRESHOLD_MS) {
      observed.push({ ts: sorted[i].ts + 1, ...Object.fromEntries([...selectedIds].map(id => [`observed_${id}`, null])) })
    }
  }
  const futureByTime = new Map<number, ChartPoint>()
  const connectors: { location_id: number; data: ChartPoint[] }[] = []
  let lastReading: number | null = null
  for (const location of prediction?.locations ?? []) {
    if (!selectedIds.has(String(location.location_id)) || location.status !== "ok") continue
    const latest = latestReadings.get(location.location_id)
    if (latest && location.points.length > 0) {
      lastReading = Math.max(lastReading ?? latest.ts, latest.ts)
      const first = location.points[0]
      const firstTime = Date.parse(first.recorded_at)
      if (firstTime > latest.ts && firstTime - latest.ts <= GAP_THRESHOLD_MS) {
        // Only the dashed visual connector is interpolated. Observations and
        // Timestral's uncertainty bounds keep their original values/timestamps.
        connectors.push({ location_id: location.location_id, data: [
          { ts: latest.ts, capacity: latest.capacity },
          { ts: firstTime, capacity: first.capacity },
        ] })
      }
    }
    for (const value of location.points) {
      const ts = Date.parse(value.recorded_at)
      const point = futureByTime.get(ts) ?? { ts }
      point[`prediction_${location.location_id}`] = value.capacity
      point[`uncertainty_${location.location_id}`] = [value.p10, value.p90]
      futureByTime.set(ts, point)
    }
  }
  const future = [...futureByTime.values()].sort((a, b) => a.ts - b.ts)
  return { observed, future, connectors, lastReading, data: [...observed, ...future].sort((a, b) => a.ts - b.ts) }
}
