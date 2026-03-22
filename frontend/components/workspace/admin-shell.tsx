"use client"

import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { clearAdminSession } from "@/lib/admin-auth-storage"

type AdminShellProps = {
  title: string
  subtitle: string
  username: string
  children: React.ReactNode
}

const navItems = [
  { href: "/admin", label: "Overview" },
  { href: "/admin/clients", label: "Clients" },
  { href: "/admin/agents", label: "Agents" },
  { href: "/admin/calls", label: "Calls" },
  { href: "/admin/audit", label: "Audit" },
  { href: "/admin/system-logs", label: "System Logs" },
]

export function AdminShell({ title, subtitle, username, children }: AdminShellProps) {
  const pathname = usePathname()
  const router = useRouter()

  function handleLogout() {
    clearAdminSession()
    router.push("/admin/login")
  }

  return (
    <main className="relative min-h-screen overflow-x-hidden noise-overlay bg-background text-foreground">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -left-16 top-[-6rem] h-72 w-72 rounded-full bg-foreground/5 blur-3xl" />
        <div className="absolute right-0 top-20 h-64 w-64 rounded-full bg-foreground/5 blur-3xl" />
      </div>

      <div className="relative z-10 mx-auto max-w-[1500px] px-6 py-8 lg:px-12 lg:py-10">
        <header className="mb-8 border-b border-foreground/10 pb-6">
          <div className="mb-5 flex flex-wrap items-center justify-between gap-4">
            <div>
              <span className="inline-flex items-center gap-3 text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground">
                <span className="h-px w-7 bg-foreground/30" />
                Divyashree Admin
              </span>
              <h1 className="mt-3 text-4xl font-display tracking-tight lg:text-5xl">{title}</h1>
              <p className="mt-2 text-muted-foreground">{subtitle}</p>
            </div>
            <div className="flex items-center gap-3">
              <span className="rounded-full border border-foreground/20 px-3 py-1 text-xs font-mono text-muted-foreground">
                {username}
              </span>
              <button
                onClick={handleLogout}
                className="h-10 rounded-xl border border-foreground/20 px-4 text-sm hover:bg-foreground hover:text-background transition-colors"
              >
                Logout
              </button>
            </div>
          </div>

          <nav className="flex flex-wrap gap-2">
            {navItems.map((item) => {
              const active = pathname === item.href
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`rounded-full px-4 py-2 text-sm transition-colors ${
                    active
                      ? "bg-foreground text-background"
                      : "border border-foreground/20 text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {item.label}
                </Link>
              )
            })}
          </nav>
        </header>

        {children}
      </div>
    </main>
  )
}
