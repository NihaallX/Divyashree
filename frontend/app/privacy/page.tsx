import { ContentShell } from "@/components/workspace/content-shell"

export default function PrivacyPage() {
  return (
    <ContentShell
      eyebrow="Legal"
      title="Privacy"
      description="This page summarizes data handling for Divyashree project environments."
      maxWidthClassName="max-w-4xl"
    >
      <section className="rounded-xl border border-foreground/15 bg-background/70 p-6">
        <ul className="list-disc pl-5 text-muted-foreground space-y-2">
          <li>Authentication data is managed through backend auth routes and database storage.</li>
          <li>Call and campaign metadata may be stored for analytics and operational workflows.</li>
          <li>Service integrations (for example, Twilio) may process call-related records.</li>
          <li>Access to protected APIs requires valid bearer tokens.</li>
        </ul>
      </section>
    </ContentShell>
  )
}
