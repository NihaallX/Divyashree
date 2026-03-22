import Link from "next/link"
import { ContentShell } from "@/components/workspace/content-shell"

export default function DeveloperDocumentationPage() {
  return (
    <ContentShell
      eyebrow="Developers"
      title="Documentation"
      description="Entry point to implementation and runtime resources for the current Divyashree stack."
      maxWidthClassName="max-w-4xl"
    >
      <section className="rounded-xl border border-foreground/15 bg-background/70 p-6">
        <ul className="list-disc space-y-2 pl-5 text-muted-foreground">
          <li>Frontend application routes for auth and dashboard</li>
          <li>Backend FastAPI routes for auth, calls, campaigns, and system health</li>
          <li>Voice gateway service for media callbacks and outbound call flow</li>
          <li>Docker and tunnel scripts for local and deployment workflows</li>
        </ul>
      </section>

      <div className="flex flex-wrap gap-4 text-sm">
        <Link href="/docs" className="underline">Docs summary page</Link>
        <a href="http://localhost:8000/docs" className="underline" target="_blank" rel="noreferrer">Swagger UI</a>
        <Link href="/developers/api-reference" className="underline">API reference</Link>
      </div>
    </ContentShell>
  )
}
