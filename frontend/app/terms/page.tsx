import { ContentShell } from "@/components/workspace/content-shell"

export default function TermsPage() {
  return (
    <ContentShell
      eyebrow="Legal"
      title="Terms"
      description="High-level usage terms for the Divyashree project environment."
      maxWidthClassName="max-w-4xl"
    >
      <section className="rounded-xl border border-foreground/15 bg-background/70 p-6">
        <ul className="list-disc pl-5 text-muted-foreground space-y-2">
          <li>Use API endpoints only with valid credentials and authorized project context.</li>
          <li>Respect telephony and regional compliance requirements for outbound calling.</li>
          <li>Do not use the platform for abusive, fraudulent, or unauthorized communication.</li>
          <li>Operational limits and environment configuration can affect runtime behavior.</li>
        </ul>
      </section>
    </ContentShell>
  )
}
