"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import { adminGetAnalytics, adminGetClients, type AdminAnalytics } from "@/lib/api"
import { AdminShell } from "@/components/workspace/admin-shell"
import { useAdminSessionGuard } from "./_admin-helpers"

const emptyAnalytics: AdminAnalytics = {
  total_clients: 0,
  active_clients: 0,
  total_agents: 0,
  total_calls: 0,
  calls_today: 0,
  success_rate: 0,
  avg_call_duration: 0,
  peak_hours: [],
  top_clients: [],
}

export default function AdminOverviewPage() {
  const { ready, token, username } = useAdminSessionGuard()
  const [analytics, setAnalytics] = useState<AdminAnalytics>(emptyAnalytics)
  const [clientCount, setClientCount] = useState(0)
  const [error, setError] = useState("")

  useEffect(() => {
    if (!ready || !token) return

    Promise.all([adminGetAnalytics(token), adminGetClients(token)])
      .then(([analyticsData, clients]) => {
        setAnalytics(analyticsData)
        setClientCount(clients.length)
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load admin dashboard"))
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
      title="Operations dashboard"
      subtitle="Monitor all clients, agents, call volume, and platform reliability from one console."
      username={username}
    >
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        {[
          { label: "Clients", value: clientCount, href: "/admin/clients" },
          { label: "Active clients", value: analytics.active_clients, href: "/admin/clients" },
          { label: "Agents", value: analytics.total_agents, href: "/admin/agents" },
          { label: "Calls", value: analytics.total_calls, href: "/admin/calls" },
          { label: "Calls today", value: analytics.calls_today, href: "/admin/calls" },
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
          <h2 className="text-2xl font-display">Analytics snapshot</h2>
          <p className="mt-2 text-sm text-muted-foreground">Live system-level stats from admin analytics endpoint.</p>
          <pre className="mt-5 overflow-auto rounded-xl border border-foreground/10 bg-muted/30 p-4 text-xs">
            {JSON.stringify(analytics, null, 2)}
          </pre>
          {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
        </div>

        <div className="rounded-2xl border border-foreground/15 bg-background/70 p-6">
          <h2 className="text-2xl font-display">Quick actions</h2>
          <ul className="mt-4 space-y-3 text-sm text-muted-foreground">
            <li><Link href="/admin/clients" className="underline">Inspect client accounts</Link></li>
            <li><Link href="/admin/calls" className="underline">Review latest calls</Link></li>
            <li><Link href="/admin/audit" className="underline">Check audit trail</Link></li>
            <li><Link href="/admin/system-logs" className="underline">View backend and gateway logs</Link></li>
          </ul>
        </div>
      </section>
    </AdminShell>
  )
}
