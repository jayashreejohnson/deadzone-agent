"use client";
import { useEffect, useState } from "react";

/**
 * Floating phone-shaped widget that auto-cycles through three mini mockups
 * of mobile features. Always visible (z-index 1600 — above the trip planner
 * backdrop) so LinkedIn visitors see the mobile vision without clicking.
 *
 * Click anywhere on the widget → opens /mobile in a new tab.
 */

const CYCLE_MS = 5000;
const FADE_MS = 400;

// ── Compact mini-screens ─────────────────────────────────────
// Designed at 124×216 (the inside-phone canvas). Faithful in spirit to the
// full /mobile mockups but simplified for legibility at this scale.

function MiniGPS() {
  return (
    <div className="h-full flex flex-col" style={{ background: "#060b14" }}>
      <div className="flex justify-between px-2 pt-1 pb-0.5" style={{ fontSize: 6, color: "#555" }}>
        <span>9:41</span><span>●●●</span>
      </div>
      <div className="relative mx-1.5 rounded-lg overflow-hidden" style={{ background: "#0a1828", height: 70 }}>
        <svg className="absolute inset-0" width="100%" height="100%" viewBox="0 0 120 70">
          <polyline points="10,58 30,42 60,28 90,18 110,12"
            stroke="#00d4ff" strokeWidth="1.4" fill="none" strokeDasharray="3 2" opacity=".7" />
          <circle cx="110" cy="12" r="9" fill="#ef4444" opacity=".14" />
          <circle cx="110" cy="12" r="9" stroke="#ef4444" strokeWidth="0.8" fill="none" opacity=".7" />
          <circle cx="30" cy="42" r="3" fill="#00d4ff" />
          <circle cx="30" cy="42" r="3" fill="none" stroke="#00d4ff" strokeWidth="0.7" opacity=".5">
            <animate attributeName="r" values="4;9;4" dur="2.4s" repeatCount="indefinite" />
            <animate attributeName="opacity" values=".55;0;.55" dur="2.4s" repeatCount="indefinite" />
          </circle>
        </svg>
        <div className="absolute top-1 left-1 flex items-center gap-1" style={{ fontSize: 6, color: "#22c55e" }}>
          <span style={{ width: 4, height: 4, borderRadius: "50%", background: "#22c55e", display: "inline-block" }} />
          Monitoring
        </div>
      </div>
      <div className="px-1.5 mt-1.5 space-y-1">
        <div className="rounded-md px-1.5 py-1 flex items-center gap-1.5" style={{ background: "#0d1e30" }}>
          <span style={{ fontSize: 10 }}>📍</span>
          <div>
            <div style={{ fontSize: 5.5, color: "#475569" }}>Background</div>
            <div style={{ fontSize: 7.5, color: "#e2e8f0", fontWeight: 600 }}>Route detected</div>
          </div>
        </div>
        <div className="rounded-md px-1.5 py-1 flex items-center gap-1.5"
          style={{ background: "#180e0e", border: "1px solid #3f1515" }}>
          <span style={{ fontSize: 10 }}>⚠️</span>
          <div>
            <div style={{ fontSize: 5.5, color: "#f87171" }}>Dead zone · 18 min</div>
            <div style={{ fontSize: 7.5, color: "#e2e8f0", fontWeight: 600 }}>Building pack</div>
          </div>
        </div>
      </div>
    </div>
  );
}

function MiniCountdown() {
  return (
    <div className="h-full flex flex-col items-center justify-center relative"
      style={{ background: "linear-gradient(160deg, #090e1e 0%, #18082e 50%, #090e1e 100%)" }}>
      <div className="text-center mt-2">
        <div style={{ fontSize: 30, fontWeight: 200, color: "#fff", lineHeight: 1 }}>10:47</div>
        <div style={{ fontSize: 6, color: "#64748b", marginTop: 3 }}>Tuesday, May 24</div>
      </div>
      <div className="absolute bottom-3 left-2 right-2 rounded-lg p-1.5"
        style={{ background: "rgba(14,16,30,.9)", backdropFilter: "blur(12px)",
                 border: "1px solid rgba(255,255,255,.07)" }}>
        <div className="flex items-center gap-1 mb-1">
          <div className="rounded-md flex items-center justify-center"
            style={{ width: 14, height: 14, background: "rgba(0,212,255,.1)",
                     border: "1px solid rgba(0,212,255,.18)" }}>
            <span style={{ fontSize: 8 }}>📡</span>
          </div>
          <span style={{ fontSize: 6.5, color: "#64748b" }}>DeadZone</span>
          <span style={{ fontSize: 6, color: "#334155", marginLeft: "auto" }}>now</span>
        </div>
        <div style={{ fontSize: 8, color: "#f1f5f9", fontWeight: 700, marginBottom: 1 }}>Dead zone in 3 min</div>
        <div style={{ fontSize: 6.5, color: "#64748b" }}>Your offline pack is ready.</div>
      </div>
    </div>
  );
}

function MiniContent() {
  return (
    <div className="h-full flex flex-col items-center justify-center relative overflow-hidden"
      style={{ background: "#000" }}>
      <div className="absolute inset-0"
        style={{ background: "linear-gradient(180deg, #050510 0%, #080518 50%, #050510 100%)" }} />
      <div className="absolute top-2 right-2 flex items-center gap-0.5 px-1.5 py-0.5 rounded-full"
        style={{ background: "rgba(239,68,68,.1)", border: "1px solid rgba(239,68,68,.18)",
                 fontSize: 6, color: "#f87171" }}>
        <span>📵</span><span>No Signal</span>
      </div>
      <div className="absolute inset-0 flex items-center justify-center"
        style={{ fontSize: 36, color: "rgba(255,255,255,.04)" }}>▶</div>
      <div className="relative z-10 mx-2 rounded-lg p-2.5 text-center"
        style={{ background: "rgba(0,14,6,.92)", border: "1px solid rgba(34,197,94,.16)",
                 backdropFilter: "blur(12px)" }}>
        <div style={{ fontSize: 7, color: "#22c55e", fontWeight: 700, marginBottom: 4 }}>Content pre-fetched</div>
        <div style={{ fontSize: 22, color: "#fff", fontWeight: 700, lineHeight: 1 }}>22 min</div>
        <div style={{ fontSize: 6.5, color: "#475569", marginBottom: 7 }}>staged for your tunnel</div>
        <div className="flex justify-center gap-1.5" style={{ fontSize: 6.5 }}>
          <span style={{ color: "#f97316" }}>4 reels</span>
          <span style={{ color: "#1e293b" }}>·</span>
          <span style={{ color: "#a78bfa" }}>3 articles</span>
        </div>
      </div>
    </div>
  );
}

const SCREENS: { node: React.ReactNode; label: string }[] = [
  { node: <MiniGPS />,       label: "GPS auto-detection" },
  { node: <MiniCountdown />, label: "Dead zone countdown" },
  { node: <MiniContent />,   label: "Content pre-fetch"  },
];

// ── Compact phone frame ──────────────────────────────────────

function MiniPhone({ children }: { children: React.ReactNode }) {
  // Outer phone shell — 130×240, notch + side buttons for that "real device"
  // recognition. Inner canvas where the screen content lives: ~124×216.
  return (
    <div className="relative" style={{ width: 130, height: 240 }}>
      <div
        className="absolute inset-0 overflow-hidden"
        style={{
          borderRadius: 22,
          background: "#0c0c18",
          border: "2px solid #252535",
          boxShadow: "inset 0 0 0 1px #2a2a3c",
        }}
      >
        {/* Notch */}
        <div className="absolute z-20"
          style={{ top: 5, left: "50%", transform: "translateX(-50%)",
                   width: 38, height: 8, background: "#000", borderRadius: 6 }} />
        {/* Screen content */}
        <div className="absolute inset-0 overflow-hidden" style={{ paddingTop: 16 }}>
          {children}
        </div>
        {/* Glass sheen */}
        <div className="absolute inset-0 pointer-events-none"
          style={{ borderRadius: 22,
                   background: "linear-gradient(135deg, rgba(255,255,255,.05) 0%, transparent 52%)" }} />
      </div>
      {/* Side buttons */}
      <div className="absolute rounded-l-sm"
        style={{ left: -2, top: 40, width: 2, height: 16, background: "#202030" }} />
      <div className="absolute rounded-l-sm"
        style={{ left: -2, top: 62, width: 2, height: 16, background: "#202030" }} />
      <div className="absolute rounded-r-sm"
        style={{ right: -2, top: 52, width: 2, height: 26, background: "#202030" }} />
    </div>
  );
}

// ── Main widget ──────────────────────────────────────────────

export default function MobileVisionWidget() {
  const [idx, setIdx] = useState(0);
  const [visible, setVisible] = useState(true);
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReducedMotion(mq.matches);
    const handler = (e: MediaQueryListEvent) => setReducedMotion(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  useEffect(() => {
    if (reducedMotion) return;
    const interval = setInterval(() => {
      setVisible(false);
      setTimeout(() => {
        setIdx((i) => (i + 1) % SCREENS.length);
        setVisible(true);
      }, FADE_MS);
    }, CYCLE_MS);
    return () => clearInterval(interval);
  }, [reducedMotion]);

  const current = SCREENS[idx];

  return (
    <a
      href="/mobile"
      target="_blank"
      rel="noopener noreferrer"
      aria-label="View the full mobile vision for DeadZone — opens in new tab"
      className="hidden sm:flex absolute flex-col items-center gap-1.5 group transition-all duration-300 hover:-translate-y-1"
      style={{
        bottom: "5.5rem",
        left:   "1rem",
        zIndex: 1600,
      }}
    >
      {/* Tiny banner above the phone — sets context */}
      <div
        className="flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[8px] font-medium tracking-[0.18em] uppercase"
        style={{
          background: "rgba(167,139,250,0.1)",
          color:      "#c4b5fd",
          border:     "1px solid rgba(167,139,250,0.25)",
          letterSpacing: "0.2em",
        }}
      >
        <span style={{ width: 4, height: 4, borderRadius: "50%", background: "#a78bfa",
                       boxShadow: "0 0 6px #a78bfa", display: "inline-block" }} />
        Coming to mobile
      </div>

      {/* Phone with pulsing border */}
      <div
        className={reducedMotion ? "relative" : "relative mvw-glow-animated"}
        style={{
          padding: 2,
          borderRadius: 24,
          background: "linear-gradient(135deg, rgba(0,212,255,0.18) 0%, rgba(167,139,250,0.18) 100%)",
          boxShadow:  "0 0 28px -8px rgba(0,212,255,0.35), 0 16px 40px -12px rgba(0,0,0,0.7)",
          animation:  reducedMotion ? "none" : "mvw-glow 4s ease-in-out infinite",
        }}
      >
        <MiniPhone>
          <div
            style={{
              opacity:    visible ? 1 : 0,
              transition: `opacity ${FADE_MS}ms ease-in-out`,
              height:     "100%",
            }}
          >
            {current.node}
          </div>
        </MiniPhone>
      </div>

      {/* Caption */}
      <div className="flex items-center gap-1.5 px-2 py-1 rounded-lg text-[10px] font-medium transition-all duration-300"
        style={{
          background: "rgba(5,8,16,0.85)",
          backdropFilter: "blur(12px)",
          border: "1px solid rgba(0,212,255,0.1)",
          color: "#94a3b8",
          minWidth: 130,
          justifyContent: "center",
        }}
      >
        <span style={{ color: "#7dd3fc" }}>{current.label}</span>
        <span className="transition-transform duration-300 group-hover:translate-x-0.5"
              style={{ color: "#a78bfa" }}>→</span>
      </div>

    </a>
  );
}
