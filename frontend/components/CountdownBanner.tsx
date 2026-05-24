"use client";
import type { DeadZone } from "@/lib/route";

type CountdownBannerProps = {
  zone: DeadZone;
  secondsUntil: number;
  packStatus: "preparing" | "ready" | "cached";
};

function formatTime(s: number): string {
  if (s <= 0) return "0:00";
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

function severityIcon(severity?: string): string {
  if (severity === "high") return "⚠️";
  if (severity === "medium") return "🟡";
  if (severity === "low") return "🟢";
  return "📵";
}

export default function CountdownBanner({ zone, secondsUntil, packStatus }: CountdownBannerProps) {
  const isOffline = secondsUntil <= 0;

  // Background transitions: blue → orange → red → dark
  let bgClass = "bg-sky-900/90 border-sky-500/40";
  if (isOffline) {
    bgClass = "bg-slate-900/95 border-slate-600/40";
  } else if (secondsUntil <= 10) {
    bgClass = "bg-red-900/90 border-red-500/40";
  } else if (secondsUntil <= 20) {
    bgClass = "bg-orange-900/90 border-orange-500/40";
  }

  return (
    <div
      className={`${bgClass} backdrop-blur-md border rounded-xl px-4 py-3 flex items-center gap-4 w-full transition-colors duration-500`}
    >
      <div className="flex items-center gap-2 flex-1 min-w-0">
        <span className="text-lg">{severityIcon(zone.severity)}</span>
        <div className="min-w-0">
          <div className="text-slate-100 font-medium text-sm truncate">{zone.name}</div>
          {zone.severity && (
            <div className="text-xs text-slate-400 capitalize">{zone.severity} severity</div>
          )}
        </div>
      </div>

      {isOffline ? (
        <div className="text-slate-100 font-semibold text-sm whitespace-nowrap">
          📵 Offline mode — your pack is loaded
        </div>
      ) : (
        <div className="flex items-center gap-1 shrink-0">
          <span className="text-slate-400 text-sm">Dead zone in</span>
          <span
            className={`font-mono font-bold text-lg tabular-nums ${
              secondsUntil <= 10
                ? "text-red-400 animate-pulse"
                : secondsUntil <= 20
                ? "text-orange-400"
                : "text-sky-300"
            }`}
          >
            {formatTime(secondsUntil)}
          </span>
        </div>
      )}

      <div className="shrink-0">
        {packStatus === "preparing" && (
          <div className="flex items-center gap-1.5 text-sky-300 text-xs">
            <span className="inline-block w-3 h-3 border-2 border-sky-400/30 border-t-sky-400 rounded-full animate-spin" />
            Building offline pack...
          </div>
        )}
        {packStatus === "ready" && (
          <div className="flex items-center gap-1.5 text-emerald-300 text-xs">
            <span>✅</span>
            <span>Pack ready — you&apos;re covered</span>
          </div>
        )}
        {packStatus === "cached" && (
          <div className="flex items-center gap-1.5 text-sky-300 text-xs">
            <span>💾</span>
            <span>Cached pack purchased</span>
          </div>
        )}
      </div>
    </div>
  );
}
