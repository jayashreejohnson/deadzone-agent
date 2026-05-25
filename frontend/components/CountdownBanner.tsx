"use client";
import type { DeadZone } from "@/lib/route";

type CountdownBannerProps = {
  zone: DeadZone;
  secondsUntil: number;
  packStatus: "preparing" | "ready" | "cached";
};

function formatTime(s: number): string {
  if (s <= 0) return "0:00";
  const m   = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

/** 4 signal bars — drain as we approach the dead zone */
function SignalBars({ secondsUntil }: { secondsUntil: number }) {
  // full bars at 60 s, 0 bars at 0 s
  const filledBars = secondsUntil <= 0 ? 0 : Math.ceil(Math.min(secondsUntil / 15, 4));
  const heights    = ["h-2", "h-3.5", "h-5", "h-7"];
  const colors     = {
    4: "#00d4ff",  // electric cyan
    3: "#60a5fa",  // blue
    2: "#f59e0b",  // amber
    1: "#ef4444",  // red
    0: "#ef4444",
  };
  const activeColor = colors[filledBars as keyof typeof colors] ?? "#ef4444";

  return (
    <div className="flex items-end gap-[3px]" title={`${filledBars}/4 bars`}>
      {heights.map((h, i) => {
        const isFilled = i < filledBars;
        return (
          <div
            key={i}
            className={`w-[5px] rounded-sm transition-all duration-500 ${h}`}
            style={{
              background:  isFilled ? activeColor : "rgba(148,163,184,0.2)",
              boxShadow:   isFilled ? `0 0 6px ${activeColor}88` : "none",
              animation:   isFilled && filledBars <= 1 ? "barFlicker 0.9s ease-in-out infinite" : "none",
            }}
          />
        );
      })}
    </div>
  );
}

function SeverityChip({ severity }: { severity?: string }) {
  const map = {
    high:   { label: "HIGH",   bg: "rgba(239,68,68,0.18)",   text: "#fca5a5", border: "rgba(239,68,68,0.4)" },
    medium: { label: "MEDIUM", bg: "rgba(245,158,11,0.15)",  text: "#fcd34d", border: "rgba(245,158,11,0.35)" },
    low:    { label: "LOW",    bg: "rgba(16,185,129,0.15)",  text: "#6ee7b7", border: "rgba(16,185,129,0.35)" },
  };
  const s = map[severity as keyof typeof map] ?? map.medium;
  return (
    <span
      className="text-[10px] font-semibold tracking-widest px-2 py-0.5 rounded-full border"
      style={{ background: s.bg, color: s.text, borderColor: s.border }}
    >
      {s.label}
    </span>
  );
}

export default function CountdownBanner({ zone, secondsUntil, packStatus }: CountdownBannerProps) {
  const isOffline = secondsUntil <= 0;
  const isCritical = secondsUntil > 0 && secondsUntil <= 10;
  const isWarning  = secondsUntil > 10 && secondsUntil <= 20;

  const borderColor = isOffline   ? "rgba(100,116,139,0.3)"
                    : isCritical  ? "rgba(239,68,68,0.5)"
                    : isWarning   ? "rgba(245,158,11,0.45)"
                    : "rgba(0,212,255,0.25)";

  const glowColor   = isOffline   ? "none"
                    : isCritical  ? "0 0 24px rgba(239,68,68,0.25)"
                    : isWarning   ? "0 0 20px rgba(245,158,11,0.2)"
                    : "0 0 20px rgba(0,212,255,0.15)";

  const PRE_ZONE_ACTIONS = [
    { icon: "📥", label: "Open your pack" },
    { icon: "💬", label: "Send a text" },
    { icon: "🗺", label: "Save maps" },
    { icon: "📸", label: "Screenshot nav" },
  ];

  return (
    <div
      className="flex flex-col rounded-xl w-full transition-all duration-500 overflow-hidden"
      style={{
        background: "rgba(5,8,16,0.88)",
        backdropFilter: "blur(18px)",
        border: `1px solid ${borderColor}`,
        boxShadow: glowColor,
      }}
    >
      {/* ── Main row ── */}
      <div className="flex items-center gap-4 px-4 py-3">
        {/* Signal bars */}
        <div className="shrink-0">
          <SignalBars secondsUntil={secondsUntil} />
        </div>

        {/* Zone info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-slate-100 font-semibold text-sm truncate">{zone.name}</span>
            <SeverityChip severity={zone.severity} />
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5 tracking-wide">
            {isOffline ? "you're in the dead zone" : `dead zone approaching`}
            {zone.duration_minutes && !isOffline ? ` · ${zone.duration_minutes} min blackout` : ""}
          </div>
        </div>

        {/* Countdown or offline state */}
        <div className="shrink-0 text-right">
          {isOffline ? (
            <div className="text-slate-400 text-sm font-medium tracking-wide">📵 offline</div>
          ) : (
            <div className="flex flex-col items-end gap-0.5">
              <span
                className="font-mono font-bold text-2xl tabular-nums leading-none"
                style={{
                  color: isCritical ? "#ef4444" : isWarning ? "#f59e0b" : "#00d4ff",
                  animation: isCritical ? "countdownGlow 0.8s ease-in-out infinite" : "none",
                  textShadow: isCritical
                    ? "0 0 12px rgba(239,68,68,0.7)"
                    : isWarning
                    ? "0 0 10px rgba(245,158,11,0.5)"
                    : "0 0 10px rgba(0,212,255,0.4)",
                }}
              >
                {formatTime(secondsUntil)}
              </span>
              <span className="text-[10px] text-slate-500 tracking-widest uppercase">until loss</span>
            </div>
          )}
        </div>

        {/* Pack status pill */}
        <div className="shrink-0">
          {packStatus === "preparing" && (
            <div className="flex items-center gap-1.5 text-xs"
                 style={{ color: "#00d4ff" }}>
              <span
                className="inline-block w-2.5 h-2.5 rounded-full border-2 animate-spin"
                style={{ borderColor: "rgba(0,212,255,0.25)", borderTopColor: "#00d4ff" }}
              />
              <span className="hidden sm:inline tracking-wide">building pack</span>
            </div>
          )}
          {packStatus === "ready" && (
            <div className="flex items-center gap-1.5 text-xs font-medium"
                 style={{ color: "#10b981" }}>
              <span>✅</span>
              <span className="hidden sm:inline tracking-wide">pack ready</span>
            </div>
          )}
          {packStatus === "cached" && (
            <div className="flex items-center gap-1.5 text-xs font-medium"
                 style={{ color: "#8b5cf6" }}>
              <span>💾</span>
              <span className="hidden sm:inline tracking-wide">cached</span>
            </div>
          )}
        </div>
      </div>

      {/* ── Pre-dead-zone action checklist ── */}
      {!isOffline && secondsUntil > 5 && (
        <div
          className="flex items-center gap-3 px-4 py-2"
          style={{ borderTop: "1px solid rgba(255,255,255,0.05)" }}
        >
          <span
            className="text-[9px] uppercase tracking-[0.18em] shrink-0"
            style={{ color: "#334155" }}
          >
            do now
          </span>
          <div className="flex items-center gap-1.5 flex-wrap">
            {PRE_ZONE_ACTIONS.map(({ icon, label }) => (
              <span
                key={label}
                className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full"
                style={{
                  background:  "rgba(255,255,255,0.04)",
                  color:       "#64748b",
                  border:      "1px solid rgba(255,255,255,0.07)",
                }}
              >
                {icon} {label}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
