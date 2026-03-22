"use client"

import { useEffect, useState } from "react"
import { adminGetAgents } from "@/lib/api"
import { AdminShell } from "@/components/workspace/admin-shell"
import { useAdminSessionGuard } from "../_admin-helpers"

export default function AdminAgentsPage() {
  const { ready, token, username } = useAdminSessionGuard()
  const [agents, setAgents] = useState<Array<Record<string, unknown>>>([])
  const [error, setError] = useState("")

  useEffect(() => {
    if (!ready || !token) return

    adminGetAgents(token)
      .then(setAgents)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load agents"))
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
      title="Agents"
      subtitle="Admin view of all agents across all client accounts."
      username={username}
    >
      <section className="rounded-2xl border border-foreground/15 bg-background/70 p-6">
        <h2 className="text-2xl font-display mb-4">All agents</h2>
        {error ? <p className="mb-4 text-sm text-red-600">{error}</p> : null}
        <pre className="overflow-auto rounded-xl border border-foreground/10 bg-muted/30 p-4 text-xs">
          {JSON.stringify(agents, null, 2)}
        </pre>
      </section>
    </AdminShell>
  )
}
