"use client";
import { useEffect, useMemo, useRef, useState } from "react";

export type AgentEvent = Record<string, unknown> & { type: string };

// ?? Log line classifier ??????????????????????????????????????????????????????

type Line = { bullet: string; color: string; label: string; sub?: string; glow?: string };

function classify(e: AgentEvent): Line | null {
  if (e.type === "status") {
    return { bullet: "?", color: "#f59e0b", label: (e.msg as string) || "Weak connectivity predicted ahead", glow: "rgba(245,158,11,0.4)" };
  }
  if (e.type === "tool" && e.name === "nimble") {
    const q = String(e.query ?? "").toLowerCase();
    if (q.includes("weather"))
      return { bullet: "?", color: "#a78bfa", label: "Gathering weather intelligence",   glow: "rgba(167,139,250,0.4)" };
    if (q.includes("road") || q.includes("traffic"))
      return { bullet: "?", color: "#60a5fa", label: "Checking road conditions",          glow: "rgba(96,165,250,0.4)" };
    if (q.includes("news"))
      return { bullet: "?", color: "#a78bfa", label: "Scanning local news",               glow: "rgba(167,139,250,0.4)" };
    return   { bullet: "?", color: "#a78bfa", label: "Searching nearby services",         glow: "rgba(167,139,250,0.4)" };
  }
  if (e.type === "tool" && e.name === "senso") {
    return { bullet: "?", color: "#10b981", label: "Assembling continuity pack", glow: "rgba(16,185,129,0.4)" };
  }
  if (e.type === "payment") {
    return { bullet: "?", color: "#c4b5fd", label: "x402 agent settlement", sub: `${e.from} ? ${e.to}  $${Number(e.amount).toFixed(2)}`, glow: "rgba(196,181,253,0.4)" };
  }
  if (e.type === "pack_ready") {
    return { bullet: "?", color: "#10b981", label: e.cached ? "Offline pack reused (cached)" : "Continuity pack assembled", glow: "rgba(16,185,129,0.5)" };
  }
  if (e.type === "eval_complete") {
    const score = e.score as number;
    const color = score >= 80 ? "#10b981" : score >= 60 ? "#f59e0b" : "#ef4444";
    const sla   = e.sla_pass ? "SLA ?" : "SLA ?";
    const cov   = `coverage ${Math.round((e.coverage as number) * 100)}%`;
    return { bullet: "?", color, label: `Pack quality score: ${score}/100`, sub: `${cov} ? ${sla} ? ${e.build_ms}ms build`, glow: `${color}60` };
  }
  if (e.type === "log") {
    return { bullet: "?", color: e.level === "warn" ? "#fbbf24" : "#475569", label: (e.msg as string) || "" };
  }
  // Silent event types (shown in waterfall only)
  if (e.type === "tool_start" || e.type === "tool_end" || e.type === "trace_started") return null;
  return null;
}

// ?? Waterfall ??????????????????????????????????????????????????????????????????

const TOOL_COLOR: Record<string, string> = {
  nimble_search:                  "#8b5cf6",
  senso_publish:                  "#10b981",
  clickhouse_find_recent_pack:    "#00d4ff",
  clickhouse_save_pack:           "#00d4ff",
  clickhouse_log_event:           "#475569",
  payments_pay:                   "#f59e0b",
  deliver_pack:                   "#10b981",
};
const TOOL_LABEL: Record<string, string> = {
  nimble_search:                  "search",
  senso_publish:                  "publish",
  clickhouse_find_recent_pack:    "cache lookup",
  clickhouse_save_pack:           "save pack",
  clickhouse_log_event:           "log",
  payments_pay:                   "x402 pay",
  deliver_pack:                   "deliver",
};

function WaterfallBar({ tool, t_ms, latency_ms, maxTime, ok }: {
  tool: string; t_ms: number; latency_ms: number; maxTime: number; ok?: boolean;
}) {
  const color  = ok === false ? "#ef4444" : (TOOL_COLOR[tool] ?? "#475569");
  const label  = TOOL_LABEL[tool] ?? tool;
  const left   = (t_ms / maxTime) * 100;
  const width  = Math.max((latency_ms / maxTime) * 100, 1.5);
  return (
    <div className="flex items-center gap-2 h-5">
      <div className="text-[9px] text-slate-600 w-16 text-right shrink-0 truncate" title={tool}>
        {label}
      </div>
      <div className="flex-1 relative h-3 rounded overflow-hidden" style={{ background: "rgba(255,255,255,0.03)" }}>
        <div
          className="absolute top-0 h-full rounded"
          style={{
            left:    `${left}%`,
            width:   `${width}%`,
            background: `${color}`,
            boxShadow:  `0 0 4px ${color}60`,
            minWidth: "3px",
          }}
        />
      </div>
      <div className="text-[9px] tabular-nums w-12 shrink-0" style={{ color }}>
        {latency_ms}ms
      </div>
    </div>
  );
}

// ?? Main component ????????????????????????????????????????????????????????????

export default function LiveLogs({ events, onReplay, isReplaying, traceId }: {
  events:      AgentEvent[];
  onReplay?:   () => void;
  isReplaying?: boolean;
  traceId?:    string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [showWaterfall, setShowWaterfall] = useState(false);

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [events.length]);

  // Build waterfall data from tool_start / tool_end event pairs
  const waterfallData = useMemo(() => {
    const starts = new Map<number, { tool: string; t_ms: number }>();
    const rows: { tool: string; t_ms: number; latency_ms: number; call_id: number; ok: boolean }[] = [];
    for (const ev of events) {
      if (ev.type === "tool_start") {
        starts.set(ev.call_id as number, { tool: ev.tool as string, t_ms: (ev.t_ms as number) ?? 0 });
      } else if (ev.type === "tool_end") {
        const start = starts.get(ev.call_id as number);
        if (start) {
          rows.push({
            tool:       start.tool,
            t_ms:       start.t_ms,
            latency_ms: (ev.latency_ms as number) ?? 0,
            call_id:    ev.call_id as number,
            ok:         (ev.ok as boolean) !== false,
          });
        }
      }
    }
    return rows;
  }, [events]);

  const maxTime = useMemo(() => {
    if (waterfallData.length === 0) return 1000;
    return Math.max(1, ...waterfallData.map((r) => r.t_ms + r.latency_ms));
  }, [waterfallData]);

  // Eval and trace metadata
  const evalEvent  = useMemo(() => events.findLast?.((e) => e.type === "eval_complete") ?? events.filter(e => e.type === "eval_complete").at(-1), [events]);
  const evalScore  = evalEvent ? (evalEvent.score as number) : undefined;
  const scoreColor = evalScore !== undefined ? (evalScore >= 80 ? "#10b981" : evalScore >= 60 ? "#f59e0b" : "#ef4444") : "#475569";

  const lines = events.map(classify).filter(Boolean) as Line[];

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div
        className="px-3 py-2.5 shrink-0 flex items-center gap-2"
        style={{ borderBottom: "1px solid rgba(0,212,255,0.1)" }}
      >
        <span
          className="inline-block w-1.5 h-1.5 rounded-full"
          style={{
            background: isReplaying ? "#f59e0b" : "#00d4ff",
            boxShadow: isReplaying ? "0 0 6px #f59e0b" : "0 0 6px #00d4ff",
            animation: isReplaying ? "pulse 1s infinite" : "none",
          }}
        />
        <span className="text-[10px] uppercase tracking-[0.2em] text-slate-500 font-medium">
          {isReplaying ? "Replaying?" : "Agent Log"}
        </span>

        {/* Eval badge */}
        {evalScore !== undefined && (
          <span
            className="text-[10px] font-semibold px-1.5 py-0.5 rounded tabular-nums"
            style={{ background: `${scoreColor}18`, color: scoreColor, border: `1px solid ${scoreColor}30` }}
            title="Pack quality score"
          >
            {evalScore}
          </span>
        )}

        {/* Event count */}
        {lines.length > 0 && (
          <span
            className="text-[10px] tabular-nums px-1.5 py-0.5 rounded-full"
            style={{ background: "rgba(0,212,255,0.1)", color: "#00d4ff" }}
          >
            {lines.length}
          </span>
        )}

        <div className="flex-1" />

        {/* Trace ID */}
        {traceId && (
          <span className="text-[9px] font-mono text-slate-700 truncate max-w-[64px]" title={traceId}>
            {traceId.slice(0, 14)}
          </span>
        )}

        {/* Waterfall toggle */}
        {waterfallData.length > 0 && (
          <button
            onClick={() => setShowWaterfall((v) => !v)}
            className="text-[9px] uppercase tracking-widest transition-colors"
            style={{ color: showWaterfall ? "#00d4ff" : "#475569" }}
            title="Toggle execution waterfall"
          >
            ?
          </button>
        )}

        {/* Replay button */}
        {onReplay && traceId && !isReplaying && (
          <button
            onClick={onReplay}
            className="text-[10px] px-2 py-0.5 rounded-md font-medium transition-all duration-200"
            style={{ background: "rgba(245,158,11,0.1)", color: "#f59e0b", border: "1px solid rgba(245,158,11,0.2)" }}
            title={`Replay trace ${traceId}`}
          >
            ?
          </button>
        )}
      </div>

      {/* Execution Waterfall */}
      {showWaterfall && waterfallData.length > 0 && (
        <div
          className="px-3 py-2 shrink-0 space-y-0.5"
          style={{ borderBottom: "1px solid rgba(0,212,255,0.07)", background: "rgba(0,0,0,0.2)" }}
        >
          <div className="text-[8px] uppercase tracking-[0.2em] text-slate-700 mb-1.5">
            Execution Waterfall ? {maxTime}ms total
          </div>
          {waterfallData.map((row) => (
            <WaterfallBar key={row.call_id} {...row} maxTime={maxTime} />
          ))}
        </div>
      )}

      {/* Scrollable log */}
      <div
        ref={ref}
        className="flex-1 overflow-y-auto p-4 space-y-3"
        style={{ scrollbarWidth: "thin", scrollbarColor: "rgba(0,212,255,0.15) transparent" }}
      >
        {lines.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 pb-8">
            <div className="text-3xl opacity-30">??</div>
            <div className="text-[11px] text-slate-600 tracking-widest uppercase text-center">
              awaiting agent activity
            </div>
          </div>
        ) : (
          lines.map((l, i) => (
            <div key={i} className="flex items-start gap-3 animate-[fadeIn_0.25s_ease-out]">
              <div
                className="shrink-0 w-5 h-5 rounded flex items-center justify-center text-[11px] font-bold mt-0.5"
                style={{
                  background: l.glow ? `${l.color}14` : "rgba(255,255,255,0.04)",
                  border:     `1px solid ${l.color}30`,
                  color:      l.color,
                  boxShadow:  l.glow ? `0 0 8px ${l.glow}` : "none",
                }}
              >
                {l.bullet}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm leading-snug" style={{ color: l.color }}>{l.label}</div>
                {l.sub && (
                  <div className="text-[11px] mt-0.5 font-mono tracking-wide" style={{ color: "#475569" }}>
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
