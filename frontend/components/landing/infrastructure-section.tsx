"use client";

import { useEffect, useState, useRef } from "react";

const services = [
  { name: "Frontend App", role: "Next.js", endpoint: "localhost:3000" },
  { name: "Backend API", role: "FastAPI", endpoint: "localhost:8000" },
  { name: "Voice Gateway", role: "Twilio Media", endpoint: "localhost:8001" },
  { name: "Database", role: "PostgreSQL", endpoint: "DATABASE_URL" },
  { name: "Queue / Cache", role: "Redis", endpoint: "localhost:6379" },
  { name: "Tunnel", role: "ngrok/Cloudflare", endpoint: "public webhook URL" },
];

export function InfrastructureSection() {
  const [isVisible, setIsVisible] = useState(false);
  const [activeService, setActiveService] = useState(0);
  const sectionRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) setIsVisible(true);
      },
      { threshold: 0.1 }
    );

    if (sectionRef.current) observer.observe(sectionRef.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      setActiveService((prev) => (prev + 1) % services.length);
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  return (
    <section ref={sectionRef} className="relative py-24 lg:py-32 overflow-hidden">
      <div className="max-w-[1400px] mx-auto px-6 lg:px-12">
        <div className="grid lg:grid-cols-2 gap-16 lg:gap-24 items-center">
          {/* Left: Content */}
          <div
            className={`transition-all duration-700 ${
              isVisible ? "opacity-100 translate-x-0" : "opacity-0 -translate-x-8"
            }`}
          >
            <span className="inline-flex items-center gap-3 text-sm font-mono text-muted-foreground mb-6">
              <span className="w-8 h-px bg-foreground/30" />
              Infrastructure
            </span>
            <h2 className="text-4xl lg:text-6xl font-display tracking-tight mb-8">
              Built as
              <br />
              composable services.
            </h2>
            <p className="text-xl text-muted-foreground leading-relaxed mb-12">
              Divyashree runs as a practical voice stack: frontend, FastAPI backend,
              voice gateway, database, and queue/tunnel services working together.
            </p>

            {/* Stats */}
            <div className="grid grid-cols-3 gap-8">
              <div>
                <div className="text-4xl lg:text-5xl font-display mb-2">6</div>
                <div className="text-sm text-muted-foreground">Core services</div>
              </div>
              <div>
                <div className="text-4xl lg:text-5xl font-display mb-2">/health</div>
                <div className="text-sm text-muted-foreground">Runtime check</div>
              </div>
              <div>
                <div className="text-4xl lg:text-5xl font-display mb-2">/info</div>
                <div className="text-sm text-muted-foreground">Service metadata</div>
              </div>
            </div>
          </div>

          {/* Right: Service list */}
          <div
            className={`transition-all duration-700 delay-200 ${
              isVisible ? "opacity-100 translate-x-0" : "opacity-0 translate-x-8"
            }`}
          >
            <div className="border border-foreground/10">
              {/* Header */}
              <div className="px-6 py-4 border-b border-foreground/10 flex items-center justify-between">
                <span className="text-sm font-mono text-muted-foreground">Service Topology</span>
                <span className="flex items-center gap-2 text-xs font-mono text-green-600">
                  <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                  Runtime aware
                </span>
              </div>

              {/* Services */}
              <div>
                {services.map((service, index) => (
                  <div
                    key={service.name}
                    className={`px-6 py-5 border-b border-foreground/5 last:border-b-0 flex items-center justify-between transition-all duration-300 ${
                      activeService === index ? "bg-foreground/[0.02]" : ""
                    }`}
                  >
                    <div className="flex items-center gap-4">
                      <span 
                        className={`w-2 h-2 rounded-full transition-colors duration-300 ${
                          activeService === index ? "bg-foreground" : "bg-foreground/20"
                        }`}
                      />
                      <div>
                        <div className="font-medium">{service.name}</div>
                        <div className="text-sm text-muted-foreground">{service.role}</div>
                      </div>
                    </div>
                    <span className="font-mono text-sm text-muted-foreground">{service.endpoint}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
