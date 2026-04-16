import { Navigation } from "@/components/landing/navigation";
import { HeroSection } from "@/components/landing/hero-section";
import { FeaturesSection } from "@/components/landing/features-section";
import { HowItWorksSection } from "@/components/landing/how-it-works-section";
import { InfrastructureSection } from "@/components/landing/infrastructure-section";
import { MetricsSection } from "@/components/landing/metrics-section";
import { IntegrationsSection } from "@/components/landing/integrations-section";
import { SecuritySection } from "@/components/landing/security-section";
import { DevelopersSection } from "@/components/landing/developers-section";
import { TestimonialsSection } from "@/components/landing/testimonials-section";
import { CtaSection } from "@/components/landing/cta-section";
import { FooterSection } from "@/components/landing/footer-section";
import VoiceWidget from "@/src/components/VoiceWidget";

export default function Home() {
  return (
    <main className="relative min-h-screen overflow-x-hidden noise-overlay">
      <Navigation />
      <section className="relative z-20 px-4 pt-24 md:pt-28">
        <div className="mx-auto w-full max-w-[1200px] rounded-[26px] border border-foreground/10 bg-background/80 p-5 backdrop-blur-xl shadow-[0_28px_90px_-55px_rgba(10,10,10,0.8)] md:p-10">
          <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,560px)]">
            <div className="space-y-5">
              <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                Live Evaluator Demo
              </p>
              <h1 className="font-display text-4xl leading-[0.95] tracking-tight text-foreground md:text-6xl">
                Test your voice agent end to end in one place.
              </h1>
              <p className="max-w-[56ch] text-sm leading-relaxed text-muted-foreground md:text-base">
                Speak naturally, pause mid-thought, and interrupt responses to validate turn detection, transcription capture,
                and interruption handling. This evaluator now runs as a full first-class section instead of a corner widget.
              </p>

              <div className="grid gap-3 text-sm sm:grid-cols-2">
                <div className="rounded-xl border border-foreground/10 bg-background/70 px-4 py-3">
                  <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">Signal Quality</p>
                  <p className="mt-1 text-foreground">Live mic level + adaptive trigger threshold</p>
                </div>
                <div className="rounded-xl border border-foreground/10 bg-background/70 px-4 py-3">
                  <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">Turn Handling</p>
                  <p className="mt-1 text-foreground">Speech start/stop behavior tuned for natural pauses</p>
                </div>
                <div className="rounded-xl border border-foreground/10 bg-background/70 px-4 py-3">
                  <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">Transcript Feed</p>
                  <p className="mt-1 text-foreground">Continuous scrolling chat timeline inside the panel</p>
                </div>
                <div className="rounded-xl border border-foreground/10 bg-background/70 px-4 py-3">
                  <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">Evaluator Goal</p>
                  <p className="mt-1 text-foreground">Stress test real-call behavior before campaign launch</p>
                </div>
              </div>
            </div>

            <div className="w-full">
              <VoiceWidget className="min-h-[560px]" />
            </div>
          </div>
        </div>
      </section>

      <section className="relative z-20 px-4 pt-8 md:pt-10">
        <div className="mx-auto w-full max-w-[1200px]">
          <div className="rounded-xl border border-foreground/10 bg-background/75 px-4 py-3 text-center backdrop-blur-sm md:px-5">
            <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              Continue below for product architecture, workflows, and integration details
            </p>
          </div>
        </div>
      </section>
      <HeroSection />
      <FeaturesSection />
      <HowItWorksSection />
      <InfrastructureSection />
      <MetricsSection />
      <IntegrationsSection />
      <SecuritySection />
      <DevelopersSection />
      <TestimonialsSection />
      <CtaSection />
      <FooterSection />
    </main>
  );
}
