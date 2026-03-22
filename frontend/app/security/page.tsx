import { ContentShell } from "@/components/workspace/content-shell"

export default function SecurityPage() {
  return (
    <ContentShell
      eyebrow="Legal"
      title="Security"
      description="Implemented security posture for this project codebase."
      maxWidthClassName="max-w-4xl"
    >
      <section className="rounded-xl border border-foreground/15 bg-background/70 p-6">
        <ul className="list-disc pl-5 text-muted-foreground space-y-2">
          <li>JWT-based authentication and refresh token support in backend auth routes.</li>
          <li>CORS controls configured for allowed frontend/API origins.</li>
          <li>Protected route patterns for user-scoped resources.</li>
          <li>Health and logging endpoints for operational monitoring.</li>
        </ul>
      </section>
    </ContentShell>
  )
}
