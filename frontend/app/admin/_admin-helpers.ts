"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { adminVerify } from "@/lib/api"
import { getAdminToken, getAdminUsername } from "@/lib/admin-auth-storage"

export function useAdminSessionGuard() {
  const router = useRouter()
  const [ready, setReady] = useState(false)
  const [token, setToken] = useState<string | null>(null)
  const [username, setUsername] = useState<string | null>(null)

  useEffect(() => {
    const nextToken = getAdminToken()
    const nextUsername = getAdminUsername()

    if (!nextToken || !nextUsername) {
      router.replace("/admin/login")
      return
    }

    adminVerify(nextToken)
      .then(() => {
        setToken(nextToken)
        setUsername(nextUsername)
        setReady(true)
      })
      .catch(() => {
        router.replace("/admin/login")
      })
  }, [router])

  return { ready, token, username }
}
