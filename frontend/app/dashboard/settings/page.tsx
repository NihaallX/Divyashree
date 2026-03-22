"use client"

import { useEffect, useState } from "react"
import { getCurrentUser, type UserProfile } from "@/lib/api"
import { WorkspaceShell } from "@/components/workspace/workspace-shell"
import { useSessionGuard } from "../_client-helpers"

export default function SettingsPage() {
  const { ready, user, token } = useSessionGuard()
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [error, setError] = useState("")

  useEffect(() => {
    if (!ready || !token) return

    getCurrentUser(token)
      .then(setProfile)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load profile"))
  }, [ready, token])

  if (!ready || !user) {
    return (
      <main className="min-h-screen bg-background text-foreground flex items-center justify-center">
        <p className="font-mono text-sm text-muted-foreground">Checking session...</p>
      </main>
    )
  }

  return (
    <WorkspaceShell
      title="Settings"
      subtitle="View account profile and integration-ready user metadata."
      userLabel={user.name || user.email || "user"}
    >
      <section className="rounded-2xl border border-foreground/15 bg-background/70 p-6">
        <h2 className="text-2xl font-display">Account profile</h2>
        {error ? <p className="mt-4 text-sm text-red-600">{error}</p> : null}
        <pre className="mt-4 overflow-auto rounded-xl border border-foreground/10 bg-muted/30 p-4 text-xs">
          {JSON.stringify(profile, null, 2)}
        </pre>
      </section>
    </WorkspaceShell>
  )
}
