"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"
import { adminGetClientDetail } from "@/lib/api"
import { AdminShell } from "@/components/workspace/admin-shell"
import { useAdminSessionGuard } from "../../_admin-helpers"

export default function AdminClientDetailPage() {
  const { clientId } = useParams<{ clientId: string }>()
  const { ready, token, username } = useAdminSessionGuard()
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState("")

  useEffect(() => {
    if (!ready || !token || !clientId) return

    adminGetClientDetail(token, clientId)
      .then(setDetail)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load client detail"))
  }, [ready, token, clientId])

  if (!ready || !username) {
    return (
      <main className="min-h-screen bg-background text-foreground flex items-center justify-center">
        <p className="font-mono text-sm text-muted-foreground">Checking admin session...</p>
      </main>
    )
  }

  return (
    <AdminShell
      title="Client detail"
      subtitle="Inspect full profile, call stats, and audit context for a single client."
      username={username}
    >
      {error ? <p className="mb-4 text-sm text-red-600">{error}</p> : null}
      <section className="rounded-2xl border border-foreground/15 bg-background/70 p-6">
        <pre className="overflow-auto rounded-xl border border-foreground/10 bg-muted/30 p-4 text-xs">
          {JSON.stringify(detail, null, 2)}
        </pre>
      </section>
    </AdminShell>
  )
}
