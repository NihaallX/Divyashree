"use client"

import { useEffect, useState } from "react"
import { getAgents, type Agent } from "@/lib/api"
import { WorkspaceShell } from "@/components/workspace/workspace-shell"
import { useSessionGuard } from "../_client-helpers"

export default function AgentsPage() {
  const { ready, user, token } = useSessionGuard()
  const [agents, setAgents] = useState<Agent[]>([])
  const [error, setError] = useState("")

  useEffect(() => {
    if (!ready || !token || !user?.id) return

    getAgents({ token, userId: user.id })
      .then(setAgents)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load agents"))
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
      title="Agents"
      subtitle="Review available AI agents, model settings, and active status."
      userLabel={user.name || user.email || "user"}
    >
      <section className="rounded-2xl border border-foreground/15 bg-background/70 p-6">
        <div className="mb-5 flex items-center justify-between gap-3">
          <h2 className="text-2xl font-display">Agent list</h2>
          <span className="rounded-full border border-foreground/20 px-3 py-1 text-xs font-mono">
            {agents.length} total
          </span>
        </div>

        {error ? <p className="mb-4 text-sm text-red-600">{error}</p> : null}

        {agents.length === 0 ? (
          <p className="text-muted-foreground">No agents found for this account yet.</p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {agents.map((agent) => (
              <article key={agent.id} className="rounded-xl border border-foreground/10 p-4">
                <div className="flex items-start justify-between gap-4">
                  <h3 className="text-xl font-display">{agent.name}</h3>
                  <span
                    className={`rounded-full px-2 py-1 text-xs font-mono ${
                      agent.is_active
                        ? "bg-green-500/15 text-green-700"
                        : "bg-foreground/10 text-muted-foreground"
                    }`}
                  >
                    {agent.is_active ? "active" : "inactive"}
                  </span>
                </div>
                <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-sm text-muted-foreground">
                  <dt>Model</dt>
                  <dd className="font-mono text-foreground">{agent.llm_model || "-"}</dd>
                  <dt>Temperature</dt>
                  <dd className="font-mono text-foreground">{agent.temperature ?? "-"}</dd>
                  <dt>Max tokens</dt>
                  <dd className="font-mono text-foreground">{agent.max_tokens ?? "-"}</dd>
                </dl>
              </article>
            ))}
          </div>
        )}
      </section>
    </WorkspaceShell>
  )
}
