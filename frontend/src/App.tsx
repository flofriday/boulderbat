import { useEffect, useState } from "react"
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
import { TypicalWeekView } from "@/components/TypicalWeekView"
import { Button } from "@/components/ui/button"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { searchParams, updateUrl } from "@/lib/url-state"

type Tab = "live" | "history" | "typical-week"

const TABS: { id: Tab; label: string }[] = [
  { id: "live", label: "Live" },
  { id: "history", label: "History" },
  { id: "typical-week", label: "Typical week" },
]

const TAB_URL_VALUES: Record<Tab, string> = {
  live: "l",
  history: "h",
  "typical-week": "w",
}

function tabFromUrl(): Tab {
  const tab = searchParams().get("t")
  if (tab === "h") return "history"
  if (tab === "w") return "typical-week"
  if (tab === "l") return "live"

  // Accept previously shared URLs and normalize them to the shorter form.
  const legacyTab = searchParams().get("tab")
  return TABS.some(candidate => candidate.id === legacyTab) ? legacyTab as Tab : "live"
}

export default function App() {
  const [tab, setTab] = useState<Tab>(tabFromUrl)

  useEffect(() => {
    if (searchParams().get("t") !== TAB_URL_VALUES[tab] || searchParams().has("tab")) {
      updateUrl({ t: TAB_URL_VALUES[tab], tab: null }, true)
    }

    const syncTab = () => setTab(tabFromUrl())
    window.addEventListener("popstate", syncTab)
    return () => window.removeEventListener("popstate", syncTab)
  }, [tab])

  function selectTab(nextTab: Tab) {
    if (nextTab === tab) return
    setTab(nextTab)
    updateUrl({
      t: TAB_URL_VALUES[nextTab],
      d: null,
      g: null,
      tab: null,
      date: null,
      gyms: null,
      gym: null,
    })
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-6xl space-y-6 px-4 py-6 sm:py-8">
        <header className="flex items-center gap-3 sm:gap-4">
          <img src={logo} alt="" className="size-10 rounded-lg sm:size-12" />
          <div className="min-w-0">
            <h1 className="text-xl font-bold tracking-tight sm:text-2xl">Boulderbat</h1>
            <p className="truncate text-sm text-muted-foreground">Find the best time to hang out at the gym</p>
          </div>
          <div className="ml-auto flex items-center gap-1">
            <Button asChild variant="ghost" size="sm">
              <a href="/docs" target="_blank" rel="noopener noreferrer">
                API docs
                <ExternalLink className="size-4" />
              </a>
            </Button>
            <Button asChild variant="ghost" size="icon-sm">
              <a
                href="https://github.com/flofriday/boulderbat"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="GitHub repository"
              >
                <GithubIcon className="size-4" />
              </a>
            </Button>
          </div>
        </header>

        <Tabs value={tab} onValueChange={value => selectTab(value as Tab)}>
          <nav className="overflow-x-auto pb-1" aria-label="Main navigation">
            <TabsList className="h-auto min-w-max gap-1 rounded-lg p-1">
              {TABS.map(item => (
                <TabsTrigger key={item.id} value={item.id} className="h-9 px-3 sm:px-4">
                  {item.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </nav>
        </Tabs>

        <main>
          {tab === "live" && <LiveView />}
          {tab === "history" && <HistoryView />}
          {tab === "typical-week" && <TypicalWeekView />}
        </main>
      </div>
    </div>
  )
}
