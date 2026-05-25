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
   Scroll arrow — click to jump to next section
───────────────────────────────────────────────────────── */
function ScrollArrow({ targetId }: { targetId: string }) {
  return (
    <div className="flex justify-center" style={{ padding: "3rem 0" }}>
      <button
        onClick={() =>
          document.getElementById(targetId)?.scrollIntoView({ behavior: "smooth", block: "start" })
        }
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          padding: "0.5rem",
          opacity: 0.28,
          transition: "opacity 0.25s",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.opacity = "0.72")}
        onMouseLeave={(e) => (e.currentTarget.style.opacity = "0.28")}
        aria-label="Scroll to next section"
      >
        <svg
          width="32"
          height="32"
          viewBox="0 0 32 32"
          fill="none"
          className="animate-bounce"
        >
          <path
            d="M7 12l9 9 9-9"
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
        {/* dynamic island */}
        <div
          className="absolute z-20"
          style={{
            top: 16,
            left: "50%",
            transform: "translateX(-50%)",
            width: 96,
            height: 26,
            background: "#000",
            borderRadius: 13,
          }}
        />
        {/* screen */}
        <div className="absolute inset-0 overflow-hidden" style={{ paddingTop: 48 }}>
          {children}
        </div>
        {/* glass glare */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            borderRadius: 50,
            background:
              "linear-gradient(135deg, rgba(255,255,255,.045) 0%, transparent 52%)",
          }}
        />
      </div>
      {/* volume */}
      <div className="absolute rounded-l-sm" style={{ left: -4, top: 100, width: 3, height: 38, background: "#202030" }} />
      <div className="absolute rounded-l-sm" style={{ left: -4, top: 150, width: 3, height: 38, background: "#202030" }} />
      {/* power */}
      <div className="absolute rounded-r-sm" style={{ right: -4, top: 122, width: 3, height: 62, background: "#202030" }} />
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
      {/* map */}
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
      {/* cards */}
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
      {/* notification */}
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
   Screen 3  Smart Contact Alerts
───────────────────────────────────────────────────────── */
function ContactScreen() {
  const contacts = [
    { name: "Mom",       checked: true  },
    { name: "Sarah K.",  checked: true  },
    { name: "Marcus T.", checked: true  },
    { name: "Work Chat", checked: false },
    { name: "Jake P.",   checked: false },
  ];
  return (
    <div className="h-full flex flex-col" style={{ background: "#060b14", fontFamily: "'Space Grotesk', sans-serif" }}>
      <div className="flex-1" style={{ background: "linear-gradient(180deg, #0d1a2a 0%, #060b14 100%)" }}>
        <div className="w-full h-full"
          style={{ background: "radial-gradient(circle at 65% 35%, rgba(0,212,255,.06), transparent)" }} />
      </div>
      {/* bottom sheet */}
      <div className="rounded-t-3xl px-4 pt-3 pb-5" style={{ background: "#0e1420", border: "1px solid #1a2535" }}>
        <div className="w-9 h-1 rounded-full mx-auto mb-4" style={{ background: "#2a3044" }} />
        <div style={{ fontSize: 15, color: "#f1f5f9", fontWeight: 700, marginBottom: 3 }}>
          Notify before you go dark?
        </div>
        <div style={{ fontSize: 12, color: "#475569", marginBottom: 12 }}>
          You messaged 5 people in the last hour
        </div>
        <div className="space-y-2.5 mb-4">
          {contacts.map((c) => (
            <div key={c.name} className="flex items-center gap-3">
              <div
                className="flex-shrink-0 w-4 h-4 rounded flex items-center justify-center"
                style={{
                  background: c.checked ? "#00d4ff" : "transparent",
                  border:     c.checked ? "none"    : "1.5px solid #334155",
                }}
              >
                {c.checked && <span style={{ fontSize: 9, color: "#000", fontWeight: 800 }}>✓</span>}
              </div>
              <span style={{ fontSize: 13, color: c.checked ? "#e2e8f0" : "#334155" }}>{c.name}</span>
            </div>
          ))}
        </div>
        <div className="flex items-center gap-2 mb-4">
          <span style={{ fontSize: 12, color: "#475569" }}>Time window:</span>
          <span className="px-2 py-0.5 rounded-lg"
            style={{ background: "#1a2535", color: "#64748b", fontSize: 12 }}>
            Last hour ▾
          </span>
        </div>
        <div className="flex gap-2">
          <button className="flex-1 py-2.5 rounded-xl font-bold"
            style={{ background: "#00d4ff", color: "#000", fontSize: 13 }}>
            Notify 3 contacts
          </button>
          <button className="px-4 py-2.5 rounded-xl"
            style={{ background: "#1a2535", color: "#475569", fontSize: 13 }}>
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
      {/* map */}
      <div className="relative mx-3 rounded-2xl overflow-hidden" style={{ background: "#0a1828", height: 178 }}>
        <svg className="absolute inset-0 w-full h-full">
          <polyline points="20,148 62,120 106,104"
            stroke="#ef4444" strokeWidth="5" fill="none" opacity=".65" />
          <polyline points="106,104 154,72 206,44"
            stroke="#00d4ff" strokeWidth="2.5" fill="none" strokeDasharray="4 3" opacity=".5" />
          <polyline points="106,104 128,140 178,150 220,96 206,44"
            stroke="#22c55e" strokeWidth="2" fill="none" strokeDasharray="4 3" opacity=".55" />
          <circle cx="62" cy="120" r="5.5" fill="#00d4ff" />
        </svg>
        <div className="absolute top-3 left-3" style={{ fontSize: 11, color: "#f87171" }}>⚠ Heavy traffic · I-94 E</div>
        <div className="absolute bottom-3 right-3" style={{ fontSize: 11, color: "#22c55e" }}>Alt route →</div>
      </div>
      {/* info */}
      <div className="px-3 mt-3 space-y-2.5">
        <div className="rounded-2xl px-3.5 py-3 flex items-center justify-between"
          style={{ background: "#0d1e30" }}>
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
    <div
      className="h-full flex flex-col items-center justify-center relative overflow-hidden"
      style={{ background: "#000", fontFamily: "'Space Grotesk', sans-serif" }}
    >
      <div className="absolute inset-0"
        style={{ background: "linear-gradient(180deg, #050510 0%, #080518 50%, #050510 100%)" }} />
      {/* no signal */}
      <div
        className="absolute top-4 right-4 flex items-center gap-1.5 px-2.5 py-1 rounded-full"
        style={{
          background: "rgba(239,68,68,.1)",
          border: "1px solid rgba(239,68,68,.18)",
          fontSize: 11, color: "#f87171",
        }}
      >
        <span>📵</span><span>No Signal</span>
      </div>
      {/* ghost play icon */}
      <div className="absolute inset-0 flex items-center justify-center"
        style={{ fontSize: 64, color: "rgba(255,255,255,.04)" }}>▶</div>
      {/* card */}
      <div
        className="relative z-10 mx-5 rounded-2xl p-5 text-center"
        style={{
          background: "rgba(0,14,6,.92)",
          border: "1px solid rgba(34,197,94,.16)",
          backdropFilter: "blur(12px)",
        }}
      >
        <div style={{ fontSize: 13, color: "#22c55e", fontWeight: 700, marginBottom: 8 }}>
          Content pre-fetched
        </div>
        <div style={{ fontSize: 36, color: "#fff", fontWeight: 700, lineHeight: 1 }}>22 min</div>
        <div style={{ fontSize: 12, color: "#475569", marginBottom: 14 }}>
          staged for your 20-min tunnel
        </div>
        <div className="flex justify-center gap-4" style={{ fontSize: 12 }}>
          <span style={{ color: "#f97316" }}>4 reels</span>
          <span style={{ color: "#1e293b" }}>·</span>
          <span style={{ color: "#a78bfa" }}>3 articles</span>
          <span style={{ color: "#1e293b" }}>·</span>
          <span style={{ color: "#38bdf8" }}>1 episode</span>
        </div>
      </div>
      <div className="absolute bottom-5 left-0 right-0 text-center"
        style={{ fontSize: 11, color: "#0f172a" }}>
        feed continues as if you never lost signal
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   Screen 6  SMS Fallback
───────────────────────────────────────────────────────── */
function SMSScreen() {
  return (
    <div className="h-full flex flex-col" style={{ background: "#08080f", fontFamily: "'Space Grotesk', sans-serif" }}>
      <div className="px-4 pt-2 pb-3" style={{ borderBottom: "1px solid #111820" }}>
        <div style={{ fontSize: 12, color: "#334155", marginBottom: 2 }}>Messages</div>
        <div style={{ fontSize: 16, color: "#f1f5f9", fontWeight: 600 }}>Mom</div>
      </div>
      {/* thread */}
      <div className="flex-1 px-4 pt-5 flex flex-col justify-end pb-3">
        {/* incoming */}
        <div className="mb-4 self-start" style={{ maxWidth: "72%" }}>
          <div className="rounded-2xl rounded-tl-sm px-3.5 py-2.5"
            style={{ background: "#1a1a2a", fontSize: 13, color: "#cbd5e1" }}>
            Are you almost here?
          </div>
          <div style={{ fontSize: 10, color: "#1e293b", marginTop: 3, marginLeft: 4 }}>3:47 PM</div>
        </div>
        {/* auto-sent */}
        <div className="self-end" style={{ maxWidth: "84%" }}>
          <div
            className="rounded-2xl rounded-tr-sm px-3.5 py-3"
            style={{
              background: "rgba(0,212,255,.07)",
              border: "1px solid rgba(0,212,255,.16)",
              fontSize: 13,
              color: "#e2e8f0",
              lineHeight: 1.5,
            }}
          >
            Going dark near Lincoln Tunnel. Back around 5:42pm.
          </div>
          <div className="flex items-center justify-end gap-2 mt-2">
            <span style={{ fontSize: 10, color: "rgba(0,212,255,.4)" }}>Sent by DeadZone</span>
            <span style={{ fontSize: 10, color: "#1e293b" }}>Delivered</span>
          </div>
        </div>
      </div>
      {/* SOS */}
      <div
        className="flex items-center justify-center gap-2 py-3"
        style={{ borderTop: "1px solid #0f0f1a", fontSize: 12, color: "#7f1d1d" }}
      >
        <span>📵</span><span>SOS Only</span>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   Feature data
───────────────────────────────────────────────────────── */
const FEATURES = [
  {
    num: "01",
    title: "GPS Auto-Detection",
    tagline: "It just knows.",
    description:
      "DeadZone runs silently in the background the moment you start moving. It reads your speed and heading, identifies your route from GPS data alone, and begins monitoring signal quality at every point ahead of you. No app to open. No destination to type in. By the time a dead zone appears on the horizon, your offline pack is already being assembled.",
    accent: "#00d4ff",
    screen: <GPSScreen />,
  },
  {
    num: "02",
    title: "Dead Zone Countdown",
    tagline: "A heads-up before you disappear.",
    description:
      "Three minutes before you lose signal, a notification appears on your lock screen. It confirms exactly how long the blackout lasts and tells you your offline pack is ready. You can tap to preview it, or ignore the notification entirely and keep driving. Either way, you arrive underground with everything already staged.",
    accent: "#a78bfa",
    screen: <NotificationScreen />,
  },
  {
    num: "03",
    title: "Smart Contact Alerts",
    tagline: "Nobody wonders where you went.",
    description:
      "Going dark mid-conversation is one of the most frustrating parts of losing signal. DeadZone checks who you have been actively messaging and, before you go underground, offers to send them a quick update. Choose from a checklist of recent contacts, set a custom time window from the last hour to the entire day, or keep a permanent list of people who should always be notified. One tap handles all of them.",
    accent: "#00d4ff",
    screen: <ContactScreen />,
  },
  {
    num: "04",
    title: "Traffic Detection",
    tagline: "Your speed tells the whole story.",
    description:
      "Your phone already tracks your speed at every moment of the drive. When DeadZone detects you have slowed to a crawl, it immediately recalculates when you will reach the dead zone, adjusts the timing on your pack, and checks whether an alternate route would give you more signal time before you go underground. The suggestion surfaces before you have thought to look for one.",
    accent: "#22c55e",
    screen: <TrafficScreen />,
  },
  {
    num: "05",
    title: "AI Content Pre-fetch",
    tagline: "Never freeze on a reel mid-tunnel.",
    description:
      "The real problem with saving content offline is that you never know what you want until you want it. The most satisfying thing to watch on the subway is always something you have not seen before. DeadZone monitors what you are currently watching, reading, and listening to, then quietly stages the next stretch of fresh content before the signal drops. Reels keep playing. Articles open instantly. The podcast continues. You just stop noticing the tunnels.",
    accent: "#f97316",
    screen: <ContentScreen />,
  },
  {
    num: "06",
    title: "SMS Fallback",
    tagline: "Last resort. Fully automatic.",
    description:
      "Data and LTE vanish deep underground, but SMS survives at signal levels where nothing else can reach. When DeadZone detects a complete data outage, it automatically sends a short message to anyone you were recently in contact with, letting them know you are temporarily unreachable and giving them an estimated time you will be back. No input needed. When you surface, your conversations pick up exactly where they left off.",
    accent: "#ec4899",
    screen: <SMSScreen />,
  },
] as const;

/* ─────────────────────────────────────────────────────────
   Feature row (alternating layout)
───────────────────────────────────────────────────────── */
function FeatureRow({
  feature,
  flip,
}: {
  feature: (typeof FEATURES)[number];
  flip: boolean;
}) {
  const { ref, visible } = useFadeIn();
  return (
    <div
      ref={ref}
      className={`flex flex-col items-center gap-14 lg:gap-24 transition-all duration-700
        ${visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-10"}
        ${flip ? "lg:flex-row-reverse" : "lg:flex-row"}`}
    >
      <div className="flex-shrink-0">
        <Phone>{feature.screen}</Phone>
      </div>
      <div className="flex-1 text-center lg:text-left">
        <div
          className="text-xs font-mono mb-4"
          style={{ color: feature.accent, letterSpacing: "0.2em" }}
        >
          {feature.num}
        </div>
        <h2
          className="text-4xl font-bold mb-4 leading-tight"
          style={{ letterSpacing: "-0.02em" }}
        >
          {feature.title}
        </h2>
        <p className="text-lg font-medium mb-6" style={{ color: feature.accent }}>
          {feature.tagline}
        </p>
        <p
          className="text-base leading-relaxed max-w-md mx-auto lg:mx-0"
          style={{ color: "#64748b" }}
        >
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
    <main
      style={{
        minHeight: "100vh",
        background: "#050810",
        fontFamily: "'Space Grotesk', sans-serif",
        color: "#e2e8f0",
      }}
    >
      {/* nav */}
      <nav
        className="sticky top-0 z-50 flex items-center justify-between px-6 py-4"
        style={{
          borderBottom: "1px solid rgba(0,212,255,.06)",
          background: "rgba(5,8,16,.94)",
          backdropFilter: "blur(18px)",
        }}
      >
        <Link
          href="/"
          className="flex items-center gap-2 text-sm"
          style={{ color: "#475569", transition: "color .2s" }}
        >
          <span>←</span>
          <span>Back to app</span>
        </Link>
        <span className="text-sm font-semibold tracking-tight" style={{ color: "#00d4ff" }}>
          DeadZone
        </span>
        <div style={{ width: 88 }} />
      </nav>

      {/* hero */}
      <section
        id="hero"
        className="max-w-3xl mx-auto px-6 pt-24 pb-4 text-center"
      >
        <div
          className="inline-flex items-center gap-2 px-3 py-1 rounded-full mb-10 text-xs font-medium"
          style={{
            background: "rgba(167,139,250,.07)",
            border: "1px solid rgba(167,139,250,.18)",
            color: "#a78bfa",
          }}
        >
          <span>📱</span>
          <span>Coming to iOS and Android</span>
        </div>
        <h1
          className="text-5xl sm:text-6xl font-bold mb-8 leading-tight"
          style={{ letterSpacing: "-0.03em" }}
        >
          Six features.
          <br />
          <span style={{ color: "#00d4ff" }}>Zero signal required.</span>
        </h1>
        <p
          className="text-xl mx-auto"
          style={{ color: "#475569", lineHeight: 1.8, maxWidth: 500 }}
        >
          DeadZone on mobile becomes an ambient layer — aware of where you are going,
          who you are talking to, and what you want to read before you go dark.
        </p>
      </section>

      {/* arrow from hero to first feature */}
      <ScrollArrow targetId="section-01" />

      {/* feature rows */}
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
      <footer
        className="border-t text-center py-20"
        style={{ borderColor: "rgba(255,255,255,.04)" }}
      >
        <div
          className="inline-flex items-center gap-2 px-3 py-1 rounded-full mb-6 text-xs"
          style={{
            background: "rgba(0,212,255,.05)",
            border: "1px solid rgba(0,212,255,.1)",
            color: "#00d4ff",
          }}
        >
          Built at Agentic Engineering Hack · Datadog NYC 2026
        </div>
        <p className="mb-8" style={{ color: "#1e293b", fontSize: 14 }}>
          The web demo is live. The phone is next.
        </p>
        <Link
          href="/"
          className="text-sm"
          style={{ color: "#00d4ff" }}
        >
          Try the live demo
        </Link>
      </footer>
    </main>
  );
}
