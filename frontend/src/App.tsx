import { useState } from "react"
import { LiveView } from "@/components/LiveView"
import { HistoryView } from "@/components/HistoryView"
import { cn } from "@/lib/utils"

type Tab = "live" | "history"

export default function App() {
  const [tab, setTab] = useState<Tab>("live")

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-5xl px-4 py-8 space-y-6">
        <header>
          <h1 className="text-2xl font-bold tracking-tight">Boulderbat</h1>
          <p className="text-sm text-muted-foreground mt-1">Live and historical capacity for Boulderbar locations</p>
        </header>

        <nav className="flex gap-1 border-b">
          {(["live", "history"] as Tab[]).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                "px-4 py-2 text-sm font-medium capitalize transition-colors border-b-2 -mb-px",
                tab === t
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              )}
            >
              {t}
            </button>
          ))}
        </nav>

        <main>
          {tab === "live" ? <LiveView /> : <HistoryView />}
        </main>
      </div>
    </div>
  )
}
