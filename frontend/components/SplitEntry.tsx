"use client";
import { useEffect, useState } from "react";

/**
 * First-visit split-screen hero. Equal-weighted left/right halves:
 *   Left  — "Try it now" (the live demo)
 *   Right — "Coming to your phone" (the mobile vision)
 *
 * Dismisses on either CTA click; localStorage flag prevents re-showing.
 * Returning visitors see the demo directly with persistent top nav tabs.
 *
 * Designed based on 30-agent design test where this approach won on
 * "Likelihood to click" (3.7/5 vs. 2.4/5 for the floating widget).
 * Copy refined from agent feedback ("Mobile Vision" → "Coming to Your Phone";
 * "Live Demo" → "Try It Now").
 */

const FLAG_KEY = "deadzone.entryDismissed.v1";
const CYCLE_MS = 7000; // slowed from 5s per agent feedback (Cassie/Asha/Vivian)
const FADE_MS = 400;

const MOBILE_PREVIEWS: { label: string; node: React.ReactNode }[] = [
  { label: "GPS auto-detection",   node: <PreviewGPS /> },
  { label: "Dead zone countdown",  node: <PreviewCountdown /> },
  { label: "Content pre-fetch",    node: <PreviewContent /> },
];

function PreviewGPS() {
  return (
    <div className="h-full flex flex-col" style={{ background: "#060b14" }}>
      <div className="flex justify-between px-3 pt-1.5 pb-0.5" style={{ fontSize: 8, color: "#555" }}>
        <span>9:41</span><span>●●● 87%</span>
      </div>
      <div className="relative mx-2 rounded-lg overflow-hidden" style={{ background: "#0a1828", height: 120 }}>
        <svg className="absolute inset-0" width="100%" height="100%" viewBox="0 0 200 120">
          <polyline points="18,100 50,75 90,50 130,30 170,18"
            stroke="#00d4ff" strokeWidth="2" fill="none" strokeDasharray="4 3" opacity=".7" />
          <circle cx="170" cy="18" r="14" fill="#ef4444" opacity=".14" />
          <circle cx="170" cy="18" r="14" stroke="#ef4444" strokeWidth="1.2" fill="none" opacity=".7" />
          <circle cx="50" cy="75" r="4" fill="#00d4ff" />
          <circle cx="50" cy="75" r="4" fill="none" stroke="#00d4ff" strokeWidth="1" opacity=".5">
            <animate attributeName="r" values="6;14;6" dur="2.4s" repeatCount="indefinite" />
            <animate attributeName="opacity" values=".55;0;.55" dur="2.4s" repeatCount="indefinite" />
          </circle>
        </svg>
        <div className="absolute top-2 left-2 flex items-center gap-1" style={{ fontSize: 8, color: "#22c55e" }}>
          <span style={{ width: 5, height: 5, borderRadius: "50%", background: "#22c55e", display: "inline-block" }} />
          Monitoring
        </div>
      </div>
      <div className="px-2 mt-2 space-y-1.5">
        <div className="rounded-md px-2 py-1.5 flex items-center gap-2" style={{ background: "#0d1e30" }}>
          <span style={{ fontSize: 14 }}>📍</span>
          <div>
            <div style={{ fontSize: 7, color: "#475569" }}>Background</div>
            <div style={{ fontSize: 10, color: "#e2e8f0", fontWeight: 600 }}>Route detected</div>
          </div>
        </div>
        <div className="rounded-md px-2 py-1.5 flex items-center gap-2"
          style={{ background: "#180e0e", border: "1px solid #3f1515" }}>
          <span style={{ fontSize: 14 }}>⚠️</span>
          <div>
            <div style={{ fontSize: 7, color: "#f87171" }}>Dead zone · 18 min</div>
            <div style={{ fontSize: 10, color: "#e2e8f0", fontWeight: 600 }}>Saving for offline</div>
          </div>
        </div>
      </div>
    </div>
  );
}

function PreviewCountdown() {
  return (
    <div className="h-full flex flex-col items-center justify-center relative"
      style={{ background: "linear-gradient(160deg, #090e1e 0%, #18082e 50%, #090e1e 100%)" }}>
      <div className="text-center mt-3">
        <div style={{ fontSize: 38, fontWeight: 200, color: "#fff", lineHeight: 1 }}>10:47</div>
        <div style={{ fontSize: 8, color: "#64748b", marginTop: 4 }}>Tuesday, May 24</div>
      </div>
      <div className="absolute bottom-4 left-3 right-3 rounded-lg p-2"
        style={{ background: "rgba(14,16,30,.9)", backdropFilter: "blur(12px)",
                 border: "1px solid rgba(255,255,255,.07)" }}>
        <div className="flex items-center gap-1.5 mb-1">
          <div className="rounded-md flex items-center justify-center"
            style={{ width: 18, height: 18, background: "rgba(0,212,255,.1)",
                     border: "1px solid rgba(0,212,255,.18)" }}>
            <span style={{ fontSize: 10 }}>📡</span>
          </div>
          <span style={{ fontSize: 8, color: "#64748b" }}>DeadZone</span>
          <span style={{ fontSize: 7, color: "#334155", marginLeft: "auto" }}>now</span>
        </div>
        <div style={{ fontSize: 10, color: "#f1f5f9", fontWeight: 700, marginBottom: 2 }}>Dead zone in 3 min</div>
        <div style={{ fontSize: 8, color: "#64748b" }}>Your offline pack is ready.</div>
      </div>
    </div>
  );
}

function PreviewContent() {
  return (
    <div className="h-full flex flex-col items-center justify-center relative overflow-hidden"
      style={{ background: "#000" }}>
      <div className="absolute inset-0"
        style={{ background: "linear-gradient(180deg, #050510 0%, #080518 50%, #050510 100%)" }} />
      <div className="absolute top-3 right-3 flex items-center gap-1 px-2 py-0.5 rounded-full"
        style={{ background: "rgba(239,68,68,.1)", border: "1px solid rgba(239,68,68,.18)",
                 fontSize: 8, color: "#f87171" }}>
        <span>📵</span><span>No Signal</span>
      </div>
      <div className="relative z-10 mx-3 rounded-lg p-3 text-center"
        style={{ background: "rgba(0,14,6,.92)", border: "1px solid rgba(34,197,94,.16)",
                 backdropFilter: "blur(12px)" }}>
        <div style={{ fontSize: 9, color: "#22c55e", fontWeight: 700, marginBottom: 5 }}>Content saved offline</div>
        <div style={{ fontSize: 28, color: "#fff", fontWeight: 700, lineHeight: 1 }}>22 min</div>
        <div style={{ fontSize: 8, color: "#475569", marginBottom: 9 }}>staged for your tunnel</div>
        <div className="flex justify-center gap-2" style={{ fontSize: 8 }}>
          <span style={{ color: "#f97316" }}>4 reels</span>
          <span style={{ color: "#1e293b" }}>·</span>
          <span style={{ color: "#a78bfa" }}>3 articles</span>
        </div>
      </div>
    </div>
  );
}

function PhoneFrame({ children }: { children: React.ReactNode }) {
  // Sized down from 200x380 so the right column fits without scrolling
  // on common laptop viewports (1366x768 and up).
  return (
    <div className="relative shrink-0" style={{ width: 168, height: 320 }}>
      <div
        className="absolute inset-0 overflow-hidden"
        style={{
          borderRadius: 28,
          background: "#0c0c18",
          border: "3px solid #252535",
          boxShadow: "inset 0 0 0 1px #2a2a3c, 0 24px 60px -16px rgba(0,0,0,0.8)",
        }}
      >
        <div className="absolute z-20"
          style={{ top: 7, left: "50%", transform: "translateX(-50%)",
                   width: 50, height: 14, background: "#000", borderRadius: 9 }} />
        <div className="absolute inset-0 overflow-hidden" style={{ paddingTop: 24 }}>
          {children}
        </div>
        <div className="absolute inset-0 pointer-events-none"
          style={{ borderRadius: 28,
                   background: "linear-gradient(135deg, rgba(255,255,255,.06) 0%, transparent 52%)" }} />
      </div>
    </div>
  );
}

type Props = {
  onTryDemo: () => void;
  onExploreMobile: () => void;
};

export default function SplitEntry({ onTryDemo, onExploreMobile }: Props) {
  const [idx, setIdx] = useState(0);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const interval = setInterval(() => {
      setVisible(false);
      setTimeout(() => {
        setIdx((i) => (i + 1) % MOBILE_PREVIEWS.length);
        setVisible(true);
      }, FADE_MS);
    }, CYCLE_MS);
    return () => clearInterval(interval);
  }, []);

  const current = MOBILE_PREVIEWS[idx];

  return (
    <div
      className="fixed inset-0 z-[2000] flex flex-col"
      style={{
        background: "#050810",
        animation: "fadeIn 0.4s ease-out",
      }}
    >
      {/* Top brand strip */}
      <div className="flex items-center justify-center px-6 py-4 shrink-0"
        style={{ borderBottom: "1px solid rgba(0,212,255,0.08)" }}>
        <div className="flex items-center gap-2">
          <div className="relative">
            <span
              className="inline-block w-2 h-2 rounded-full"
              style={{ background: "#00d4ff", boxShadow: "0 0 8px #00d4ff" }}
            />
            <span
              className="absolute inset-0 inline-block w-2 h-2 rounded-full animate-ping"
              style={{ background: "#00d4ff", opacity: 0.4 }}
            />
          </div>
          <span className="font-bold text-sm tracking-tight" style={{ color: "#e2e8f0" }}>
            DeadZone
          </span>
        </div>
      </div>

      {/* Split content */}
      <div className="flex-1 flex flex-col lg:flex-row min-h-0">

        {/* LEFT — Try it now */}
        <button
          onClick={onTryDemo}
          className="flex-1 flex flex-col items-center justify-center px-8 py-8 group relative overflow-y-auto transition-all duration-300"
          style={{
            background: "linear-gradient(135deg, rgba(0,212,255,0.04) 0%, rgba(5,8,16,0) 100%)",
            borderRight: "1px solid rgba(0,212,255,0.08)",
            borderBottom: "1px solid rgba(0,212,255,0.08)",
            cursor: "pointer",
            minHeight: 0,
          }}
        >
          {/* Ambient map preview */}
          <div className="absolute inset-0 opacity-30 pointer-events-none">
            <svg className="absolute inset-0 w-full h-full" viewBox="0 0 600 600" preserveAspectRatio="xMidYMid slice">
              <path d="M 50 480 Q 200 380 320 320 Q 440 260 560 180"
                stroke="#00d4ff" strokeWidth="2.5" fill="none" strokeDasharray="6 4" opacity="0.5" />
              <circle cx="320" cy="320" r="35" fill="rgba(239,68,68,0.18)" />
              <circle cx="320" cy="320" r="35" stroke="#ef4444" strokeWidth="1.5" fill="none" opacity="0.6" />
              <circle cx="180" cy="400" r="7" fill="#00d4ff" />
              <circle cx="180" cy="400" r="7" fill="none" stroke="#00d4ff" strokeWidth="1.5" opacity=".5">
                <animate attributeName="r" values="9;22;9" dur="3s" repeatCount="indefinite" />
                <animate attributeName="opacity" values=".55;0;.55" dur="3s" repeatCount="indefinite" />
              </circle>
            </svg>
          </div>

          <div className="relative z-10 max-w-md text-center">
            <div className="inline-block mb-3 px-3 py-1 rounded-full text-[10px] font-semibold tracking-widest uppercase"
              style={{ background: "rgba(0,212,255,0.1)", color: "#00d4ff", border: "1px solid rgba(0,212,255,0.25)" }}>
              Live · running now
            </div>
            <h2 className="text-2xl sm:text-3xl lg:text-4xl font-bold mb-3 leading-tight" style={{ color: "#e2e8f0", letterSpacing: "-0.02em" }}>
              See the agent build your offline pack
            </h2>
            <p className="text-sm sm:text-base mb-6 leading-relaxed" style={{ color: "#64748b" }}>
              Pick a route. Watch DeadZone detect where you&apos;ll lose signal and quietly gather what you&apos;ll need before you go dark.
            </p>
            <div className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl font-semibold text-sm tracking-wide transition-all duration-200 group-hover:translate-y-[-2px]"
              style={{
                background: "linear-gradient(135deg, #0891b2 0%, #00d4ff 100%)",
                color: "#050810",
                boxShadow: "0 8px 24px -8px rgba(0,212,255,0.4)",
              }}
            >
              Try it now
              <span className="transition-transform group-hover:translate-x-1">→</span>
            </div>
          </div>
        </button>

        {/* RIGHT — Coming to your phone */}
        <button
          onClick={onExploreMobile}
          className="flex-1 flex flex-col items-center justify-center px-8 py-6 group relative overflow-y-auto transition-all duration-300"
          style={{
            background: "linear-gradient(135deg, rgba(139,92,246,0.04) 0%, rgba(5,8,16,0) 100%)",
            cursor: "pointer",
            minHeight: 0,
          }}
        >
          <div className="relative z-10 max-w-md flex flex-col items-center text-center">
            <div className="inline-block mb-3 px-3 py-1 rounded-full text-[10px] font-semibold tracking-widest uppercase"
              style={{ background: "rgba(167,139,250,0.1)", color: "#c4b5fd", border: "1px solid rgba(167,139,250,0.25)" }}>
              Coming soon · join the list
            </div>
            <h2 className="text-2xl sm:text-3xl lg:text-4xl font-bold mb-3 leading-tight" style={{ color: "#e2e8f0", letterSpacing: "-0.02em" }}>
              Coming to your phone
            </h2>
            <p className="text-sm sm:text-base mb-5 leading-relaxed" style={{ color: "#64748b" }}>
              The full DeadZone app. Auto-detection, alerts before you go dark, contacts notified, content pre-fetched.
            </p>

            {/* Phone preview */}
            <div className="mb-3"
              style={{
                padding: 3,
                borderRadius: 31,
                background: "linear-gradient(135deg, rgba(0,212,255,0.18) 0%, rgba(167,139,250,0.22) 100%)",
                boxShadow: "0 0 40px -12px rgba(167,139,250,0.4)",
              }}
            >
              <PhoneFrame>
                <div
                  style={{
                    opacity: visible ? 1 : 0,
                    transition: `opacity ${FADE_MS}ms ease-in-out`,
                    height: "100%",
                  }}
                >
                  {current.node}
                </div>
              </PhoneFrame>
            </div>

            <div className="text-[11px] font-medium mb-4 tracking-wide" style={{ color: "#7dd3fc" }}>
              {current.label}
            </div>

            <div className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl font-semibold text-sm tracking-wide transition-all duration-200 group-hover:translate-y-[-2px]"
              style={{
                background: "linear-gradient(135deg, #7c3aed 0%, #a78bfa 100%)",
                color: "#fff",
                boxShadow: "0 8px 24px -8px rgba(167,139,250,0.4)",
              }}
            >
              See it on your phone
              <span className="transition-transform group-hover:translate-x-1">→</span>
            </div>
          </div>
        </button>
      </div>

      {/* Footer note */}
      <div className="text-center px-6 py-3 shrink-0" style={{ borderTop: "1px solid rgba(255,255,255,0.04)" }}>
        <p className="text-[10px] tracking-wide" style={{ color: "#334155" }}>
          Built at Agentic Engineering Hack · Datadog NYC 2026
        </p>
      </div>
    </div>
  );
}

/** Check if user has already dismissed the entry hero in this browser. */
export function hasDismissedEntry(): boolean {
  if (typeof window === "undefined") return true;
  try {
    return window.localStorage.getItem(FLAG_KEY) === "1";
  } catch {
    return true;
  }
}

/** Mark entry hero as dismissed so it never reappears for this browser. */
export function markEntryDismissed(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(FLAG_KEY, "1");
  } catch { /* ignore quota/privacy errors */ }
}
