"use client"

import { useEffect, useState } from "react"
import { adminGetAuditLogs } from "@/lib/api"
import { AdminShell } from "@/components/workspace/admin-shell"
import { useAdminSessionGuard } from "../_admin-helpers"

export default function AdminAuditPage() {
  const { ready, token, username } = useAdminSessionGuard()
  const [logs, setLogs] = useState<Array<Record<string, unknown>>>([])
  const [error, setError] = useState("")

  useEffect(() => {
    if (!ready || !token) return

    adminGetAuditLogs(token, 150)
      .then((res) => setLogs(res.logs || []))
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load audit logs"))
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
      title="Audit"
      subtitle="Track activity events and operational changes across platform resources."
      username={username}
    >
      <section className="rounded-2xl border border-foreground/15 bg-background/70 p-6">
        <h2 className="text-2xl font-display mb-4">Audit logs</h2>
        {error ? <p className="mb-4 text-sm text-red-600">{error}</p> : null}
        <pre className="overflow-auto rounded-xl border border-foreground/10 bg-muted/30 p-4 text-xs">
          {JSON.stringify(logs, null, 2)}
        </pre>
      </section>
    </AdminShell>
  )
}
