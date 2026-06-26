export type UrlValue = string | null

export function searchParams() {
  return new URLSearchParams(window.location.search)
}

export function updateUrl(values: Record<string, UrlValue>, replace = false) {
  const url = new URL(window.location.href)
  for (const [key, value] of Object.entries(values)) {
    if (value === null) url.searchParams.delete(key)
    else url.searchParams.set(key, value)
  }

  window.history[replace ? "replaceState" : "pushState"]({}, "", url)
}
