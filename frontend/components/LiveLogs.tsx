"use client";
import { useEffect, useRef } from "react";

export type AgentEvent = Record<string, unknown> & { type: string };

type Line = {
  bullet: string;
  color:  string;
  label:  string;
  sub?:   string;
  glow?:  string;
};

function classify(e: AgentEvent): Line | null {
  if (e.type === "status") {
    return {
      bullet: "◈",
      color:  "#f59e0b",
      label:  (e.msg as string) || "Weak connectivity predicted ahead",
      glow:   "rgba(245,158,11,0.4)",
    };
  }
  if (e.type === "tool" && e.name === "nimble") {
    const q = String(e.query ?? "").toLowerCase();
    if (q.includes("weather"))
      return { bullet: "◈", color: "#a78bfa", label: "Gathering weather intelligence",   glow: "rgba(167,139,250,0.4)" };
    if (q.includes("road") || q.includes("traffic"))
      return { bullet: "◈", color: "#60a5fa", label: "Checking road conditions",          glow: "rgba(96,165,250,0.4)" };
    if (q.includes("news"))
      return { bullet: "◈", color: "#a78bfa", label: "Scanning local news",               glow: "rgba(167,139,250,0.4)" };
    return   { bullet: "◈", color: "#a78bfa", label: "Searching nearby services",         glow: "rgba(167,139,250,0.4)" };
  }
  if (e.type === "tool" && e.name === "senso") {
    return { bullet: "◈", color: "#10b981", label: "Assembling continuity pack", glow: "rgba(16,185,129,0.4)" };
  }
  if (e.type === "payment") {
    return {
      bullet: "⟳",
      color:  "#c4b5fd",
      label:  "x402 agent settlement",
      sub:    `${e.from} → ${e.to}  $${Number(e.amount).toFixed(2)}`,
      glow:   "rgba(196,181,253,0.4)",
    };
  }
  if (e.type === "pack_ready") {
    return {
      bullet: "✓",
      color:  "#10b981",
      label:  e.cached ? "Offline pack reused (cached)" : "Continuity pack assembled",
      glow:   "rgba(16,185,129,0.5)",
    };
  }
  if (e.type === "log") {
    return {
      bullet: "·",
      color:  e.level === "warn" ? "#fbbf24" : "#475569",
      label:  (e.msg as string) || "",
    };
  }
  return null;
}

export default function LiveLogs({ events }: { events: AgentEvent[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [events.length]);

  const lines = events.map(classify).filter(Boolean) as Line[];

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div
        className="px-4 py-3 shrink-0 flex items-center gap-2"
        style={{ borderBottom: "1px solid rgba(0,212,255,0.1)" }}
      >
        <span
          className="inline-block w-1.5 h-1.5 rounded-full animate-pulse"
          style={{ background: "#00d4ff", boxShadow: "0 0 6px #00d4ff" }}
        />
        <span className="text-[10px] uppercase tracking-[0.2em] text-slate-500 font-medium">
          Agent Log
        </span>
        {lines.length > 0 && (
          <span
            className="ml-auto text-[10px] tabular-nums px-1.5 py-0.5 rounded-full"
            style={{ background: "rgba(0,212,255,0.1)", color: "#00d4ff" }}
          >
            {lines.length}
          </span>
        )}
      </div>

      {/* Scrollable log */}
      <div
        ref={ref}
        className="flex-1 overflow-y-auto p-4 space-y-3"
        style={{ scrollbarWidth: "thin", scrollbarColor: "rgba(0,212,255,0.15) transparent" }}
      >
        {lines.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 pb-8">
            <div className="text-3xl opacity-30">🛰</div>
            <div className="text-[11px] text-slate-600 tracking-widest uppercase text-center">
              awaiting agent activity
            </div>
          </div>
        ) : (
          lines.map((l, i) => (
            <div
              key={i}
              className="flex items-start gap-3 animate-[fadeIn_0.25s_ease-out]"
            >
              {/* Bullet */}
              <div
                className="shrink-0 w-5 h-5 rounded flex items-center justify-center text-[11px] font-bold mt-0.5"
                style={{
                  background:  l.glow ? `${l.color}14` : "rgba(255,255,255,0.04)",
                  border:      `1px solid ${l.color}30`,
                  color:       l.color,
                  boxShadow:   l.glow ? `0 0 8px ${l.glow}` : "none",
                }}
              >
                {l.bullet}
              </div>

              {/* Text */}
              <div className="flex-1 min-w-0">
                <div className="text-sm leading-snug" style={{ color: l.color }}>
                  {l.label}
                </div>
                {l.sub && (
                  <div className="text-[11px] mt-0.5 font-mono tracking-wide"
                       style={{ color: "#475569" }}>
                    {l.sub}
                  </div>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
