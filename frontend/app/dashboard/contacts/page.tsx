"use client"

import { useEffect, useState } from "react"
import { getContacts, type Contact } from "@/lib/api"
import { WorkspaceShell } from "@/components/workspace/workspace-shell"
import { useSessionGuard } from "../_client-helpers"

export default function ContactsPage() {
  const { ready, user, token } = useSessionGuard()
  const [contacts, setContacts] = useState<Contact[]>([])
  const [error, setError] = useState("")

  useEffect(() => {
    if (!ready || !token || !user?.id) return

    getContacts(token, user.id)
      .then(setContacts)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load contacts"))
  }, [ready, token, user?.id])

  if (!ready || !user) {
    return (
      <main className="min-h-screen bg-background text-foreground flex items-center justify-center">
        <p className="font-mono text-sm text-muted-foreground">Checking session...</p>
      </main>
    )
  }

  return (
    <WorkspaceShell
      title="Contacts"
      subtitle="Browse imported contacts used for outbound and campaign workflows."
      userLabel={user.name || user.email || "user"}
    >
      <section className="rounded-2xl border border-foreground/15 bg-background/70 p-6">
        <div className="mb-5 flex items-center justify-between gap-3">
          <h2 className="text-2xl font-display">Contact records</h2>
          <span className="rounded-full border border-foreground/20 px-3 py-1 text-xs font-mono">
            {contacts.length} total
          </span>
        </div>

        {error ? <p className="mb-4 text-sm text-red-600">{error}</p> : null}

        {contacts.length === 0 ? (
          <p className="text-muted-foreground">No contacts found. Upload contacts from campaign creation flow.</p>
        ) : (
          <div className="overflow-auto rounded-xl border border-foreground/10">
            <table className="w-full text-sm">
              <thead className="bg-muted/30 text-left">
                <tr>
                  <th className="p-3">Name</th>
                  <th className="p-3">Phone</th>
                  <th className="p-3">Email</th>
                  <th className="p-3">Company</th>
                </tr>
              </thead>
              <tbody>
                {contacts.map((contact) => (
                  <tr key={contact.id} className="border-t border-foreground/10">
                    <td className="p-3">{contact.name}</td>
                    <td className="p-3 font-mono">{contact.phone}</td>
                    <td className="p-3 text-muted-foreground">{contact.email || "-"}</td>
                    <td className="p-3 text-muted-foreground">{contact.company || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </WorkspaceShell>
  )
}
