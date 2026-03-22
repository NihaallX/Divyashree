"use client"

import { useEffect, useState } from "react"
import { API_BASE_URL } from "@/lib/config"
import { getHealth } from "@/lib/api"
import { ContentShell } from "@/components/workspace/content-shell"

type JsonValue = Record<string, unknown>

export default function StatusPage() {
  const [health, setHealth] = useState<JsonValue | null>(null)
  const [info, setInfo] = useState<JsonValue | null>(null)
  const [error, setError] = useState("")

  useEffect(() => {
    let mounted = true

    async function load() {
      try {
        const [healthData, infoRes] = await Promise.all([
          getHealth(),
          fetch(`${API_BASE_URL}/info`).then((r) => r.json()),
        ])
        if (!mounted) return
        setHealth(healthData)
        setInfo(infoRes)
      } catch (err) {
        if (!mounted) return
        setError(err instanceof Error ? err.message : "Failed to load service status")
      }
    }

    load()
    return () => {
      mounted = false
    }
  }, [])

  return (
    <ContentShell
      eyebrow="Developers"
      title="Status"
      description="Live runtime checks from backend health and info endpoints."
      maxWidthClassName="max-w-4xl"
    >
      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      <section className="grid gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-foreground/15 bg-background/70 p-5">
          <h2 className="font-medium mb-3">GET /health</h2>
          <pre className="overflow-auto rounded-lg bg-muted/30 p-3 text-xs">{JSON.stringify(health, null, 2)}</pre>
        </div>

        <div className="rounded-xl border border-foreground/15 bg-background/70 p-5">
          <h2 className="font-medium mb-3">GET /info</h2>
          <pre className="overflow-auto rounded-lg bg-muted/30 p-3 text-xs">{JSON.stringify(info, null, 2)}</pre>
        </div>
      </section>
    </ContentShell>
  )
}
