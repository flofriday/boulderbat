import { useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { MapPin, RefreshCw } from "lucide-react"

interface LiveReading {
  id: number
  title: string
  url: string
  capacity: number
  recorded_at: string
}

function capacityStatus(pct: number) {
  if (pct < 40) return { label: "Quiet", badgeClassName: "border-emerald-200 bg-emerald-50 text-emerald-700", barClassName: "bg-emerald-500" }
  if (pct < 70) return { label: "Moderate", badgeClassName: "border-amber-200 bg-amber-50 text-amber-700", barClassName: "bg-amber-500" }
  return { label: "Busy", badgeClassName: "border-red-200 bg-red-50 text-red-700", barClassName: "bg-red-500" }
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false })
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
    const initialFetch = window.setTimeout(() => { void fetchLive() }, 0)
    const refresh = window.setInterval(() => { void fetchLive() }, 60_000)
    return () => {
      window.clearTimeout(initialFetch)
      window.clearInterval(refresh)
    }
  }, [])

  if (loading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }, (_, index) => (
          <Card key={index}>
            <CardHeader className="space-y-3">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-7 w-20" />
            </CardHeader>
            <CardContent><Skeleton className="h-2 w-full" /></CardContent>
          </Card>
        ))}
      </div>
    )
  }
  if (error) {
    return (
      <Card className="border-destructive/30">
        <CardContent className="flex flex-col gap-3 p-6 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-destructive">Could not load live capacity: {error}</p>
          <Button variant="outline" size="sm" onClick={fetchLive}>Try again</Button>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          {lastFetch ? <>Updated at {lastFetch.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false })}</> : null}
        </p>
        <Button
          onClick={fetchLive}
          variant="outline"
          size="sm"
        >
          <RefreshCw className="size-3.5" />
          Refresh
        </Button>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {data.map((loc) => (
          <Card key={loc.id} className="overflow-hidden">
            <CardHeader className="flex-row items-start justify-between space-y-0 pb-3">
              <CardTitle className="flex min-w-0 items-center gap-2 text-base">
                <MapPin className="size-4 shrink-0 text-muted-foreground" />
                <a href={loc.url} target="_blank" rel="noopener noreferrer" className="truncate hover:underline">
                  {loc.title}
                </a>
              </CardTitle>
              <Badge variant="outline" className={capacityStatus(loc.capacity).badgeClassName}>
                {capacityStatus(loc.capacity).label}
              </Badge>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex items-end justify-between">
                <span className="text-3xl font-bold tabular-nums">{loc.capacity}%</span>
                <span className="text-xs text-muted-foreground">{formatTime(loc.recorded_at)}</span>
              </div>
              <div className="h-2 w-full rounded-full bg-secondary overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${capacityStatus(loc.capacity).barClassName}`}
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
