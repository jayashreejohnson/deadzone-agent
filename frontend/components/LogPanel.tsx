"use client";
import { useEffect, useRef } from "react";

export type AgentEvent = Record<string, any> & { type: string; _ts?: number };

function renderLine(e: AgentEvent): { color: string; text: string } {
  switch (e.type) {
    case "status":
      return { color: "text-orange-300", text: `⚠️  ${e.msg}` };
    case "tool":
      if (e.name === "nimble") return { color: "text-sky-300", text: `🔎 nimble.search("${e.query}")` };
      if (e.name === "senso") return { color: "text-violet-300", text: `📤 senso.publish — ${e.msg}` };
      return { color: "text-slate-300", text: `🛠  ${e.name}` };
    case "payment":
      return {
        color: "text-emerald-300",
        text: `💸 x402: ${e.from} → ${e.to}  $${Number(e.amount).toFixed(4)}  tx=${e.tx?.slice(0, 14)}…`,
      };
    case "pack_ready":
      return {
        color: "text-emerald-400 font-semibold",
        text: e.cached ? `✅ pack delivered (CACHED) — ${e.url}` : `✅ pack delivered — ${e.url}`,
      };
    case "log":
      return { color: e.level === "warn" ? "text-yellow-300" : "text-slate-400", text: `· ${e.msg}` };
    default:
      return { color: "text-slate-500", text: JSON.stringify(e) };
  }
}

export default function LogPanel({ events }: { events: AgentEvent[] }) {
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [events.length]);
  return (
    <div className="flex flex-col h-full bg-slate-950 border-l border-slate-800">
      <div className="px-4 py-2 border-b border-slate-800 text-xs uppercase tracking-wider text-slate-400">
        Agent log (live)
      </div>
      <div ref={scrollRef} className="flex-1 overflow-y-auto font-mono text-[12px] leading-relaxed p-3 space-y-1">
        {events.length === 0 ? (
          <div className="text-slate-600">waiting for events…</div>
        ) : (
          events.map((e, i) => {
            const { color, text } = renderLine(e);
            return <div key={i} className={color}>{text}</div>;
          })
        )}
      </div>
    </div>
  );
}
