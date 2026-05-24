"use client";
import { useEffect } from "react";

type Variant = "payment" | "reconnecting" | "synced";

const CONFIG: Record<Variant, {
  icon:   string;
  title:  string;
  sub:    string;
  accent: string;
}> = {
  payment:      { icon: "⚡", title: "Agent settlement",      sub: "x402 pack acquired.",             accent: "#8b5cf6" },
  reconnecting: { icon: "📶", title: "Connectivity restored", sub: "Syncing live route data…",         accent: "#00d4ff" },
  synced:       { icon: "✅", title: "Back online",           sub: "Real-time services resumed.",      accent: "#10b981" },
};

export default function Toast({
  variant, detail, autoDismissMs = 3500, onDismiss,
}: { variant: Variant; detail?: string; autoDismissMs?: number; onDismiss: () => void }) {
  useEffect(() => {
    const id = setTimeout(onDismiss, autoDismissMs);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const c = CONFIG[variant];

  return (
    <div
      className="flex items-start gap-3 rounded-xl px-4 py-3 animate-[fadeInRight_0.3s_ease-out] min-w-[260px] max-w-xs"
      style={{
        background:    "rgba(5, 8, 16, 0.94)",
        backdropFilter:"blur(18px)",
        border:        `1px solid ${c.accent}28`,
        boxShadow:     `0 0 30px -8px ${c.accent}20, 0 16px 32px -12px rgba(0,0,0,0.6)`,
      }}
    >
      {/* Icon */}
      <div
        className="w-8 h-8 rounded-lg flex items-center justify-center text-base shrink-0 mt-0.5"
        style={{ background: `${c.accent}14`, border: `1px solid ${c.accent}30` }}
      >
        {c.icon}
      </div>

      {/* Text */}
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold text-slate-100">{c.title}</div>
        <div className="text-xs mt-0.5" style={{ color: "#64748b" }}>
          {detail || c.sub}
        </div>
      </div>
    </div>
  );
}
