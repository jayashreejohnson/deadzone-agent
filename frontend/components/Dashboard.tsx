"use client";
import { useEffect, useState } from "react";

type Summary = {
  packs_built:    number;
  packs_sold:     number;
  total_paid_usd: number;
  avg_build_ms:   number;
  recent_events:  {
    user_id:     string;
    action:      string;
    deadzone_id: string;
    pack_id:     string;
    ts:          string;
  }[];
};

const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

type StatDef = {
  icon:  string;
  label: string;
  value: string | number;
  color: string;
};

function StatPill({ icon, label, value, color }: StatDef) {
  return (
    <div className="flex items-center gap-2.5">
      <span
        className="w-6 h-6 rounded-md flex items-center justify-center text-sm shrink-0"
        style={{ background: `${color}15`, border: `1px solid ${color}30` }}
      >
        {icon}
      </span>
      <div>
        <div
          className="text-sm font-semibold tabular-nums leading-none"
          style={{ color, textShadow: `0 0 10px ${color}60` }}
        >
          {value}
        </div>
        <div className="text-[9px] text-slate-600 uppercase tracking-widest mt-0.5">{label}</div>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [data, setData]         = useState<Summary | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let alive = true;
    const fetchOnce = async () => {
      try {
        const r = await fetch(`${API}/dashboard`);
        const j = await r.json();
        if (alive) setData(j);
      } catch {}
    };
    fetchOnce();
    const id = setInterval(fetchOnce, 3000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const stats: StatDef[] = [
    { icon: "⚡", label: "packs built", value: data?.packs_built ?? "—",                           color: "#00d4ff" },
    { icon: "💾", label: "packs sold",  value: data?.packs_sold  ?? "—",                           color: "#8b5cf6" },
    { icon: "$",  label: "$ paid",      value: data ? `$${data.total_paid_usd.toFixed(2)}` : "—", color: "#10b981" },
    { icon: "⏱", label: "avg build",   value: data ? `${Number(data.avg_build_ms).toFixed(0)}ms` : "—", color: "#f59e0b" },
  ];

  const actionColor = (a: string) =>
    a === "built"  ? "#10b981"
    : a === "bought" ? "#8b5cf6"
    : "#475569";

  return (
    <div
      style={{
        background:    "rgba(5, 8, 16, 0.92)",
        backdropFilter:"blur(18px)",
        borderTop:     "1px solid rgba(0, 212, 255, 0.1)",
      }}
    >
      {/* Expanded events table */}
      {expanded && (
        <div
          className="px-4 pt-3 pb-2 overflow-y-auto animate-[slideInUp_0.25s_ease-out]"
          style={{ maxHeight: "200px", borderBottom: "1px solid rgba(0,212,255,0.07)" }}
        >
          <div className="text-[9px] uppercase tracking-[0.2em] text-slate-600 mb-2">
            Recent Events
          </div>
          {(data?.recent_events ?? []).length === 0 ? (
            <div className="text-[11px] text-slate-600 py-2">No events yet</div>
          ) : (
            <div className="space-y-1.5">
              {(data?.recent_events ?? []).map((e, i) => (
                <div key={i} className="flex items-center gap-3 text-xs">
                  <span className="text-slate-600 w-16 shrink-0 tabular-nums text-[10px]">
                    {new Date(e.ts).toLocaleTimeString()}
                  </span>
                  <span
                    className="font-semibold w-12 shrink-0 text-[10px] tracking-wider uppercase"
                    style={{ color: actionColor(e.action) }}
                  >
                    {e.action}
                  </span>
                  <span className="text-slate-400 truncate min-w-0 text-[11px]">
                    {e.deadzone_id}
                  </span>
                  <span className="text-slate-600 font-mono text-[10px] shrink-0 hidden md:block truncate max-w-[120px]">
                    {e.pack_id}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Stats bar */}
      <div className="flex items-center gap-6 px-4 py-2.5">
        {/* Context label — explains the agent economy to non-technical users */}
        <div
          className="shrink-0 text-[9px] uppercase tracking-[0.2em] pr-3 hidden sm:block"
          style={{ color: "#334155", borderRight: "1px solid rgba(0,212,255,0.08)" }}
          title="AI agents autonomously assemble offline continuity packs before you enter dead zones"
        >
          Nimble Network
        </div>
        {stats.map((s) => (
          <StatPill key={s.label} {...s} />
        ))}

        {/* Separator */}
        <div className="flex-1" />

        {/* Expand toggle */}
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest transition-colors duration-200"
          style={{ color: expanded ? "#00d4ff" : "#475569" }}
        >
          <span>{expanded ? "▼" : "▲"}</span>
          <span className="hidden sm:inline">{expanded ? "hide" : "events"}</span>
        </button>
      </div>
    </div>
  );
}
