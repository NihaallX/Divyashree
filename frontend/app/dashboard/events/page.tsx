"use client"

import { useEffect, useState } from "react"
import { getUpcomingEvents } from "@/lib/api"
import { WorkspaceShell } from "@/components/workspace/workspace-shell"
import { useSessionGuard } from "../_client-helpers"

export default function EventsPage() {
  const { ready, user, token } = useSessionGuard()
  const [events, setEvents] = useState<Array<Record<string, unknown>>>([])
  const [error, setError] = useState("")

  useEffect(() => {
    if (!ready || !token) return

    getUpcomingEvents(token)
      .then((data) => setEvents(data.events || []))
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load events"))
  }, [ready, token])

  if (!ready || !user) {
    return (
      <main className="min-h-screen bg-background text-foreground flex items-center justify-center">
        <p className="font-mono text-sm text-muted-foreground">Checking session...</p>
      </main>
    )
  }

  return (
    <WorkspaceShell
      title="Events"
      subtitle="Track upcoming scheduled events linked to calls and campaigns."
      userLabel={user.name || user.email || "user"}
    >
      <section className="rounded-2xl border border-foreground/15 bg-background/70 p-6">
        <div className="mb-5 flex items-center justify-between gap-3">
          <h2 className="text-2xl font-display">Upcoming events</h2>
          <span className="rounded-full border border-foreground/20 px-3 py-1 text-xs font-mono">
            {events.length} total
          </span>
        </div>

        {error ? <p className="mb-4 text-sm text-red-600">{error}</p> : null}

        {events.length === 0 ? (
          <p className="text-muted-foreground">No upcoming events.</p>
        ) : (
          <div className="space-y-3">
            {events.map((event, idx) => (
              <article key={String(event.id || idx)} className="rounded-xl border border-foreground/10 p-4">
                <p className="font-medium">{String(event.title || "Untitled event")}</p>
                <p className="mt-1 text-sm text-muted-foreground">{String(event.scheduled_at || "-")}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Contact: {String(event.contact_name || "-")} | Type: {String(event.type || "-")}
                </p>
              </article>
            ))}
          </div>
        )}
      </section>
    </WorkspaceShell>
  )
}
