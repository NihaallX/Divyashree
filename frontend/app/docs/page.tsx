"use client"

import { useEffect, useState } from "react"
import { API_BASE_URL } from "@/lib/config"
import { getHealth } from "@/lib/api"
import { ContentShell } from "@/components/workspace/content-shell"

export default function DocsPage() {
  const [connection, setConnection] = useState<"checking" | "online" | "offline">("checking")

  useEffect(() => {
    let active = true

    getHealth()
      .then(() => {
        if (active) setConnection("online")
      })
      .catch(() => {
        if (active) setConnection("offline")
      })

    return () => {
      active = false
    }
  }, [])

  const endpoints = [
    { method: "GET", path: "/health", auth: "No", desc: "Service health and dependency status" },
    { method: "GET", path: "/info", auth: "No", desc: "Backend service and runtime info" },
    { method: "POST", path: "/auth/signup", auth: "No", desc: "Create user and return tokens" },
    { method: "POST", path: "/auth/login", auth: "No", desc: "Authenticate and return tokens" },
    { method: "GET", path: "/auth/verify-token", auth: "Yes", desc: "Validate bearer token" },
    { method: "GET", path: "/agents", auth: "Yes", desc: "List agents for authenticated user" },
    { method: "POST", path: "/calls/outbound", auth: "Yes", desc: "Trigger outbound AI call" },
    { method: "GET", path: "/calls", auth: "Yes", desc: "List calls for authenticated user" },
    { method: "GET", path: "/campaigns", auth: "Yes", desc: "List campaigns for authenticated user" },
    { method: "POST", path: "/campaigns/create", auth: "Yes", desc: "Create campaign from uploaded contacts" },
    { method: "GET", path: "/system/voice-gateway-url", auth: "No", desc: "Get active voice gateway URL" },
  ]

  return (
    <ContentShell
      eyebrow="Docs"
      title="Divyashree API Docs"
      description={`Base URL: ${API_BASE_URL}`}
      maxWidthClassName="max-w-4xl"
    >
      <div className="rounded-xl border border-foreground/15 bg-muted/20 p-4 flex items-center justify-between gap-4">
        <span className="text-sm">Backend connectivity</span>
        <span className="inline-flex items-center gap-2 text-sm font-mono">
          <span
            className={`h-2 w-2 rounded-full ${
              connection === "online"
                ? "bg-green-500"
                : connection === "offline"
                  ? "bg-red-500"
                  : "bg-yellow-500"
            }`}
          />
          {connection}
        </span>
      </div>

      <div className="overflow-hidden rounded-xl border border-foreground/15 bg-background/70">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-left">
            <tr>
              <th className="p-3">Method</th>
              <th className="p-3">Path</th>
              <th className="p-3">Auth</th>
              <th className="p-3">Description</th>
            </tr>
          </thead>
          <tbody>
            {endpoints.map((endpoint) => (
              <tr key={endpoint.path} className="border-t border-foreground/10">
                <td className="p-3 font-mono">{endpoint.method}</td>
                <td className="p-3 font-mono">{endpoint.path}</td>
                <td className="p-3 font-mono">{endpoint.auth}</td>
                <td className="p-3 text-muted-foreground">{endpoint.desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-sm text-muted-foreground">
        For full schema and try-it-out endpoints, open <a className="underline" href="http://localhost:8000/docs" target="_blank" rel="noreferrer">backend Swagger UI</a>.
      </p>
    </ContentShell>
  )
}
