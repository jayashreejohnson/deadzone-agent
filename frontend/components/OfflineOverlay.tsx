"use client";
import { useEffect, useState } from "react";

type OfflineOverlayProps = {
  durationSeconds: number;
  onDone: () => void;
};

export default function OfflineOverlay({ durationSeconds, onDone }: OfflineOverlayProps) {
  const [elapsed, setElapsed]   = useState(0);
  const [fading, setFading]     = useState(false);
  const [phase, setPhase]       = useState<"glitch" | "static" | "recover">("glitch");

  useEffect(() => {
    if (durationSeconds <= 0) { onDone(); return; }

    const id = setInterval(() => {
      setElapsed((prev) => {
        const next = prev + 0.1;
        // Phase transitions
        const ratio = next / durationSeconds;
        if (ratio > 0.85)      setPhase("recover");
        else if (ratio > 0.15) setPhase("static");
        else                   setPhase("glitch");

        if (next >= durationSeconds) {
          clearInterval(id);
          setFading(true);
          setTimeout(onDone, 700);
        }
        return next;
      });
    }, 100);
    return () => clearInterval(id);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [durationSeconds]);

  const progress = Math.min(elapsed / Math.max(durationSeconds, 1), 1);
  const remaining = Math.ceil(Math.max(durationSeconds - elapsed, 0));

  return (
    <div
      className="absolute inset-0 z-[2000] flex flex-col items-center justify-center scanlines overflow-hidden"
      style={{
        background: "rgba(2, 4, 10, 0.96)",
        opacity: fading ? 0 : 1,
        transition: fading ? "opacity 0.7s ease-out" : "none",
      }}
    >
      {/* Ambient red glow pulse */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: "radial-gradient(circle at 50% 50%, rgba(239,68,68,0.08) 0%, transparent 65%)",
          animation: "fadeIn 0.3s ease-out",
        }}
      />

      {/* Moving scanline */}
      {phase !== "recover" && (
        <div
          className="absolute left-0 right-0 h-0.5 pointer-events-none z-10"
          style={{
            background: "linear-gradient(90deg, transparent, rgba(0,212,255,0.4), transparent)",
            animation: "slideInUp 2.2s linear infinite",
            top: 0,
          }}
        />
      )}

      {/* Main content */}
      <div className="relative z-10 text-center space-y-8 px-8 max-w-md">

        {/* Glitch icon */}
        <div
          className="text-7xl select-none"
          style={{ filter: phase === "glitch" ? "hue-rotate(180deg)" : "none", transition: "filter 0.5s" }}
        >
          📵
        </div>

        {/* Glitch text */}
        <div className="relative select-none">
          <div
            className="glitch-text text-4xl font-bold tracking-[0.25em] uppercase"
            data-text="NO SIGNAL"
            style={{ color: "#ef4444" }}
          >
            NO SIGNAL
          </div>
        </div>

        {/* Sub-text */}
        <div
          className="text-slate-500 text-sm tracking-widest uppercase"
          style={{ animation: phase === "recover" ? "fadeIn 0.5s ease-out" : "none" }}
        >
          {phase === "recover" ? "signal acquiring…" : "offline pack active"}
        </div>

        {/* Progress bar */}
        <div className="space-y-2">
          <div
            className="w-full rounded-full h-1 overflow-hidden"
            style={{ background: "rgba(255,255,255,0.07)" }}
          >
            <div
              className="h-full rounded-full transition-all duration-100"
              style={{
                width: `${progress * 100}%`,
                background:
                  phase === "recover"
                    ? "linear-gradient(90deg, #10b981, #00d4ff)"
                    : "linear-gradient(90deg, #ef4444, #f97316)",
                boxShadow:
                  phase === "recover"
                    ? "0 0 8px rgba(16,185,129,0.6)"
                    : "0 0 8px rgba(239,68,68,0.6)",
              }}
            />
          </div>
          <div className="text-xs text-slate-600 tabular-nums tracking-widest">
            {remaining}s remaining
          </div>
        </div>

        {/* BSSID / fake tech readout */}
        <div
          className="text-[10px] text-slate-700 font-mono tracking-widest space-y-1"
          style={{ animation: phase === "glitch" ? "fadeIn 0.5s ease-out" : "none" }}
        >
          <div>BSSID: ██:██:██:██:██:██</div>
          <div>RSSI: –110 dBm · CHANNEL: –</div>
        </div>
      </div>
    </div>
  );
}
