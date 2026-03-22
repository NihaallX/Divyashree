"use client"

import { useEffect, useState } from "react"
import { getAnalytics, getDashboardStats, type AnalyticsResponse, type DashboardStats } from "@/lib/api"
import { WorkspaceShell } from "@/components/workspace/workspace-shell"
import { useSessionGuard } from "../_client-helpers"

const dayOptions = [7, 14, 30]

const emptyStats: DashboardStats = {
  totalCalls: 0,
  interestedCalls: 0,
  notInterestedCalls: 0,
  avgConfidence: 0,
  todayCalls: 0,
}

const emptyAnalytics: AnalyticsResponse = {
  dailyCalls: [],
  outcomeDistribution: {
    interested: 0,
    notInterested: 0,
    noAnswer: 0,
    other: 0,
  },
  hourlyBreakdown: [],
  averageDuration: 0,
  successRate: 0,
  totalCalls: 0,
  completedCalls: 0,
  dateRange: {
    start: "",
    end: "",
    days: 14,
  },
}

export default function DashboardAnalyticsPage() {
  const { ready, user, token } = useSessionGuard()
  const [days, setDays] = useState(14)
  const [stats, setStats] = useState<DashboardStats>(emptyStats)
  const [analytics, setAnalytics] = useState<AnalyticsResponse>(emptyAnalytics)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    if (!ready || !token) {
      return
    }

    setLoading(true)
    setError("")

    Promise.all([getDashboardStats(token), getAnalytics(token, days)])
      .then(([statsData, analyticsData]) => {
        setStats(statsData)
        setAnalytics(analyticsData)
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load analytics")
      })
      .finally(() => setLoading(false))
  }, [ready, token, days])

  if (!ready || !user) {
    return (
      <main className="min-h-screen bg-background text-foreground flex items-center justify-center">
        <p className="font-mono text-sm text-muted-foreground">Checking session...</p>
      </main>
    )
  }

  return (
    <WorkspaceShell
      title="Analytics"
      subtitle="Track call outcomes, confidence, volume, and day-level trends."
      userLabel={user.name || user.email || "user"}
    >
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <MetricCard label="Total calls" value={stats.totalCalls} />
        <MetricCard label="Today" value={stats.todayCalls} />
        <MetricCard label="Interested" value={stats.interestedCalls} />
        <MetricCard label="Not interested" value={stats.notInterestedCalls} />
        <MetricCard label="Confidence" value={`${Math.round(stats.avgConfidence * 100)}%`} />
      </section>

      <section className="mt-8 rounded-2xl border border-foreground/15 bg-background/70 p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-2xl font-display">Window</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Review analytics for the last 7, 14, or 30 days.
            </p>
          </div>
          <div className="flex items-center gap-2 rounded-full border border-foreground/20 p-1">
            {dayOptions.map((option) => {
              const active = option === days
              return (
                <button
                  key={option}
                  onClick={() => setDays(option)}
                  className={`rounded-full px-3 py-1.5 text-sm transition-colors ${
                    active
                      ? "bg-foreground text-background"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {option}d
                </button>
              )
            })}
          </div>
        </div>

        {error ? <p className="mt-4 text-sm text-red-600">{error}</p> : null}
        {loading ? <p className="mt-4 text-sm text-muted-foreground">Loading analytics...</p> : null}

        {!loading && !error ? (
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            <MetricCard label="Success rate" value={`${analytics.successRate}%`} compact />
            <MetricCard label="Avg duration" value={`${analytics.averageDuration}s`} compact />
            <MetricCard label="Completed" value={analytics.completedCalls} compact />
          </div>
        ) : null}
      </section>

      <section className="mt-6 grid gap-6 lg:grid-cols-2">
        <div className="rounded-2xl border border-foreground/15 bg-background/70 p-6">
          <h3 className="text-xl font-display">Outcome breakdown</h3>
          <div className="mt-4 space-y-3 text-sm">
            <OutcomeRow label="Interested" value={analytics.outcomeDistribution.interested} />
            <OutcomeRow label="Not interested" value={analytics.outcomeDistribution.notInterested} />
            <OutcomeRow label="No answer / busy" value={analytics.outcomeDistribution.noAnswer} />
            <OutcomeRow label="Other" value={analytics.outcomeDistribution.other} />
          </div>
        </div>

        <div className="rounded-2xl border border-foreground/15 bg-background/70 p-6">
          <h3 className="text-xl font-display">Daily call trend</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            {analytics.dateRange.start && analytics.dateRange.end
              ? `${analytics.dateRange.start} to ${analytics.dateRange.end}`
              : "No date range available"}
          </p>

          <div className="mt-4 max-h-72 overflow-auto rounded-xl border border-foreground/10">
            <table className="w-full text-left text-sm">
              <thead className="sticky top-0 bg-background/95">
                <tr className="border-b border-foreground/10">
                  <th className="px-3 py-2 font-medium">Date</th>
                  <th className="px-3 py-2 font-medium">Total</th>
                  <th className="px-3 py-2 font-medium">Completed</th>
                  <th className="px-3 py-2 font-medium">Failed</th>
                </tr>
              </thead>
              <tbody>
                {analytics.dailyCalls.map((row) => (
                  <tr key={row.date} className="border-b border-foreground/5">
                    <td className="px-3 py-2">{row.date}</td>
                    <td className="px-3 py-2">{row.count}</td>
                    <td className="px-3 py-2">{row.completed}</td>
                    <td className="px-3 py-2">{row.failed}</td>
                  </tr>
                ))}
                {analytics.dailyCalls.length === 0 ? (
                  <tr>
                    <td className="px-3 py-6 text-muted-foreground" colSpan={4}>
                      No calls in this date range.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </WorkspaceShell>
  )
}

function MetricCard({ label, value, compact = false }: { label: string; value: number | string; compact?: boolean }) {
  return (
    <div className={`rounded-2xl border border-foreground/15 bg-background/70 ${compact ? "p-4" : "p-5"}`}>
      <p className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground">{label}</p>
      <p className={`mt-3 ${compact ? "text-2xl" : "text-4xl"} font-display leading-none`}>{value}</p>
    </div>
  )
}

function OutcomeRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between rounded-xl border border-foreground/10 px-3 py-2">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  )
}
