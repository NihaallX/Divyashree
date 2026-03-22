"use client"

import { useEffect, useState } from "react"
import { adminGetCalls } from "@/lib/api"
import { AdminShell } from "@/components/workspace/admin-shell"
import { useAdminSessionGuard } from "../_admin-helpers"

export default function AdminCallsPage() {
  const { ready, token, username } = useAdminSessionGuard()
  const [calls, setCalls] = useState<Array<Record<string, unknown>>>([])
  const [error, setError] = useState("")

  useEffect(() => {
    if (!ready || !token) return

    adminGetCalls(token, 100)
      .then(setCalls)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load calls"))
  }, [ready, token])

  if (!ready || !username) {
    return (
      <main className="min-h-screen bg-background text-foreground flex items-center justify-center">
        <p className="font-mono text-sm text-muted-foreground">Checking admin session...</p>
      </main>
    )
  }

  return (
    <AdminShell
      title="Calls"
      subtitle="Cross-client call feed with latest statuses and metadata."
      username={username}
    >
      <section className="rounded-2xl border border-foreground/15 bg-background/70 p-6">
        <h2 className="text-2xl font-display mb-4">Latest calls</h2>
        {error ? <p className="mb-4 text-sm text-red-600">{error}</p> : null}
        <pre className="overflow-auto rounded-xl border border-foreground/10 bg-muted/30 p-4 text-xs">
          {JSON.stringify(calls, null, 2)}
        </pre>
      </section>
    </AdminShell>
  )
}
