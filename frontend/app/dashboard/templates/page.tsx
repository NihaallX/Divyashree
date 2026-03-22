"use client"

import { FormEvent, useEffect, useState } from "react"
import { getTemplates, previewTemplatePrompt, type TemplateRecord } from "@/lib/api"
import { WorkspaceShell } from "@/components/workspace/workspace-shell"
import { useSessionGuard } from "../_client-helpers"

export default function TemplatesPage() {
  const { ready, user, token } = useSessionGuard()
  const [templates, setTemplates] = useState<TemplateRecord[]>([])
  const [selected, setSelected] = useState<TemplateRecord | null>(null)
  const [sampleInput, setSampleInput] = useState("Hi, I want to book a demo this week")
  const [preview, setPreview] = useState("")
  const [error, setError] = useState("")

  useEffect(() => {
    if (!ready || !token) return
    getTemplates(token)
      .then((data) => {
        setTemplates(data)
        setSelected(data[0] || null)
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load templates"))
  }, [ready, token])

  async function handlePreview(event: FormEvent) {
    event.preventDefault()
    if (!token || !selected?.content) return

    try {
      setError("")
      const result = await previewTemplatePrompt(token, {
        prompt_text: selected.content,
        sample_user_input: sampleInput,
      })
      setPreview(result.preview_response)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Preview failed")
    }
  }

  if (!ready || !user) {
    return (
      <main className="min-h-screen bg-background text-foreground flex items-center justify-center">
        <p className="font-mono text-sm text-muted-foreground">Checking session...</p>
      </main>
    )
  }

  return (
    <WorkspaceShell
      title="Templates"
      subtitle="Browse starter prompts and test output preview against sample input."
      userLabel={user.name || user.email || "user"}
    >
      <section className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="rounded-2xl border border-foreground/15 bg-background/70 p-6">
          <h2 className="text-2xl font-display">Template library</h2>
          <div className="mt-4 space-y-2">
            {templates.map((template) => (
              <button
                key={template.id}
                onClick={() => setSelected(template)}
                className={`w-full rounded-xl border px-3 py-2 text-left transition-colors ${
                  selected?.id === template.id
                    ? "border-foreground/50 bg-foreground/5"
                    : "border-foreground/10 hover:border-foreground/30"
                }`}
              >
                <p className="font-medium">{template.name}</p>
                <p className="text-xs text-muted-foreground">{template.category || "custom"}</p>
              </button>
            ))}
            {templates.length === 0 ? <p className="text-sm text-muted-foreground">No templates found.</p> : null}
          </div>
        </div>

        <div className="rounded-2xl border border-foreground/15 bg-background/70 p-6">
          <h2 className="text-2xl font-display">Prompt preview</h2>
          {selected ? (
            <form className="mt-4 space-y-4" onSubmit={handlePreview}>
              <div>
                <p className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground">Prompt</p>
                <pre className="mt-2 max-h-40 overflow-auto rounded-xl border border-foreground/10 bg-muted/30 p-3 text-xs">
                  {selected.content || "No content"}
                </pre>
              </div>
              <div>
                <label className="block text-sm mb-2">Sample user input</label>
                <textarea
                  className="w-full min-h-24 rounded-xl border border-foreground/20 bg-background/80 p-3 text-sm"
                  value={sampleInput}
                  onChange={(e) => setSampleInput(e.target.value)}
                />
              </div>
              <button className="h-10 rounded-xl border border-foreground/20 px-4 text-sm hover:bg-foreground hover:text-background transition-colors">
                Run preview
              </button>
            </form>
          ) : (
            <p className="mt-4 text-muted-foreground">Select a template to preview it.</p>
          )}

          {error ? <p className="mt-4 text-sm text-red-600">{error}</p> : null}
          {preview ? (
            <div className="mt-4 rounded-xl border border-foreground/10 p-4">
              <p className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground mb-2">Preview response</p>
              <p className="text-sm leading-relaxed">{preview}</p>
            </div>
          ) : null}
        </div>
      </section>
    </WorkspaceShell>
  )
}
