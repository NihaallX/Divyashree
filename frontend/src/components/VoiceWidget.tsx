"use client";

import { useVoiceSession, SessionStatus } from "../hooks/useVoiceSession";
import { useEffect, useRef } from "react";

interface VoiceWidgetProps {
  className?: string;
}

const STATUS_LABEL: Record<SessionStatus, string> = {
  idle: "Talk to Priya",
  connecting: "Connecting...",
  greeting: "Priya is speaking...",
  listening: "Listening...",
  processing: "Thinking...",
  speaking: "Priya is speaking...",
  error: "Something went wrong",
};

const STATUS_COLOR: Record<SessionStatus, string> = {
  idle: "text-foreground/70",
  connecting: "text-muted-foreground",
  greeting: "text-foreground",
  listening: "text-foreground",
  processing: "text-muted-foreground",
  speaking: "text-foreground",
  error: "text-destructive",
};

export default function VoiceWidget({ className = "" }: VoiceWidgetProps) {
  const { status, messages, error, micLevel, isVoiceDetected, voiceThreshold, start, stop } = useVoiceSession();
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const isActive = status !== "idle" && status !== "error";
  const micLevelPercent = Math.round(micLevel * 100);
  const thresholdPercent = Math.round(voiceThreshold * 100);

  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) {
      return;
    }
    container.scrollTop = container.scrollHeight;
  }, [messages.length]);

  return (
    <div className={`flex h-full w-full flex-col rounded-2xl border border-foreground/10 bg-background/85 p-4 backdrop-blur-xl shadow-xl shadow-foreground/5 md:p-5 ${className}`}>
      <div className="flex items-center gap-3">
        <div className="relative shrink-0">
          {isActive && (
            <div
              className="absolute -inset-1.5 rounded-full border border-foreground/40 animate-ping"
            />
          )}
          <div className="flex h-11 w-11 items-center justify-center rounded-full bg-foreground text-background text-lg font-semibold">
            P
          </div>
        </div>

        <div>
          <div className="font-display text-lg leading-none">Priya</div>
          <div className={`mt-1 text-xs font-mono uppercase tracking-wide transition-colors ${STATUS_COLOR[status]}`}>
            {STATUS_LABEL[status]}
          </div>
        </div>
      </div>

      {error && (
        <div className="mt-3 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="mt-3 rounded-xl border border-foreground/10 bg-muted/40 p-3">
        <div className="mb-2 flex items-center justify-between">
          <p className="text-xs font-mono uppercase tracking-wide text-muted-foreground">Mic activation</p>
          <p className={`text-xs font-mono ${isVoiceDetected ? "text-foreground" : "text-muted-foreground"}`}>
            {isVoiceDetected ? "Voice detected" : "Too quiet"}
          </p>
        </div>
        <div className="relative h-2 overflow-hidden rounded-full bg-foreground/10">
          <div
            className={`h-full rounded-full transition-all duration-100 ${isVoiceDetected ? "bg-foreground" : "bg-foreground/50"}`}
            style={{ width: `${micLevelPercent}%` }}
          />
          <div
            className="absolute inset-y-0 w-[2px] bg-destructive/80"
            style={{ left: `${thresholdPercent}%` }}
          />
        </div>
        <p className="mt-2 text-[11px] font-mono uppercase tracking-wide text-muted-foreground">
          level {micLevelPercent}% · trigger {thresholdPercent}%
        </p>
      </div>

      <div ref={messagesContainerRef} className="mt-3 flex min-h-[220px] max-h-[340px] flex-col gap-2 overflow-y-auto pr-1">
        {messages.length === 0 ? (
          <div className="flex h-full min-h-[220px] items-center justify-center rounded-xl border border-dashed border-foreground/15 bg-background/40 px-4 text-center text-sm text-muted-foreground">
            Start a conversation to see live transcript quality, VAD behavior, and response timing.
          </div>
        ) : (
          <>
          {messages.map((m, i) => (
            <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
              <div
                className={`max-w-[85%] rounded-xl px-3 py-2 text-sm leading-relaxed ${
                  m.role === "user"
                    ? "rounded-br-sm border border-foreground/15 bg-foreground/10 text-foreground"
                    : "rounded-bl-sm border border-foreground/10 bg-background text-foreground/90"
                }`}
              >
                {m.text}
              </div>
            </div>
          ))}
          </>
        )}
      </div>

      {status === "listening" && (
        <div className="mt-2 flex h-6 items-end justify-center gap-1">
          {[0, 1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="w-1 rounded bg-foreground/80"
              style={{ animation: `wow-bar 0.9s ease-in-out ${i * 0.12}s infinite alternate` }}
            />
          ))}
        </div>
      )}

      <div className="mt-3 flex gap-2">
        {!isActive ? (
          <button
            onClick={start}
            className="flex-1 rounded-full bg-foreground px-4 py-2.5 text-sm font-medium text-background transition hover:bg-foreground/90"
          >
            Talk to Priya
          </button>
        ) : (
          <button
            onClick={stop}
            className="flex-1 rounded-full bg-destructive px-4 py-2.5 text-sm font-medium text-white transition hover:opacity-90"
          >
            End conversation
          </button>
        )}
      </div>

      <div className="mt-2 text-center font-mono text-[11px] uppercase tracking-wide text-muted-foreground">
        Live evaluator demo
      </div>

      <style>{`
        @keyframes wow-bar {
          from { height: 6px; opacity: 0.5; }
          to { height: 22px; opacity: 1; }
        }
      `}</style>
    </div>
  );
}
