"use client"

import { FormEvent, useState } from "react"
import { useRouter } from "next/navigation"
import { adminLogin } from "@/lib/api"
import { saveAdminSession } from "@/lib/admin-auth-storage"

export default function AdminLoginPage() {
  const router = useRouter()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setLoading(true)
    setError("")

    try {
      const data = await adminLogin({ username, password })
      saveAdminSession(data.token, data.username)
      router.push("/admin")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Admin login failed")
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="min-h-screen bg-background text-foreground flex items-center justify-center px-6">
      <div className="w-full max-w-md border border-border p-8 rounded-2xl bg-card">
        <h1 className="text-3xl font-display mb-2">Admin login</h1>
        <p className="text-muted-foreground mb-8">Sign in to the platform operations console.</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm mb-2">Username</label>
            <input
              type="text"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full h-11 px-3 rounded-lg border border-border bg-background"
              placeholder="admin"
            />
          </div>

          <div>
            <label className="block text-sm mb-2">Password</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full h-11 px-3 rounded-lg border border-border bg-background"
              placeholder="••••••••"
            />
          </div>

          {error ? <p className="text-sm text-red-600">{error}</p> : null}

          <button
            type="submit"
            disabled={loading}
            className="w-full h-11 rounded-lg bg-foreground text-background disabled:opacity-60"
          >
            {loading ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </div>
    </main>
  )
}
