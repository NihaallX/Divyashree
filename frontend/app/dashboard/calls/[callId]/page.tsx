"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"
import { getCallAnalysis, getCallById, getCallTranscripts, type CallRecord } from "@/lib/api"
import { API_BASE_URL } from "@/lib/config"
import { WorkspaceShell } from "@/components/workspace/workspace-shell"
import { useSessionGuard } from "../../_client-helpers"

export default function CallDetailPage() {
  const { callId } = useParams<{ callId: string }>()
  const { ready, user, token } = useSessionGuard()
  const [call, setCall] = useState<CallRecord | null>(null)
  const [analysis, setAnalysis] = useState<Record<string, unknown> | null>(null)
  const [transcripts, setTranscripts] = useState<Array<Record<string, unknown>>>([])
  const [error, setError] = useState("")

  useEffect(() => {
    if (!ready || !token || !callId) return

    Promise.all([getCallById(callId, token), getCallAnalysis(callId, token), getCallTranscripts(callId, token)])
      .then(([callData, analysisData, transcriptData]) => {
        setCall(callData)
        setAnalysis(analysisData)
        setTranscripts(transcriptData)
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load call details"))
  }, [ready, token, callId])

  if (!ready || !user) {
    return (
      <main className="min-h-screen bg-background text-foreground flex items-center justify-center">
        <p className="font-mono text-sm text-muted-foreground">Checking session...</p>
      </main>
    )
  }

  return (
    <WorkspaceShell
      title="Call details"
      subtitle="Inspect call metadata, analysis, transcript, and recording."
      userLabel={user.name || user.email || "user"}
    >
      {error ? <p className="mb-4 text-sm text-red-600">{error}</p> : null}

      <section className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-2xl border border-foreground/15 bg-background/70 p-6">
          <h2 className="text-2xl font-display">Metadata</h2>
          <pre className="mt-4 overflow-auto rounded-xl border border-foreground/10 bg-muted/30 p-4 text-xs">
            {JSON.stringify(call, null, 2)}
          </pre>
        </div>

        <div className="rounded-2xl border border-foreground/15 bg-background/70 p-6">
          <h2 className="text-2xl font-display">Analysis</h2>
          <pre className="mt-4 overflow-auto rounded-xl border border-foreground/10 bg-muted/30 p-4 text-xs">
            {JSON.stringify(analysis, null, 2)}
          </pre>
          <div className="mt-4">
            <audio
              controls
              className="w-full"
              src={`${API_BASE_URL}/calls/${callId}/recording/stream`}
            >
              Your browser does not support audio playback.
            </audio>
          </div>
        </div>
      </section>

      <section className="mt-6 rounded-2xl border border-foreground/15 bg-background/70 p-6">
        <h2 className="text-2xl font-display">Transcripts</h2>
        {transcripts.length === 0 ? (
          <p className="mt-3 text-muted-foreground">No transcript entries yet.</p>
        ) : (
          <div className="mt-4 space-y-3">
            {transcripts.map((line, idx) => (
              <div key={idx} className="rounded-xl border border-foreground/10 p-3 text-sm">
                <p className="text-xs font-mono text-muted-foreground mb-1">{String(line.role || "speaker")}</p>
                <p>{String(line.content || line.text || "")}</p>
              </div>
            ))}
          </div>
        )}
      </section>
    </WorkspaceShell>
  )
}
