import { useState } from "react"
import { ExternalLink } from "lucide-react"
import logo from "@/assets/logo.svg"

function GithubIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" className={className}>
      <path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.1.79-.25.79-.56v-2.17c-3.2.7-3.87-1.36-3.87-1.36-.52-1.33-1.28-1.68-1.28-1.68-1.05-.72.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.7 1.26 3.36.96.1-.75.4-1.26.73-1.55-2.55-.29-5.24-1.28-5.24-5.67 0-1.25.45-2.27 1.19-3.07-.12-.29-.52-1.47.11-3.07 0 0 .97-.31 3.17 1.17.92-.26 1.91-.39 2.89-.39.98 0 1.97.13 2.89.39 2.2-1.48 3.17-1.17 3.17-1.17.63 1.6.23 2.78.11 3.07.74.8 1.19 1.82 1.19 3.07 0 4.4-2.69 5.37-5.25 5.66.41.35.78 1.05.78 2.12v3.14c0 .31.21.67.8.56C20.21 21.39 23.5 17.08 23.5 12 23.5 5.65 18.35.5 12 .5z" />
    </svg>
  )
}
import { LiveView } from "@/components/LiveView"
import { HistoryView } from "@/components/HistoryView"
import { cn } from "@/lib/utils"

type Tab = "live" | "history"

export default function App() {
  const [tab, setTab] = useState<Tab>("live")

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-5xl px-4 py-8 space-y-6">
        <header className="flex items-center gap-4">
          <img src={logo} alt="" className="h-12 w-12 rounded-lg" />
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Boulderbat</h1>
            <p className="text-sm text-muted-foreground mt-1">Find the best time to hang out at the gym</p>
          </div>
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
          <a
            href="/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors border-b-2 border-transparent -mb-px"
          >
            API
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
          <a
            href="https://github.com/flofriday/boulderbat"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="GitHub repository"
            className="inline-flex items-center px-3 py-2 text-muted-foreground hover:text-foreground transition-colors border-b-2 border-transparent -mb-px"
          >
            <GithubIcon className="h-4 w-4" />
          </a>
        </nav>

        <main>
          {tab === "live" ? <LiveView /> : <HistoryView />}
        </main>
      </div>
    </div>
  )
}
