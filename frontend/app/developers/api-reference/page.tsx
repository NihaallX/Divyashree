import { ContentShell } from "@/components/workspace/content-shell"

const routes = [
  { group: "System", items: ["GET /health", "GET /info", "GET /api-credits"] },
  { group: "Auth", items: ["POST /auth/signup", "POST /auth/login", "POST /auth/refresh", "GET /auth/verify-token"] },
  { group: "Agents", items: ["GET /agents", "POST /agents", "PUT /agents/{agent_id}"] },
  { group: "Calls", items: ["POST /calls/outbound", "GET /calls", "GET /calls/{call_id}"] },
  { group: "Campaigns", items: ["GET /campaigns", "POST /campaigns/create", "POST /campaigns/{id}/start", "POST /campaigns/{id}/pause"] },
]

export default function ApiReferencePage() {
  return (
    <ContentShell
      eyebrow="Developers"
      title="API Reference"
      description="Primary routes currently used by frontend and core voice workflows."
      maxWidthClassName="max-w-4xl"
    >
      <div className="space-y-4">
        {routes.map((route) => (
          <section key={route.group} className="rounded-xl border border-foreground/15 bg-background/70 p-5">
            <h2 className="text-xl font-display">{route.group}</h2>
            <ul className="mt-3 space-y-1 font-mono text-sm text-muted-foreground">
              {route.items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </ContentShell>
  )
}
