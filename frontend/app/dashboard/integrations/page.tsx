"use client"

import { useEffect, useState } from "react"
import { getCalBookings, getCalStatus } from "@/lib/api"
import { WorkspaceShell } from "@/components/workspace/workspace-shell"
import { useSessionGuard } from "../_client-helpers"

export default function IntegrationsPage() {
  const { ready, user, token } = useSessionGuard()
  const [status, setStatus] = useState<Record<string, unknown> | null>(null)
  const [bookings, setBookings] = useState<Array<Record<string, unknown>>>([])
  const [error, setError] = useState("")

  useEffect(() => {
    if (!ready || !token) return

    Promise.all([getCalStatus(token), getCalBookings(token)])
      .then(([statusData, bookingsData]) => {
        setStatus(statusData)
        setBookings(bookingsData.bookings || [])
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load integration status"))
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
      title="Integrations"
      subtitle="Monitor Cal.com connectivity and upcoming booking records."
      userLabel={user.name || user.email || "user"}
    >
      {error ? <p className="mb-4 text-sm text-red-600">{error}</p> : null}

      <section className="grid gap-6 lg:grid-cols-[0.95fr_1.05fr]">
        <div className="rounded-2xl border border-foreground/15 bg-background/70 p-6">
          <h2 className="text-2xl font-display">Cal.com status</h2>
          <pre className="mt-4 overflow-auto rounded-xl border border-foreground/10 bg-muted/30 p-4 text-xs">
            {JSON.stringify(status, null, 2)}
          </pre>
        </div>

        <div className="rounded-2xl border border-foreground/15 bg-background/70 p-6">
          <h2 className="text-2xl font-display">Recent bookings</h2>
          {bookings.length === 0 ? (
            <p className="mt-4 text-muted-foreground">No bookings available.</p>
          ) : (
            <div className="mt-4 space-y-3">
              {bookings.map((booking, idx) => (
                <article key={String(booking.id || idx)} className="rounded-xl border border-foreground/10 p-4">
                  <p className="font-medium">{String(booking.title || booking.uid || "Booking")}</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {String(booking.startTime || booking.start || booking.created_at || "-")}
                  </p>
                </article>
              ))}
            </div>
          )}
        </div>
      </section>
    </WorkspaceShell>
  )
}
