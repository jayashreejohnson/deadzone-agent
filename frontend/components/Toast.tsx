"use client";
import { useEffect } from "react";

type Variant = "payment" | "reconnecting" | "synced";

const CONFIG: Record<Variant, { icon: string; title: string; sub: string; ring: string; iconColor: string }> = {
  payment:     { icon: "💸", title: "Agent settlement completed",
                 sub: "Continuity pack acquired instantly.",
                 ring: "ring-violet-400/40", iconColor: "" },
  reconnecting:{ icon: "📶", title: "Connectivity restored",
                 sub: "Syncing live route intelligence…",
                 ring: "ring-sky-400/40", iconColor: "" },
  synced:      { icon: "✅", title: "Real-time services resumed",
                 sub: "Your journey is fully synchronized again.",
                 ring: "ring-emerald-400/40", iconColor: "" },
};

export default function Toast({
  variant, detail, autoDismissMs = 3500, onDismiss,
}: { variant: Variant; detail?: string; autoDismissMs?: number; onDismiss: () => void }) {
  useEffect(() => {
    const id = setTimeout(onDismiss, autoDismissMs);
    return () => clearTimeout(id);
  }, [onDismiss, autoDismissMs]);

  const c = CONFIG[variant];
  return (
    <div className={`bg-slate-900/95 backdrop-blur-md rounded-xl px-4 py-3
                     ring-1 ${c.ring} animate-[fadeInRight_0.3s_ease-out]
                     min-w-[280px] max-w-sm`}>
      <div className="flex items-start gap-3">
        <span className="text-xl leading-none">{c.icon}</span>
        <div className="flex-1">
          <div className="text-slate-100 text-sm font-medium">{c.title}</div>
          <div className="text-slate-400 text-xs mt-0.5">{detail || c.sub}</div>
        </div>
      </div>
    </div>
  );
}
