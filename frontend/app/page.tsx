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
        <div className="mx-auto flex w-full max-w-[1200px] justify-center md:justify-end">
          <div className="w-full max-w-[420px]">
            <div className="mb-2 text-center md:text-right">
              <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                Instant Evaluator Access
              </p>
            </div>
            <VoiceWidget />
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
