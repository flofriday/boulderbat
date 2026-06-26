import { useEffect, useMemo, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { searchParams, updateUrl } from "@/lib/url-state"

const GYMS = [
  { id: "262", label: "Hannovergasse", color: "hsl(var(--chart-3))" },
  { id: "263", label: "Hauptbahnhof", color: "hsl(var(--chart-4))" },
  { id: "264", label: "Seestadt", color: "hsl(var(--chart-5))" },
  { id: "265", label: "Wienerberg", color: "hsl(221.2 83.2% 40%)" },
  { id: "284", label: "St. Pölten", color: "hsl(160 60% 30%)" },
  { id: "260", label: "Linz", color: "hsl(var(--chart-1))" },
  { id: "261", label: "Salzburg", color: "hsl(var(--chart-2))" },
]

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
const HOURS = Array.from({ length: 16 }, (_, index) => index + 8)

interface TypicalWeekCell {
  weekday: number
  hour: number
  average_capacity: number
  sample_count: number
}

interface TypicalWeekResponse {
  cells: TypicalWeekCell[]
  week_count: number
}

function heatColor(capacity: number | undefined) {
  if (capacity === undefined) return "hsl(var(--muted))"
  const intensity = Math.min(capacity / 50, 1)
  const hue = 48 - intensity * 48
  const lightness = 94 - intensity * 48
  return `hsl(${hue} 95% ${lightness}%)`
}

function hourLabel(hour: number) {
  return `${String(hour).padStart(2, "0")}:00`
}

function gymIdFromUrl() {
  const gymId = searchParams().get("g") ?? searchParams().get("gym")
  return gymId && GYMS.some(gym => gym.id === gymId) ? gymId : GYMS[0].id
}

export function TypicalWeekView() {
  const [selectedGymId, setSelectedGymId] = useState(gymIdFromUrl)
  const [cells, setCells] = useState<TypicalWeekCell[]>([])
  const [weekCount, setWeekCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch(`/typical-week?${new URLSearchParams({ location_id: selectedGymId })}`)
      .then(response => { if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.json() })
      .then((data: TypicalWeekResponse) => {
        if (cancelled) return
        setCells(data.cells)
        setWeekCount(data.week_count)
        setError(null)
      })
      .catch(fetchError => {
        if (!cancelled) setError(fetchError instanceof Error ? fetchError.message : "Failed to fetch")
      })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [selectedGymId])

  const cellsByTime = useMemo(
    () => new Map(cells.map(cell => [`${cell.weekday}-${cell.hour}`, cell])),
    [cells],
  )
  const selectedGym = GYMS.find(gym => gym.id === selectedGymId)!
  const totalSamples = cells.reduce((sum, cell) => sum + cell.sample_count, 0)

  useEffect(() => {
    const params = searchParams()
    if (
      params.get("g") !== selectedGymId ||
      params.has("d") ||
      params.has("date") ||
      params.has("gyms") ||
      params.has("gym")
    ) {
      updateUrl({ d: null, g: selectedGymId, date: null, gyms: null, gym: null }, true)
    }

    const syncGym = () => {
      const nextGymId = gymIdFromUrl()
      setLoading(true)
      setSelectedGymId(current => current === nextGymId ? current : nextGymId)
    }
    window.addEventListener("popstate", syncGym)
    return () => window.removeEventListener("popstate", syncGym)
  }, [selectedGymId])

  function selectGym(gymId: string) {
    if (gymId === selectedGymId) return
    setLoading(true)
    setSelectedGymId(gymId)
    updateUrl({ g: gymId })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 overflow-x-auto pb-1 -mx-4 px-4 sm:mx-0 sm:px-0 sm:flex-wrap sm:overflow-visible sm:pb-0">
        {GYMS.map(gym => {
          const active = gym.id === selectedGymId
          return (
            <button
              key={gym.id}
              onClick={() => selectGym(gym.id)}
              aria-pressed={active}
              className={cn(
                "inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-3 py-1 text-sm transition-colors",
                active ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground",
              )}
            >
              <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: gym.color }} />
              {gym.label}
            </button>
          )
        })}
      </div>

      <Card>
        <CardHeader className="px-4 sm:px-6">
          <CardTitle className="text-base">Typical week — {selectedGym.label}</CardTitle>
          {!loading && !error && cells.length > 0 && (
            <p className="text-sm text-muted-foreground">Average capacity by local weekday and hour.</p>
          )}
        </CardHeader>
        <CardContent className="px-4 sm:px-6">
          {loading && <p className="py-12 text-center text-sm text-muted-foreground">Loading…</p>}
          {error && <p className="py-12 text-center text-sm text-destructive">Error: {error}</p>}
          {!loading && !error && cells.length === 0 && (
            <p className="py-12 text-center text-sm text-muted-foreground">Not enough history for this gym yet.</p>
          )}
          {!loading && !error && cells.length > 0 && (
            <div className="space-y-5">
              <div className="overflow-x-auto">
                <div className="grid min-w-[38rem] grid-cols-8 gap-px overflow-hidden rounded-md border bg-border">
                  <div className="bg-card" />
                  {DAYS.map(day => <div key={day} className="bg-card px-1 py-2 text-center text-xs font-medium">{day}</div>)}
                  {HOURS.flatMap(hour => [
                    <div key={`${hour}-label`} className="bg-card pr-2 py-1 text-right text-xs text-muted-foreground">{hourLabel(hour)}</div>,
                    ...DAYS.map((_, weekday) => {
                      const cell = cellsByTime.get(`${weekday}-${hour}`)
                      const label = cell
                        ? `${DAYS[weekday]} ${hourLabel(hour)}: ${Math.round(cell.average_capacity)}% average capacity from ${cell.sample_count} readings`
                        : `${DAYS[weekday]} ${hourLabel(hour)}: no data`
                      return (
                        <div
                          key={`${weekday}-${hour}`}
                          title={label}
                          aria-label={label}
                          className="h-7 transition-opacity hover:opacity-75"
                          style={{ backgroundColor: heatColor(cell?.average_capacity) }}
                        />
                      )
                    }),
                  ])}
                </div>
              </div>

              <div className="flex items-center gap-3 text-sm text-muted-foreground">
                <span>Quiet</span>
                <div className="flex overflow-hidden rounded-sm">
                  {[0, 10, 20, 30, 40, 50].map(value => (
                    <span key={value} className="h-4 w-9" style={{ backgroundColor: heatColor(value) }} />
                  ))}
                </div>
                <span>Busy</span>
              </div>
              <p className="text-xs text-muted-foreground">
                Based on {totalSamples.toLocaleString()} readings across {weekCount} calendar week{weekCount === 1 ? "" : "s"}.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
