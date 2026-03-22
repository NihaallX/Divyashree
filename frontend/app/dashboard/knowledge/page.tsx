"use client"

import { useEffect, useState } from "react"
import { getAgentKnowledge, getAgents, type Agent, type KnowledgeRecord } from "@/lib/api"
import { WorkspaceShell } from "@/components/workspace/workspace-shell"
import { useSessionGuard } from "../_client-helpers"

export default function KnowledgePage() {
  const { ready, user, token } = useSessionGuard()
  const [agents, setAgents] = useState<Agent[]>([])
  const [selectedAgentId, setSelectedAgentId] = useState("")
  const [knowledge, setKnowledge] = useState<KnowledgeRecord[]>([])
  const [error, setError] = useState("")

  useEffect(() => {
    if (!ready || !token || !user?.id) return

    getAgents({ token, userId: user.id })
      .then((list) => {
        setAgents(list)
        if (list[0]?.id) setSelectedAgentId(list[0].id)
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load agents"))
  }, [ready, token, user?.id])

  useEffect(() => {
    if (!token || !selectedAgentId) return

    getAgentKnowledge(selectedAgentId, token)
      .then(setKnowledge)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load knowledge"))
  }, [token, selectedAgentId])

  if (!ready || !user) {
    return (
      <main className="min-h-screen bg-background text-foreground flex items-center justify-center">
        <p className="font-mono text-sm text-muted-foreground">Checking session...</p>
      </main>
    )
  }

  return (
    <WorkspaceShell
      title="Knowledge"
      subtitle="Review stored knowledge sources attached to each AI agent."
      userLabel={user.name || user.email || "user"}
    >
      <section className="rounded-2xl border border-foreground/15 bg-background/70 p-6">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-2xl font-display">Agent knowledge base</h2>
          <select
            className="h-10 rounded-xl border border-foreground/20 bg-background px-3 text-sm"
            value={selectedAgentId}
            onChange={(e) => setSelectedAgentId(e.target.value)}
          >
            {agents.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.name}
              </option>
            ))}
          </select>
        </div>

        {error ? <p className="mb-4 text-sm text-red-600">{error}</p> : null}

        {knowledge.length === 0 ? (
          <p className="text-muted-foreground">No knowledge entries found for this agent.</p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {knowledge.map((item) => (
              <article key={item.id} className="rounded-xl border border-foreground/10 p-4">
                <h3 className="text-lg font-medium">{item.title}</h3>
                <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-sm text-muted-foreground">
                  <dt>Type</dt>
                  <dd>{item.file_type || "text"}</dd>
                  <dt>Source file</dt>
                  <dd className="truncate">{item.source_file || "-"}</dd>
                  <dt>Source URL</dt>
                  <dd className="truncate">{item.source_url || "-"}</dd>
                </dl>
              </article>
            ))}
          </div>
        )}
      </section>
    </WorkspaceShell>
  )
}
