"use client"

import { useEffect, useState } from "react"
import { getCampaigns, pauseCampaign, startCampaign, type Campaign } from "@/lib/api"
import { WorkspaceShell } from "@/components/workspace/workspace-shell"
import { useSessionGuard } from "../_client-helpers"

export default function CampaignsPage() {
  const { ready, user, token } = useSessionGuard()
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [error, setError] = useState("")
  const [pendingId, setPendingId] = useState<string | null>(null)

  useEffect(() => {
    if (!ready || !token) return

    getCampaigns(token)
      .then(setCampaigns)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load campaigns"))
  }, [ready, token])

  async function toggleCampaign(campaign: Campaign) {
    if (!token) return

    try {
      setPendingId(campaign.id)
      if (campaign.state === "pending" || campaign.state === "running") {
        await pauseCampaign(campaign.id, token)
      } else {
        await startCampaign(campaign.id, token)
      }
      const refreshed = await getCampaigns(token)
      setCampaigns(refreshed)
      setError("")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update campaign")
    } finally {
      setPendingId(null)
    }
  }

  if (!ready || !user) {
    return (
      <main className="min-h-screen bg-background text-foreground flex items-center justify-center">
        <p className="font-mono text-sm text-muted-foreground">Checking session...</p>
      </main>
    )
  }

  return (
    <WorkspaceShell
      title="Campaigns"
      subtitle="Track campaign state and quickly start or pause execution windows."
      userLabel={user.name || user.email || "user"}
    >
      <section className="rounded-2xl border border-foreground/15 bg-background/70 p-6">
        <div className="mb-5 flex items-center justify-between gap-3">
          <h2 className="text-2xl font-display">Campaign list</h2>
          <span className="rounded-full border border-foreground/20 px-3 py-1 text-xs font-mono">
            {campaigns.length} total
          </span>
        </div>

        {error ? <p className="mb-4 text-sm text-red-600">{error}</p> : null}

        {campaigns.length === 0 ? (
          <p className="text-muted-foreground">No campaigns found yet.</p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {campaigns.map((campaign) => (
              <article key={campaign.id} className="rounded-xl border border-foreground/10 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-xl font-display">{campaign.name}</h3>
                    <p className="mt-1 text-xs font-mono text-muted-foreground">{campaign.id}</p>
                  </div>
                  <span className="rounded-full border border-foreground/20 px-2 py-1 text-xs font-mono">
                    {campaign.state}
                  </span>
                </div>

                <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-sm text-muted-foreground">
                  <dt>Total</dt>
                  <dd className="font-mono text-foreground">{campaign.stats?.total ?? 0}</dd>
                  <dt>Completed</dt>
                  <dd className="font-mono text-foreground">{campaign.stats?.completed ?? 0}</dd>
                  <dt>Pending</dt>
                  <dd className="font-mono text-foreground">{campaign.stats?.pending ?? 0}</dd>
                  <dt>Failed</dt>
                  <dd className="font-mono text-foreground">{campaign.stats?.failed ?? 0}</dd>
                </dl>

                <button
                  onClick={() => toggleCampaign(campaign)}
                  disabled={pendingId === campaign.id}
                  className="mt-5 h-10 rounded-xl border border-foreground/20 px-4 text-sm hover:bg-foreground hover:text-background disabled:opacity-50"
                >
                  {pendingId === campaign.id
                    ? "Updating..."
                    : campaign.state === "pending" || campaign.state === "running"
                      ? "Pause"
                      : "Start"}
                </button>
              </article>
            ))}
          </div>
        )}
      </section>
    </WorkspaceShell>
  )
}
