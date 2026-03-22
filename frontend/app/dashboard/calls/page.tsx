"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import { getCalls, type CallRecord } from "@/lib/api"
import { WorkspaceShell } from "@/components/workspace/workspace-shell"
import { useSessionGuard } from "../_client-helpers"

export default function CallsPage() {
  const { ready, user, token } = useSessionGuard()
  const [calls, setCalls] = useState<CallRecord[]>([])
  const [error, setError] = useState("")

  useEffect(() => {
    if (!ready || !token) return

    getCalls(token, user?.id)
      .then(setCalls)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load calls"))
  }, [ready, token, user?.id])

  if (!ready || !user) {
    return (
      <main className="min-h-screen bg-background text-foreground flex items-center justify-center">
        <p className="font-mono text-sm text-muted-foreground">Checking session...</p>
      </main>
    )
  }

  return (
    <WorkspaceShell
      title="Calls"
      subtitle="Inspect call records and drill into transcripts and analysis."
      userLabel={user.name || user.email || "user"}
    >
      <section className="rounded-2xl border border-foreground/15 bg-background/70 p-6">
        <div className="mb-5 flex items-center justify-between gap-3">
          <h2 className="text-2xl font-display">Recent calls</h2>
          <span className="rounded-full border border-foreground/20 px-3 py-1 text-xs font-mono">
            {calls.length} total
          </span>
        </div>

        {error ? <p className="mb-4 text-sm text-red-600">{error}</p> : null}

        {calls.length === 0 ? (
          <p className="text-muted-foreground">No calls yet.</p>
        ) : (
          <div className="overflow-auto rounded-xl border border-foreground/10">
            <table className="w-full text-sm">
              <thead className="bg-muted/30 text-left">
                <tr>
                  <th className="p-3">Call ID</th>
                  <th className="p-3">To</th>
                  <th className="p-3">Status</th>
                  <th className="p-3">Created</th>
                  <th className="p-3">Open</th>
                </tr>
              </thead>
              <tbody>
                {calls.map((call) => (
                  <tr key={call.id} className="border-t border-foreground/10">
                    <td className="p-3 font-mono">{call.id}</td>
                    <td className="p-3 font-mono">{String(call.to_number || "-")}</td>
                    <td className="p-3">{String(call.status || "-")}</td>
                    <td className="p-3 text-muted-foreground">{String(call.created_at || "-")}</td>
                    <td className="p-3">
                      <Link href={`/dashboard/calls/${call.id}`} className="underline">
                        View details
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </WorkspaceShell>
  )
}
