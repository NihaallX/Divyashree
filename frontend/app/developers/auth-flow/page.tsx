import { ContentShell } from "@/components/workspace/content-shell"

export default function AuthFlowPage() {
  return (
    <ContentShell
      eyebrow="Developers"
      title="Auth Flow"
      description="Token-based authentication with access and refresh tokens."
      maxWidthClassName="max-w-4xl"
    >
      <section className="rounded-xl border border-foreground/15 bg-background/70 p-6">
        <ol className="list-decimal space-y-3 pl-5 text-muted-foreground">
          <li>Create account with <span className="font-mono">POST /auth/signup</span> or sign in using <span className="font-mono">POST /auth/login</span>.</li>
          <li>Store returned <span className="font-mono">access_token</span> and <span className="font-mono">refresh_token</span>.</li>
          <li>Use bearer authorization for protected endpoints such as agents, calls, and campaigns.</li>
          <li>Refresh session using <span className="font-mono">POST /auth/refresh</span> when access token expires.</li>
          <li>Optionally validate access token with <span className="font-mono">GET /auth/verify-token</span>.</li>
        </ol>
      </section>

      <div className="rounded-xl border border-foreground/15 bg-muted/20 p-5">
        <p className="text-sm text-muted-foreground">
          Frontend implementation currently uses helper modules under <span className="font-mono">frontend/lib/api.ts</span> and <span className="font-mono">frontend/lib/auth-storage.ts</span>.
        </p>
      </div>
    </ContentShell>
  )
}
