import { useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { MapPin, RefreshCw } from "lucide-react"

interface LiveReading {
  id: number
  title: string
  url: string
  capacity: number
  recorded_at: string
}

function capacityColor(pct: number) {
  if (pct < 40) return "bg-green-500"
  if (pct < 70) return "bg-yellow-500"
  return "bg-red-500"
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
}

export function LiveView() {
  const [data, setData] = useState<LiveReading[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastFetch, setLastFetch] = useState<Date | null>(null)

  async function fetchLive() {
    try {
      const res = await fetch("/live")
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setData(await res.json())
      setLastFetch(new Date())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchLive()
    const id = setInterval(fetchLive, 60_000)
    return () => clearInterval(id)
  }, [])

  if (loading) return <p className="text-muted-foreground text-sm">Loading…</p>
  if (error) return <p className="text-destructive text-sm">Error: {error}</p>

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {lastFetch ? <>Updated at {lastFetch.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</> : null}
        </p>
        <button
          onClick={fetchLive}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <RefreshCw className="h-3 w-3" />
          Refresh
        </button>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {data.map((loc) => (
          <Card key={loc.id}>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <MapPin className="h-4 w-4 text-muted-foreground shrink-0" />
                <a href={loc.url} target="_blank" rel="noopener noreferrer" className="hover:underline truncate">
                  {loc.title}
                </a>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex items-end justify-between">
                <span className="text-3xl font-bold tabular-nums">{loc.capacity}%</span>
                <span className="text-xs text-muted-foreground">{formatTime(loc.recorded_at)}</span>
              </div>
              <div className="h-2 w-full rounded-full bg-secondary overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${capacityColor(loc.capacity)}`}
                  style={{ width: `${loc.capacity}%` }}
                />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
