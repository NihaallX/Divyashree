const ADMIN_TOKEN_KEY = "admin_access_token"
const ADMIN_USERNAME_KEY = "admin_username"

export function saveAdminSession(token: string, username: string) {
  if (typeof window === "undefined") return
  localStorage.setItem(ADMIN_TOKEN_KEY, token)
  localStorage.setItem(ADMIN_USERNAME_KEY, username)
}

export function getAdminToken(): string | null {
  if (typeof window === "undefined") return null
  return localStorage.getItem(ADMIN_TOKEN_KEY)
}

export function getAdminUsername(): string | null {
  if (typeof window === "undefined") return null
  return localStorage.getItem(ADMIN_USERNAME_KEY)
}

export function clearAdminSession() {
  if (typeof window === "undefined") return
  localStorage.removeItem(ADMIN_TOKEN_KEY)
  localStorage.removeItem(ADMIN_USERNAME_KEY)
}
