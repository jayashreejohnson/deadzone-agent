"use client";
import { useEffect, useRef } from "react";

export type AgentEvent = Record<string, unknown> & { type: string };

type Line = { bullet: string; color: string; label: string; sub?: string };

function classify(e: AgentEvent): Line | null {
  if (e.type === "status") {
    return { bullet: "⚠", color: "text-amber-300",
             label: (e.msg as string) || "Weak connectivity predicted ahead" };
  }
  if (e.type === "tool" && e.name === "nimble") {
    const q = String(e.query ?? "").toLowerCase();
    if (q.includes("weather"))
      return { bullet: "🟣", color: "text-violet-300", label: "Gathering weather intelligence" };
    if (q.includes("road") || q.includes("traffic"))
      return { bullet: "🔵", color: "text-sky-300", label: "Checking road conditions" };
    if (q.includes("news"))
      return { bullet: "🟣", color: "text-violet-300", label: "Scanning local news" };
    return { bullet: "🟣", color: "text-violet-300", label: "Searching nearby services" };
  }
  if (e.type === "tool" && e.name === "senso") {
    return { bullet: "🟢", color: "text-emerald-300",
             label: "Assembling continuity pack" };
  }
  if (e.type === "payment") {
    return {
      bullet: "💸", color: "text-violet-200",
      label: "Agent settlement",
      sub: `${e.from} → ${e.to}  $${Number(e.amount).toFixed(2)}`,
    };
  }
  if (e.type === "pack_ready") {
    return {
      bullet: "🟢", color: "text-emerald-300",
      label: e.cached ? "Offline route cached (reused)" : "Continuity pack assembled",
    };
  }
  if (e.type === "log") {
    return { bullet: "·", color: e.level === "warn" ? "text-yellow-300" : "text-slate-500",
             label: (e.msg as string) || "" };
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
    <div className="flex flex-col h-full bg-slate-950 border-l border-slate-800">
      <div className="px-4 py-3 border-b border-slate-800 text-[10px] uppercase tracking-[0.2em] text-slate-500">
        Live agent log
      </div>
      <div ref={ref} className="flex-1 overflow-y-auto p-4 space-y-2.5 text-sm">
        {lines.length === 0 ? (
          <div className="text-slate-600 text-xs">awaiting agent activity…</div>
        ) : (
          lines.map((l, i) => (
            <div key={i} className="flex items-start gap-3 animate-[fadeIn_0.25s_ease-out]">
              <span className="text-xs leading-5 shrink-0 w-5 text-center">{l.bullet}</span>
              <div className="flex-1 min-w-0">
                <div className={`${l.color} leading-snug`}>{l.label}</div>
                {l.sub && <div className="text-slate-500 text-xs mt-0.5">{l.sub}</div>}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
