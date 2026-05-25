"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

/* ─────────────────────────────────────────────────────────
   Scroll-triggered fade-in
───────────────────────────────────────────────────────── */
function useFadeIn(threshold = 0.12) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([e]) => { if (e.isIntersecting) setVisible(true); },
      { threshold }
    );
    io.observe(el);
    return () => io.disconnect();
  }, [threshold]);
  return { ref, visible };
}

/* ─────────────────────────────────────────────────────────
   Scroll arrow — brightens when in viewport, click jumps to
   next section using window.scrollTo (Next.js App Router safe)
───────────────────────────────────────────────────────── */
const NAV_HEIGHT = 62;

function ScrollArrow({ targetId }: { targetId: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([e]) => setInView(e.isIntersecting),
      { threshold: 0.6 }
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  function handleClick() {
    const target = document.getElementById(targetId);
    if (!target) return;
    const top = target.getBoundingClientRect().top + window.scrollY - NAV_HEIGHT;
    window.scrollTo({ top, behavior: "smooth" });
  }

  return (
    <div ref={ref} className="flex justify-center" style={{ padding: "3.5rem 0" }}>
      <button
        onClick={handleClick}
        aria-label="Scroll to next section"
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          padding: "0.75rem",
          opacity: inView ? 0.75 : 0.2,
          transition: "opacity 0.5s ease",
        }}
      >
        <svg
          width="34"
          height="34"
          viewBox="0 0 34 34"
          fill="none"
          className="animate-bounce"
        >
          <path
            d="M8 13l9 9 9-9"
            stroke="#94a3b8"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   Phone frame  (290 × 590)
───────────────────────────────────────────────────────── */
function Phone({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative mx-auto select-none" style={{ width: 290, height: 590 }}>
      <div
        className="absolute inset-0 overflow-hidden"
        style={{
          borderRadius: 50,
          background: "#0c0c18",
          border: "3px solid #252535",
          boxShadow:
            "0 0 0 1px #111, 0 40px 100px rgba(0,0,0,.9), inset 0 0 0 1px #2a2a3c",
        }}
      >
        <div
          className="absolute z-20"
          style={{
            top: 16, left: "50%", transform: "translateX(-50%)",
            width: 96, height: 26, background: "#000", borderRadius: 13,
          }}
        />
        <div className="absolute inset-0 overflow-hidden" style={{ paddingTop: 48 }}>
          {children}
        </div>
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            borderRadius: 50,
            background: "linear-gradient(135deg, rgba(255,255,255,.045) 0%, transparent 52%)",
          }}
        />
      </div>
      <div className="absolute rounded-l-sm" style={{ left: -4, top: 100, width: 3, height: 38, background: "#202030" }} />
      <div className="absolute rounded-l-sm" style={{ left: -4, top: 150, width: 3, height: 38, background: "#202030" }} />
      <div className="absolute rounded-r-sm" style={{ right: -4, top: 122, width: 3, height: 62, background: "#202030" }} />
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   Dashboard frame — landscape car infotainment screen
───────────────────────────────────────────────────────── */
function Dashboard({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative mx-auto select-none" style={{ width: 460, height: 272 }}>
      {/* outer bezel */}
      <div
        className="absolute inset-0 overflow-hidden"
        style={{
          borderRadius: 22,
          background: "#08080e",
          border: "4px solid #1e1e2e",
          boxShadow:
            "0 0 0 1px #0a0a14, 0 32px 80px rgba(0,0,0,.9), inset 0 0 0 1px #252535",
        }}
      >
        {children}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            borderRadius: 22,
            background: "linear-gradient(135deg, rgba(255,255,255,.03) 0%, transparent 48%)",
          }}
        />
      </div>
      {/* bottom mount stub */}
      <div
        className="absolute left-1/2 -translate-x-1/2"
        style={{ bottom: -18, width: 60, height: 18, background: "#111118", borderRadius: "0 0 6px 6px" }}
      />
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   Screen 1  GPS Auto-Detection
───────────────────────────────────────────────────────── */
function GPSScreen() {
  return (
    <div className="h-full flex flex-col" style={{ background: "#060b14", fontFamily: "'Space Grotesk', sans-serif" }}>
      <div className="flex justify-between px-4 pt-1 pb-1" style={{ fontSize: 11, color: "#555" }}>
        <span>9:41</span><span>●●● 87%</span>
      </div>
      <div className="relative mx-3 rounded-2xl overflow-hidden" style={{ background: "#0a1828", height: 218 }}>
        <svg className="absolute inset-0 w-full h-full">
          <polyline points="28,178 80,130 136,88 190,58 232,36"
            stroke="#00d4ff" strokeWidth="2.5" fill="none" strokeDasharray="5 3" opacity=".7" />
          <circle cx="232" cy="36" r="22" fill="#ef4444" opacity=".14" />
          <circle cx="232" cy="36" r="22" stroke="#ef4444" strokeWidth="1.5" fill="none" opacity=".7" />
          <circle cx="80" cy="130" r="5.5" fill="#00d4ff" />
          <circle cx="80" cy="130" r="5" fill="none" stroke="#00d4ff" strokeWidth="1.2" opacity=".5">
            <animate attributeName="r" values="8;18;8" dur="2.4s" repeatCount="indefinite" />
            <animate attributeName="opacity" values=".55;0;.55" dur="2.4s" repeatCount="indefinite" />
          </circle>
        </svg>
        <div className="absolute top-3 left-3 flex items-center gap-1.5" style={{ fontSize: 11, color: "#22c55e" }}>
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: "#22c55e", display: "inline-block" }} />
          Monitoring active
        </div>
        <div className="absolute top-3 right-3" style={{ fontSize: 11, color: "#475569" }}>Chicago to Detroit</div>
      </div>
      <div className="px-3 mt-3 space-y-2.5">
        <div className="rounded-2xl px-3.5 py-3 flex items-center gap-3" style={{ background: "#0d1e30" }}>
          <span style={{ fontSize: 22 }}>📍</span>
          <div>
            <div style={{ fontSize: 11, color: "#475569" }}>Running in background</div>
            <div style={{ fontSize: 14, color: "#e2e8f0", fontWeight: 600 }}>Route auto-detected</div>
          </div>
        </div>
        <div className="rounded-2xl px-3.5 py-3 flex items-center gap-3"
          style={{ background: "#180e0e", border: "1px solid #3f1515" }}>
          <span style={{ fontSize: 22 }}>⚠️</span>
          <div>
            <div style={{ fontSize: 11, color: "#f87171" }}>Dead zone ahead · 18 min</div>
            <div style={{ fontSize: 14, color: "#e2e8f0", fontWeight: 600 }}>Building your pack now…</div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   Screen 2  Dead Zone Countdown
───────────────────────────────────────────────────────── */
function NotificationScreen() {
  return (
    <div
      className="h-full flex flex-col items-center"
      style={{
        background: "linear-gradient(160deg, #090e1e 0%, #18082e 50%, #090e1e 100%)",
        fontFamily: "'Space Grotesk', sans-serif",
      }}
    >
      <div className="mt-12 text-center">
        <div style={{ fontSize: 60, fontWeight: 200, color: "#fff", lineHeight: 1 }}>10:47</div>
        <div style={{ fontSize: 13, color: "#64748b", marginTop: 6 }}>Tuesday, May 24</div>
      </div>
      <div
        className="absolute bottom-14 left-3 right-3 rounded-2xl p-3.5"
        style={{
          background: "rgba(14,16,30,.9)",
          backdropFilter: "blur(18px)",
          border: "1px solid rgba(255,255,255,.07)",
        }}
      >
        <div className="flex items-center gap-2 mb-2.5">
          <div className="w-8 h-8 rounded-xl flex items-center justify-center"
            style={{ background: "rgba(0,212,255,.1)", border: "1px solid rgba(0,212,255,.18)" }}>
            <span style={{ fontSize: 16 }}>📡</span>
          </div>
          <span style={{ fontSize: 12, color: "#64748b" }}>DeadZone</span>
          <span style={{ fontSize: 11, color: "#334155", marginLeft: "auto" }}>now</span>
        </div>
        <div style={{ fontSize: 14, color: "#f1f5f9", fontWeight: 700, marginBottom: 3 }}>
          Dead zone in 3 min
        </div>
        <div style={{ fontSize: 12, color: "#64748b" }}>
          Your offline pack is ready. Tap to view.
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   Screen 3  Contact Alerts (personalized messages)
───────────────────────────────────────────────────────── */
function ContactScreen() {
  const contacts = [
    { name: "Mom",       checked: true,  msg: "Hey Mom, going dark near [location]…" },
    { name: "Sarah K.",  checked: true,  msg: "Heading underground, back at [time]" },
    { name: "Marcus T.", checked: true,  msg: "Default message" },
    { name: "Work Chat", checked: false, msg: null },
    { name: "Jake P.",   checked: false, msg: null },
  ];
  return (
    <div className="h-full flex flex-col" style={{ background: "#060b14", fontFamily: "'Space Grotesk', sans-serif" }}>
      <div className="flex-1" style={{ background: "linear-gradient(180deg, #0d1a2a 0%, #060b14 100%)" }}>
        <div className="w-full h-full"
          style={{ background: "radial-gradient(circle at 65% 35%, rgba(0,212,255,.06), transparent)" }} />
      </div>
      <div className="rounded-t-3xl px-4 pt-3 pb-4" style={{ background: "#0e1420", border: "1px solid #1a2535" }}>
        <div className="w-9 h-1 rounded-full mx-auto mb-3" style={{ background: "#2a3044" }} />
        <div style={{ fontSize: 15, color: "#f1f5f9", fontWeight: 700, marginBottom: 2 }}>
          Notify before you go dark?
        </div>
        <div style={{ fontSize: 11, color: "#475569", marginBottom: 10 }}>
          5 people messaged in the last hour
        </div>
        <div className="space-y-2 mb-4">
          {contacts.map((c) => (
            <div key={c.name} className="flex items-start gap-3">
              <div
                className="flex-shrink-0 mt-0.5 w-4 h-4 rounded flex items-center justify-center"
                style={{
                  background: c.checked ? "#00d4ff" : "transparent",
                  border:     c.checked ? "none"    : "1.5px solid #334155",
                }}
              >
                {c.checked && <span style={{ fontSize: 9, color: "#000", fontWeight: 800 }}>✓</span>}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span style={{ fontSize: 13, color: c.checked ? "#e2e8f0" : "#334155" }}>{c.name}</span>
                  {c.checked && (
                    <span style={{ fontSize: 10, color: "#334155" }}>✏️</span>
                  )}
                </div>
                {c.msg && (
                  <div style={{ fontSize: 10, color: c.msg === "Default message" ? "#334155" : "#475569", marginTop: 1 }}
                    className="truncate">
                    {c.msg}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
        <div className="flex gap-2">
          <button className="flex-1 py-2 rounded-xl font-bold"
            style={{ background: "#00d4ff", color: "#000", fontSize: 12 }}>
            Notify 3 contacts
          </button>
          <button className="px-4 py-2 rounded-xl"
            style={{ background: "#1a2535", color: "#475569", fontSize: 12 }}>
            Skip
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   Screen 4  Traffic Detection
───────────────────────────────────────────────────────── */
function TrafficScreen() {
  return (
    <div className="h-full flex flex-col" style={{ background: "#060b14", fontFamily: "'Space Grotesk', sans-serif" }}>
      <div className="flex justify-between px-4 pt-1 pb-1" style={{ fontSize: 11, color: "#555" }}>
        <span>9:41</span><span>●●● 87%</span>
      </div>
      <div className="relative mx-3 rounded-2xl overflow-hidden" style={{ background: "#0a1828", height: 178 }}>
        <svg className="absolute inset-0 w-full h-full">
          <polyline points="20,148 62,120 106,104" stroke="#ef4444" strokeWidth="5" fill="none" opacity=".65" />
          <polyline points="106,104 154,72 206,44" stroke="#00d4ff" strokeWidth="2.5" fill="none" strokeDasharray="4 3" opacity=".5" />
          <polyline points="106,104 128,140 178,150 220,96 206,44" stroke="#22c55e" strokeWidth="2" fill="none" strokeDasharray="4 3" opacity=".55" />
          <circle cx="62" cy="120" r="5.5" fill="#00d4ff" />
        </svg>
        <div className="absolute top-3 left-3" style={{ fontSize: 11, color: "#f87171" }}>⚠ Heavy traffic · I-94 E</div>
        <div className="absolute bottom-3 right-3" style={{ fontSize: 11, color: "#22c55e" }}>Alt route →</div>
      </div>
      <div className="px-3 mt-3 space-y-2.5">
        <div className="rounded-2xl px-3.5 py-3 flex items-center justify-between" style={{ background: "#0d1e30" }}>
          <div>
            <div style={{ fontSize: 11, color: "#475569" }}>Current speed</div>
            <div style={{ fontSize: 28, color: "#ef4444", fontWeight: 700, lineHeight: 1.1 }}>8 mph</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 11, color: "#475569" }}>Dead zone ETA</div>
            <div style={{ fontSize: 22, color: "#f59e0b", fontWeight: 700 }}>9 min</div>
          </div>
        </div>
        <div className="rounded-2xl px-3.5 py-3" style={{ background: "#091a0f", border: "1px solid #142b1a" }}>
          <div style={{ fontSize: 12, color: "#22c55e", marginBottom: 3 }}>Alternate via I-90 E</div>
          <div style={{ fontSize: 13, color: "#e2e8f0", fontWeight: 600, marginBottom: 10 }}>
            Saves 14 min · dead zone ETA moves to 23 min
          </div>
          <div className="flex gap-2">
            <button className="px-4 py-1.5 rounded-lg font-bold"
              style={{ background: "#22c55e", color: "#000", fontSize: 12 }}>Reroute</button>
            <button className="px-4 py-1.5 rounded-lg"
              style={{ background: "#1a2535", color: "#475569", fontSize: 12 }}>Stay</button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   Screen 5  AI Content Pre-fetch
───────────────────────────────────────────────────────── */
function ContentScreen() {
  return (
    <div className="h-full flex flex-col items-center justify-center relative overflow-hidden"
      style={{ background: "#000", fontFamily: "'Space Grotesk', sans-serif" }}>
      <div className="absolute inset-0"
        style={{ background: "linear-gradient(180deg, #050510 0%, #080518 50%, #050510 100%)" }} />
      <div className="absolute top-4 right-4 flex items-center gap-1.5 px-2.5 py-1 rounded-full"
        style={{ background: "rgba(239,68,68,.1)", border: "1px solid rgba(239,68,68,.18)", fontSize: 11, color: "#f87171" }}>
        <span>📵</span><span>No Signal</span>
      </div>
      <div className="absolute inset-0 flex items-center justify-center"
        style={{ fontSize: 64, color: "rgba(255,255,255,.04)" }}>▶</div>
      <div className="relative z-10 mx-5 rounded-2xl p-5 text-center"
        style={{ background: "rgba(0,14,6,.92)", border: "1px solid rgba(34,197,94,.16)", backdropFilter: "blur(12px)" }}>
        <div style={{ fontSize: 13, color: "#22c55e", fontWeight: 700, marginBottom: 8 }}>
          Content pre-fetched
        </div>
        <div style={{ fontSize: 36, color: "#fff", fontWeight: 700, lineHeight: 1 }}>22 min</div>
        <div style={{ fontSize: 12, color: "#475569", marginBottom: 14 }}>staged for your 20-min tunnel</div>
        <div className="flex justify-center gap-4" style={{ fontSize: 12 }}>
          <span style={{ color: "#f97316" }}>4 reels</span>
          <span style={{ color: "#1e293b" }}>·</span>
          <span style={{ color: "#a78bfa" }}>3 articles</span>
          <span style={{ color: "#1e293b" }}>·</span>
          <span style={{ color: "#38bdf8" }}>1 episode</span>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   Screen 6  CarPlay  (landscape, rendered inside Dashboard)
───────────────────────────────────────────────────────── */
function CarPlayScreen() {
  const bars = [5, 10, 16, 8, 13, 9, 5, 14, 8, 11, 6, 15, 9, 12, 7];
  return (
    <div className="h-full flex" style={{ background: "#07070d", fontFamily: "'Space Grotesk', sans-serif" }}>
      {/* CarPlay top bar */}
      <div
        className="absolute top-0 left-0 right-0 z-10 flex items-center justify-between px-4 py-2"
        style={{ background: "rgba(7,7,13,.95)", borderBottom: "1px solid #111118", fontSize: 11, color: "#334155" }}
      >
        <span style={{ fontWeight: 600, color: "#475569" }}>Maps</span>
        <div className="flex items-center gap-3">
          <span style={{ color: "#22c55e", fontSize: 10 }}>● Connected</span>
          <span>9:41 AM</span>
        </div>
      </div>

      {/* map panel */}
      <div className="relative flex-1 overflow-hidden" style={{ marginTop: 32, background: "#09111e" }}>
        <svg className="absolute inset-0 w-full h-full">
          <polyline points="10,220 60,175 115,135 170,100 215,74"
            stroke="#00d4ff" strokeWidth="2.5" fill="none" strokeDasharray="5 3" opacity=".65" />
          <circle cx="215" cy="74" r="24" fill="#ef4444" opacity=".1" />
          <circle cx="215" cy="74" r="24" stroke="#ef4444" strokeWidth="1.5" fill="none" opacity=".55" />
          <circle cx="60" cy="175" r="5" fill="#00d4ff" />
          <circle cx="60" cy="175" r="5" fill="none" stroke="#00d4ff" strokeWidth="1">
            <animate attributeName="r" values="7;15;7" dur="2.2s" repeatCount="indefinite" />
            <animate attributeName="opacity" values=".5;0;.5" dur="2.2s" repeatCount="indefinite" />
          </circle>
        </svg>
        <div className="absolute bottom-3 left-3" style={{ fontSize: 11, color: "#334155" }}>
          Chicago to Detroit · I-94 E
        </div>
      </div>

      {/* alert panel */}
      <div
        className="flex flex-col justify-center px-5 py-5"
        style={{ width: 192, borderLeft: "1px solid #111118", background: "#08080e", marginTop: 32 }}
      >
        {/* countdown */}
        <div className="mb-5">
          <div className="flex items-center gap-1.5 mb-2">
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#ef4444", display: "inline-block" }}>
              <animate attributeName="opacity" values="1;0.3;1" dur="1.5s" repeatCount="indefinite" />
            </span>
            <span style={{ fontSize: 10, color: "#ef4444", fontWeight: 600, letterSpacing: "0.1em" }}>DEAD ZONE AHEAD</span>
          </div>
          <div style={{ fontSize: 44, color: "#fff", fontWeight: 200, lineHeight: 1 }}>2:45</div>
          <div style={{ fontSize: 11, color: "#334155", marginTop: 2 }}>minutes away</div>
        </div>

        {/* voice alert waveform */}
        <div className="mb-4">
          <div className="flex items-center gap-1.5 mb-2">
            <span style={{ fontSize: 12 }}>🔊</span>
            <span style={{ fontSize: 10, color: "#475569" }}>Voice alert</span>
          </div>
          <div className="flex items-end gap-0.5" style={{ height: 20 }}>
            {bars.map((h, i) => (
              <div
                key={i}
                style={{
                  width: 3,
                  height: h,
                  background: "#00d4ff",
                  borderRadius: 2,
                  opacity: 0.65,
                  animation: `waveBar 1.1s ease-in-out ${(i * 0.08).toFixed(2)}s infinite alternate`,
                }}
              />
            ))}
          </div>
        </div>

        {/* spoken line */}
        <div
          className="rounded-xl px-3 py-2.5 mb-3"
          style={{ background: "#0d1a10", border: "1px solid #142b1a" }}
        >
          <div style={{ fontSize: 10, color: "#334155", marginBottom: 3 }}>Speaking now</div>
          <div style={{ fontSize: 11, color: "#86efac", lineHeight: 1.5, fontStyle: "italic" }}>
            &ldquo;Dead zone in 3 minutes. Pack ready.&rdquo;
          </div>
        </div>

        {/* pack badge */}
        <div
          className="rounded-xl px-3 py-2 text-center"
          style={{ background: "rgba(0,212,255,.07)", border: "1px solid rgba(0,212,255,.15)" }}
        >
          <span style={{ fontSize: 12, color: "#00d4ff", fontWeight: 600 }}>Pack ready ✓</span>
        </div>
      </div>

      {/* waveform keyframe */}
      <style>{`
        @keyframes waveBar {
          from { transform: scaleY(0.3); opacity: 0.35; }
          to   { transform: scaleY(1);   opacity: 0.8;  }
        }
      `}</style>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   Feature data
───────────────────────────────────────────────────────── */
const FEATURES = [
  {
    num: "01",
    frame: "phone" as const,
    title: "GPS Auto-Detection",
    tagline: "It just knows.",
    description:
      "DeadZone runs silently in the background the moment you start moving. It reads your speed and heading, identifies your route from GPS data alone, and begins monitoring signal quality at every point ahead of you. No app to open. No destination to type in. By the time a dead zone appears on the horizon, your offline pack is already being assembled.",
    accent: "#00d4ff",
    screen: <GPSScreen />,
  },
  {
    num: "02",
    frame: "phone" as const,
    title: "Dead Zone Countdown",
    tagline: "A heads-up before you disappear.",
    description:
      "Three minutes before you lose signal, a notification appears on your lock screen. It confirms exactly how long the blackout lasts and tells you your offline pack is ready. You can tap to preview it, or ignore the notification entirely and keep driving. Either way, you arrive underground with everything already staged.",
    accent: "#a78bfa",
    screen: <NotificationScreen />,
  },
  {
    num: "03",
    frame: "phone" as const,
    title: "Contact Alerts",
    tagline: "Nobody wonders where you went.",
    description:
      "Before you go dark, DeadZone checks who you have been actively messaging and offers to send each of them a personalised update. Mom gets one message. Work gets another. You write each template once in settings, and DeadZone fills in the location and time automatically every time it fires. A checklist lets you choose who receives it, with a customisable time window from the last hour to the entire day. If signal drops before you act, it falls back to SMS automatically.",
    accent: "#00d4ff",
    screen: <ContactScreen />,
  },
  {
    num: "04",
    frame: "phone" as const,
    title: "Traffic Detection",
    tagline: "Your speed tells the whole story.",
    description:
      "Your phone already tracks your speed at every moment of the drive. When DeadZone detects you have slowed to a crawl, it immediately recalculates when you will reach the dead zone, adjusts the timing on your pack, and checks whether an alternate route would give you more signal time before you go underground. The suggestion surfaces before you have thought to look for one.",
    accent: "#22c55e",
    screen: <TrafficScreen />,
  },
  {
    num: "05",
    frame: "phone" as const,
    title: "AI Content Pre-fetch",
    tagline: "Never freeze on a reel mid-tunnel.",
    description:
      "The real problem with saving content offline is that you never know what you want until you want it. The most satisfying thing to watch on the subway is always something you have not seen before. DeadZone monitors what you are currently watching, reading, and listening to, then quietly stages the next stretch of fresh content before the signal drops. Reels keep playing. Articles open instantly. The podcast continues. You just stop noticing the tunnels.",
    accent: "#f97316",
    screen: <ContentScreen />,
  },
  {
    num: "06",
    frame: "carplay" as const,
    title: "CarPlay and Voice Alerts",
    tagline: "Hands on the wheel, ears on the road.",
    description:
      "DeadZone connects natively to your car through Apple CarPlay and Android Auto. The dead zone countdown appears directly on your dashboard display, updating in real time as your speed and traffic conditions change. Two minutes out, the car speaks the alert through the cabin speakers. No glancing at your phone. No tapping any screen. The pack confirmation plays as you enter the tunnel, and your eyes stay exactly where they should be.",
    accent: "#22c55e",
    screen: <CarPlayScreen />,
  },
] as const;

/* ─────────────────────────────────────────────────────────
   Feature row (alternating layout, phone or dashboard frame)
───────────────────────────────────────────────────────── */
function FeatureRow({
  feature,
  flip,
}: {
  feature: (typeof FEATURES)[number];
  flip: boolean;
}) {
  const { ref, visible } = useFadeIn();

  const mockup =
    feature.frame === "carplay" ? (
      <Dashboard>{feature.screen}</Dashboard>
    ) : (
      <Phone>{feature.screen}</Phone>
    );

  return (
    <div
      ref={ref}
      className={`flex flex-col items-center gap-14 lg:gap-24 transition-all duration-700
        ${visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-10"}
        ${flip && feature.frame !== "carplay" ? "lg:flex-row-reverse" : "lg:flex-row"}`}
    >
      <div className="flex-shrink-0">{mockup}</div>
      <div className="flex-1 text-center lg:text-left">
        <div className="text-xs font-mono mb-4" style={{ color: feature.accent, letterSpacing: "0.2em" }}>
          {feature.num}
        </div>
        <h2 className="text-4xl font-bold mb-4 leading-tight" style={{ letterSpacing: "-0.02em" }}>
          {feature.title}
        </h2>
        <p className="text-lg font-medium mb-6" style={{ color: feature.accent }}>
          {feature.tagline}
        </p>
        <p className="text-base leading-relaxed max-w-md mx-auto lg:mx-0" style={{ color: "#64748b" }}>
          {feature.description}
        </p>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   Page
───────────────────────────────────────────────────────── */
export default function MobilePage() {
  return (
    <main style={{ minHeight: "100vh", background: "#050810", fontFamily: "'Space Grotesk', sans-serif", color: "#e2e8f0" }}>

      {/* nav */}
      <nav
        className="sticky top-0 z-50 flex items-center justify-between px-6 py-4"
        style={{ borderBottom: "1px solid rgba(0,212,255,.06)", background: "rgba(5,8,16,.94)", backdropFilter: "blur(18px)" }}
      >
        <Link href="/" className="flex items-center gap-2 text-sm" style={{ color: "#475569" }}>
          <span>←</span><span>Back to app</span>
        </Link>
        <span className="text-sm font-semibold tracking-tight" style={{ color: "#00d4ff" }}>DeadZone</span>
        <div style={{ width: 88 }} />
      </nav>

      {/* hero */}
      <section id="hero" className="max-w-3xl mx-auto px-6 pt-24 pb-4 text-center">
        <div
          className="inline-flex items-center gap-2 px-3 py-1 rounded-full mb-10 text-xs font-medium"
          style={{ background: "rgba(167,139,250,.07)", border: "1px solid rgba(167,139,250,.18)", color: "#a78bfa" }}
        >
          <span>📱</span><span>Coming to iOS and Android</span>
        </div>
        <h1 className="text-5xl sm:text-6xl font-bold mb-8 leading-tight" style={{ letterSpacing: "-0.03em" }}>
          Six features.
          <br />
          <span style={{ color: "#00d4ff" }}>Zero signal required.</span>
        </h1>
        <p className="text-xl mx-auto" style={{ color: "#475569", lineHeight: 1.8, maxWidth: 500 }}>
          DeadZone on mobile becomes an ambient layer aware of where you are going,
          who you are talking to, and what you want to read before you go dark.
        </p>
      </section>

      {/* arrow: hero to first feature */}
      <ScrollArrow targetId="section-01" />

      {/* features */}
      <section className="max-w-5xl mx-auto px-6 pb-8">
        {FEATURES.map((f, i) => (
          <div key={f.num}>
            <div id={`section-${f.num}`} className="py-10">
              <FeatureRow feature={f} flip={i % 2 !== 0} />
            </div>
            {i < FEATURES.length - 1 && (
              <ScrollArrow targetId={`section-${FEATURES[i + 1].num}`} />
            )}
          </div>
        ))}
      </section>

      {/* footer */}
      <footer className="border-t text-center py-20" style={{ borderColor: "rgba(255,255,255,.04)" }}>
        <div
          className="inline-flex items-center gap-2 px-3 py-1 rounded-full mb-6 text-xs"
          style={{ background: "rgba(0,212,255,.05)", border: "1px solid rgba(0,212,255,.1)", color: "#00d4ff" }}
        >
          Built at Agentic Engineering Hack · Datadog NYC 2026
        </div>
        <p className="mb-8" style={{ color: "#1e293b", fontSize: 14 }}>The web demo is live. The phone is next.</p>
        <Link href="/" className="text-sm" style={{ color: "#00d4ff" }}>Try the live demo</Link>
      </footer>

    </main>
  );
}
