"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import { getAgents, getCampaigns, getContacts, getHealth } from "@/lib/api"
import { WorkspaceShell } from "@/components/workspace/workspace-shell"
import { useSessionGuard } from "./_client-helpers"

type HealthData = Record<string, unknown>

export default function DashboardPage() {
  const { ready, user, token } = useSessionGuard()
  const [health, setHealth] = useState<HealthData | null>(null)
  const [counts, setCounts] = useState({ agents: 0, contacts: 0, campaigns: 0 })
  const [error, setError] = useState("")

  useEffect(() => {
    if (!ready || !token || !user?.id) {
      return
    }

    Promise.all([
      getHealth(),
      getAgents({ userId: user.id, token }),
      getContacts(token, user.id),
      getCampaigns(token),
    ])
      .then(([healthData, agents, contacts, campaigns]) => {
        setHealth(healthData)
        setCounts({
          agents: agents.length,
          contacts: contacts.length,
          campaigns: campaigns.length,
        })
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Dashboard load failed"))
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
      title="Dashboard"
      subtitle="Monitor backend health, entity counts, and jump into operational surfaces."
      userLabel={user.name || user.email || "user"}
    >
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        {[
          { label: "Agents", value: counts.agents, href: "/dashboard/agents" },
          { label: "Contacts", value: counts.contacts, href: "/dashboard/contacts" },
          { label: "Campaigns", value: counts.campaigns, href: "/dashboard/campaigns" },
          { label: "Analytics", value: "insights", href: "/dashboard/analytics" },
          { label: "API Health", value: health ? "online" : "loading", href: "/developers/status" },
        ].map((item) => (
          <Link
            key={item.label}
            href={item.href}
            className="group rounded-2xl border border-foreground/15 bg-background/70 p-5 hover-lift"
          >
            <p className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground">{item.label}</p>
            <p className="mt-3 text-4xl font-display leading-none">{item.value}</p>
            <p className="mt-3 text-sm text-muted-foreground group-hover:text-foreground transition-colors">Open page</p>
          </Link>
        ))}
      </section>

      <section className="mt-8 grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-2xl border border-foreground/15 bg-background/70 p-6">
          <h2 className="text-2xl font-display">Backend snapshot</h2>
          <p className="mt-2 text-sm text-muted-foreground">Live output from health endpoint.</p>
          {health ? (
            <pre className="mt-5 overflow-auto rounded-xl border border-foreground/10 bg-muted/30 p-4 text-xs">
              {JSON.stringify(health, null, 2)}
            </pre>
          ) : (
            <p className="mt-4 text-sm text-muted-foreground">Loading health data...</p>
          )}
          {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
        </div>

        <div className="rounded-2xl border border-foreground/15 bg-background/70 p-6">
          <h2 className="text-2xl font-display">Quick actions</h2>
          <ul className="mt-4 space-y-3 text-sm text-muted-foreground">
            <li><Link href="/dashboard/agents" className="underline">Manage your AI agents</Link></li>
            <li><Link href="/dashboard/contacts" className="underline">Review contact records</Link></li>
            <li><Link href="/dashboard/campaigns" className="underline">Track campaign states</Link></li>
            <li><Link href="/dashboard/analytics" className="underline">Open analytics dashboard</Link></li>
            <li><Link href="/docs" className="underline">API documentation overview</Link></li>
            <li><a href="http://localhost:8000/docs" className="underline" target="_blank" rel="noreferrer">Backend Swagger UI</a></li>
          </ul>
        </div>
      </section>
    </WorkspaceShell>
  )
}
