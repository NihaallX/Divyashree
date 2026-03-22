"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import { adminGetClients, type AdminClientCard } from "@/lib/api"
import { AdminShell } from "@/components/workspace/admin-shell"
import { useAdminSessionGuard } from "../_admin-helpers"

export default function AdminClientsPage() {
  const { ready, token, username } = useAdminSessionGuard()
  const [clients, setClients] = useState<AdminClientCard[]>([])
  const [error, setError] = useState("")

  useEffect(() => {
    if (!ready || !token) return

    adminGetClients(token)
      .then(setClients)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load clients"))
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
      title="Clients"
      subtitle="Browse all client accounts, call volumes, and activity indicators."
      username={username}
    >
      <section className="rounded-2xl border border-foreground/15 bg-background/70 p-6">
        <div className="mb-5 flex items-center justify-between gap-3">
          <h2 className="text-2xl font-display">Client list</h2>
          <span className="rounded-full border border-foreground/20 px-3 py-1 text-xs font-mono">
            {clients.length} total
          </span>
        </div>

        {error ? <p className="mb-4 text-sm text-red-600">{error}</p> : null}

        {clients.length === 0 ? (
          <p className="text-muted-foreground">No clients found.</p>
        ) : (
          <div className="overflow-auto rounded-xl border border-foreground/10">
            <table className="w-full text-sm">
              <thead className="bg-muted/30 text-left">
                <tr>
                  <th className="p-3">Client</th>
                  <th className="p-3">Company</th>
                  <th className="p-3">Agents</th>
                  <th className="p-3">Calls</th>
                  <th className="p-3">Active</th>
                  <th className="p-3">Open</th>
                </tr>
              </thead>
              <tbody>
                {clients.map((client) => (
                  <tr key={client.id} className="border-t border-foreground/10">
                    <td className="p-3">
                      <p className="font-medium">{client.name}</p>
                      <p className="text-xs text-muted-foreground">{client.email}</p>
                    </td>
                    <td className="p-3 text-muted-foreground">{client.company || "-"}</td>
                    <td className="p-3 font-mono">{client.agent_count}</td>
                    <td className="p-3 font-mono">{client.total_calls}</td>
                    <td className="p-3 font-mono">{client.active_calls}</td>
                    <td className="p-3">
                      <Link href={`/admin/clients/${client.id}`} className="underline">Details</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </AdminShell>
  )
}
