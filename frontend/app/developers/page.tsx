import Link from "next/link"
import { ContentShell } from "@/components/workspace/content-shell"

const pages = [
  { title: "Documentation", href: "/developers/documentation", desc: "Project-level implementation docs and usage guide." },
  { title: "API Reference", href: "/developers/api-reference", desc: "Core backend routes grouped by capability." },
  { title: "Auth Flow", href: "/developers/auth-flow", desc: "Signup/login/refresh token flow used by frontend." },
  { title: "Status", href: "/developers/status", desc: "Live backend status and service checks." },
]

export default function DevelopersPage() {
  return (
    <ContentShell
      eyebrow="Developers"
      title="Developer Pages"
      description="Everything needed to integrate Divyashree APIs safely."
      maxWidthClassName="max-w-4xl"
    >
      <div className="grid gap-4 md:grid-cols-2">
        {pages.map((page) => (
          <Link
            key={page.href}
            href={page.href}
            className="rounded-xl border border-foreground/15 bg-background/70 p-5 hover-lift"
          >
            <h2 className="text-xl font-display">{page.title}</h2>
            <p className="mt-2 text-sm text-muted-foreground">{page.desc}</p>
          </Link>
        ))}
      </div>
    </ContentShell>
  )
}
