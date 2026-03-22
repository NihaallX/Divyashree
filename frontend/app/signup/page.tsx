"use client"

import Link from "next/link"
import { FormEvent, useState } from "react"
import { useRouter } from "next/navigation"
import { signup } from "@/lib/api"
import { saveSession } from "@/lib/auth-storage"

export default function SignupPage() {
  const router = useRouter()
  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError("")
    setLoading(true)

    try {
      const data = await signup({ name, email, password })
      saveSession(data.access_token, data.refresh_token, data.user)
      router.push("/dashboard")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed")
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="min-h-screen bg-background text-foreground flex items-center justify-center px-6">
      <div className="w-full max-w-md border border-border p-8 rounded-2xl bg-card">
        <h1 className="text-3xl font-display mb-2">Create account</h1>
        <p className="text-muted-foreground mb-8">Start using Divyashree in minutes.</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm mb-2">Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full h-11 px-3 rounded-lg border border-border bg-background"
              placeholder="Nihal"
            />
          </div>

          <div>
            <label className="block text-sm mb-2">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full h-11 px-3 rounded-lg border border-border bg-background"
              placeholder="you@example.com"
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
            {loading ? "Creating account..." : "Create account"}
          </button>
        </form>

        <p className="text-sm text-muted-foreground mt-6">
          Already have an account? <Link href="/login" className="underline">Sign in</Link>
        </p>
      </div>
    </main>
  )
}
