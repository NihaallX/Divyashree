import Link from "next/link"
import { ContentShell } from "@/components/workspace/content-shell"

export default function AboutPage() {
  return (
    <ContentShell
      eyebrow="Company"
      title="About Nihal Pardeshi"
      description="AI-native product builder with hands-on experience scoping, shipping, and iterating on production conversational AI systems."
      maxWidthClassName="max-w-5xl"
    >

        <section className="border border-foreground/15 rounded-xl p-6 space-y-4 bg-background/70">
          <h2 className="text-2xl font-display">Mission</h2>
          <p className="text-muted-foreground leading-relaxed">
            I am building AI infrastructure for SMBs, not just voice systems but the broader workflows around lead
            capture, follow-up, and customer engagement.
          </p>
          <p className="text-muted-foreground leading-relaxed">
            This direction became personal after discussing lead generation with a local clinic and seeing how high
            costs and unclear implementation paths stop businesses from adopting AI in practical ways.
          </p>
        </section>

        <section className="border border-foreground/15 rounded-xl p-6 space-y-4 bg-background/70">
          <h2 className="text-2xl font-display">What I focus on</h2>
          <ul className="list-disc pl-5 text-muted-foreground space-y-2">
            <li>Translating customer pain points into clear PRDs and prioritized roadmaps</li>
            <li>Shipping AI products with strong UX, measurable outcomes, and production reliability</li>
            <li>Designing multilingual experiences with easy onboarding and affordable usage tiers</li>
            <li>Balancing latency, quality, and cost across LLM and voice infrastructure decisions</li>
          </ul>
        </section>

        <section className="border border-foreground/15 rounded-xl p-6 space-y-4 bg-background/70">
          <h2 className="text-2xl font-display">Experience</h2>
          <div className="text-muted-foreground space-y-3">
            <p>
              <span className="text-foreground">AI Product Intern, ChatMaven.ai</span> (Jun 2025 - Nov 2025)
            </p>
            <ul className="list-disc pl-5 space-y-2">
              <li>Owned end-to-end delivery of an AI healthcare IVR from discovery to AWS deployment</li>
              <li>Authored PRDs and feature specs aligned to operational and business outcomes</li>
              <li>Coordinated cross-functional prioritization across engineering and business teams</li>
              <li>Improved quality and reliability of LLM-driven voice, SMS, and email workflows</li>
            </ul>
          </div>
        </section>

        <section className="border border-foreground/15 rounded-xl p-6 space-y-5 bg-background/70">
          <h2 className="text-2xl font-display">Selected projects</h2>

          <div className="space-y-2">
            <h3 className="text-xl font-display">RelayX</h3>
            <p className="text-muted-foreground">AI-first outbound voice agent platform for SMBs.</p>
            <ul className="list-disc pl-5 text-muted-foreground space-y-1">
              <li>Built the product from 0-to-1 with dynamic conversational reasoning as a core differentiator</li>
              <li>Reduced latency by 89% through system-level optimization</li>
              <li>Created call-performance analytics to drive KPI-based product iteration</li>
            </ul>
          </div>

          <div className="space-y-2">
            <h3 className="text-xl font-display">Khaoozy</h3>
            <p className="text-muted-foreground">Full-stack canteen pre-order platform, led 0-to-1 and launched.</p>
            <ul className="list-disc pl-5 text-muted-foreground space-y-1">
              <li>Live product at khaoozy.tech with UPI payments and real-time order tracking</li>
              <li>Implemented end-to-end order lifecycle and automated refund safeguards</li>
              <li>Built dual interfaces for students and canteen operations</li>
            </ul>
          </div>

          <div className="space-y-2">
            <h3 className="text-xl font-display">RateMyProf India</h3>
            <p className="text-muted-foreground">Professor review platform launched from concept to production.</p>
            <ul className="list-disc pl-5 text-muted-foreground space-y-1">
              <li>Scaled to 500+ professor listings</li>
              <li>Reduced invalid submissions by 85% using moderation and spam detection workflows</li>
              <li>Reached 85+ PageSpeed score and top-6 organic SEO ranking</li>
            </ul>
          </div>
        </section>

        <section className="border border-foreground/15 rounded-xl p-6 space-y-4 bg-background/70">
          <h2 className="text-2xl font-display">Core skills</h2>
          <p className="text-muted-foreground leading-relaxed">
            AI and agents: GPT, Claude, Gemini, LangGraph, RAG, vector stores, TTS, prompt engineering.
          </p>
          <p className="text-muted-foreground leading-relaxed">
            Product: PRD authoring, MVP scoping, feature prioritization, OKR/KPI tracking, user-journey mapping,
            competitive benchmarking, and data-informed iteration.
          </p>
          <p className="text-muted-foreground leading-relaxed">
            Engineering and cloud: Python, JavaScript, SQL, FastAPI, Docker, AWS Lambda/SES/SNS/API Gateway.
          </p>
          <p className="text-muted-foreground leading-relaxed">
            Languages prioritized for SMB workflows: Hindi, Tamil, Telugu, Kannada, Malayalam, Bengali, Marathi,
            Gujarati, Punjabi, Odia, and Assamese.
          </p>
        </section>

        <section className="flex flex-wrap gap-4">
          <Link href="/docs" className="underline text-sm">Project docs</Link>
          <Link href="/developers" className="underline text-sm">Developer pages</Link>
          <a href="https://ai-pm-portfolio.vercel.app/" className="underline text-sm" target="_blank" rel="noreferrer">Portfolio</a>
          <a href="https://www.linkedin.com/in/nihaallp/" className="underline text-sm" target="_blank" rel="noreferrer">LinkedIn</a>
        </section>
    </ContentShell>
  )
}
