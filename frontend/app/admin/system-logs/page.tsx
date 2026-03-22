"use client"

import { useEffect, useState } from "react"
import { adminGetSystemLogs } from "@/lib/api"
import { AdminShell } from "@/components/workspace/admin-shell"
import { useAdminSessionGuard } from "../_admin-helpers"

export default function AdminSystemLogsPage() {
  const { ready, token, username } = useAdminSessionGuard()
  const [backendLogs, setBackendLogs] = useState<string[]>([])
  const [gatewayLogs, setGatewayLogs] = useState<string[]>([])
  const [error, setError] = useState("")

  useEffect(() => {
    if (!ready || !token) return

    Promise.all([
      adminGetSystemLogs(token, "backend", 200),
      adminGetSystemLogs(token, "voice-gateway", 200),
    ])
      .then(([backend, gateway]) => {
        setBackendLogs(backend.lines || [])
        setGatewayLogs(gateway.lines || [])
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load system logs"))
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
      title="System logs"
      subtitle="View backend and voice gateway logs for debugging and incident response."
      username={username}
    >
      {error ? <p className="mb-4 text-sm text-red-600">{error}</p> : null}

      <section className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-2xl border border-foreground/15 bg-background/70 p-6">
          <h2 className="text-2xl font-display mb-4">Backend</h2>
          <pre className="max-h-[520px] overflow-auto rounded-xl border border-foreground/10 bg-muted/30 p-4 text-xs">
            {backendLogs.join("\n") || "No backend logs"}
          </pre>
        </div>

        <div className="rounded-2xl border border-foreground/15 bg-background/70 p-6">
          <h2 className="text-2xl font-display mb-4">Voice gateway</h2>
          <pre className="max-h-[520px] overflow-auto rounded-xl border border-foreground/10 bg-muted/30 p-4 text-xs">
            {gatewayLogs.join("\n") || "No voice-gateway logs"}
          </pre>
        </div>
      </section>
    </AdminShell>
  )
}
