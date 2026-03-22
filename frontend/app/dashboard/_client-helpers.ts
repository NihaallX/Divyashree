"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { getAccessToken, getUser } from "@/lib/auth-storage"

type SessionUser = {
  id?: string
  email?: string
  name?: string
}

export function useSessionGuard() {
  const router = useRouter()
  const [ready, setReady] = useState(false)
  const [user, setUser] = useState<SessionUser | null>(null)
  const [token, setToken] = useState<string | null>(null)

  useEffect(() => {
    const nextUser = getUser<SessionUser>()
    const nextToken = getAccessToken()

    if (!nextUser || !nextToken) {
      router.replace("/login")
      return
    }

    setUser(nextUser)
    setToken(nextToken)
    setReady(true)
  }, [router])

  return { ready, user, token }
}
