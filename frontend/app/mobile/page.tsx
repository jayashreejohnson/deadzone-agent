"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

/* ─────────────────────────────────────────────────────────
   Scroll-triggered fade-in hook
───────────────────────────────────────────────────────── */
function useFadeIn(threshold = 0.15) {
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
   Phone frame wrapper
───────────────────────────────────────────────────────── */
function Phone({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative mx-auto select-none" style={{ width: 256, height: 524 }}>
      {/* outer shell */}
      <div
        className="absolute inset-0 overflow-hidden"
        style={{
          borderRadius: 44,
          background: "#0c0c18",
          border: "3px solid #252535",
          boxShadow:
            "0 0 0 1px #111, 0 32px 80px rgba(0,0,0,.85), inset 0 0 0 1px #2a2a3c",
        }}
      >
        {/* dynamic island */}
        <div
          className="absolute z-20"
          style={{
            top: 14, left: "50%", transform: "translateX(-50%)",
            width: 88, height: 24, background: "#000", borderRadius: 12,
          }}
        />
        {/* screen */}
        <div className="absolute inset-0 overflow-hidden" style={{ paddingTop: 44 }}>
          {children}
        </div>
        {/* glass glare */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            borderRadius: 44,
            background: "linear-gradient(135deg, rgba(255,255,255,.04) 0%, transparent 50%)",
          }}
        />
      </div>
      {/* volume buttons */}
      <div className="absolute rounded-l-sm" style={{ left: -4, top: 90,  width: 3, height: 34, background: "#202030" }} />
      <div className="absolute rounded-l-sm" style={{ left: -4, top: 134, width: 3, height: 34, background: "#202030" }} />
      {/* power button */}
      <div className="absolute rounded-r-sm" style={{ right: -4, top: 108, width: 3, height: 56, background: "#202030" }} />
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   Screen 1 — GPS Auto-Detection
───────────────────────────────────────────────────────── */
function GPSScreen() {
  return (
    <div className="h-full flex flex-col" style={{ background: "#060b14", fontFamily: "'Space Grotesk', sans-serif" }}>
      <div className="flex justify-between px-4 pt-1 pb-1" style={{ fontSize: 10, color: "#666" }}>
        <span>9:41</span><span>●●● 87%</span>
      </div>
      {/* mini map */}
      <div className="relative mx-3 rounded-2xl overflow-hidden" style={{ background: "#0a1828", height: 190 }}>
        <svg className="absolute inset-0 w-full h-full">
          {/* route line */}
          <polyline points="28,158 75,118 128,82 180,54 218,34"
            stroke="#00d4ff" strokeWidth="2.5" fill="none" strokeDasharray="5 3" opacity=".7" />
          {/* dead zone */}
          <circle cx="218" cy="34" r="20" fill="#ef4444" opacity=".15" />
          <circle cx="218" cy="34" r="20" stroke="#ef4444" strokeWidth="1.5" fill="none" opacity=".7" />
          {/* position dot + pulse */}
          <circle cx="75" cy="118" r="5" fill="#00d4ff" />
          <circle cx="75" cy="118" r="5" fill="none" stroke="#00d4ff" strokeWidth="1" opacity=".5">
            <animate attributeName="r" values="7;16;7" dur="2.2s" repeatCount="indefinite" />
            <animate attributeName="opacity" values=".6;0;.6" dur="2.2s" repeatCount="indefinite" />
          </circle>
        </svg>
        <div className="absolute top-2.5 left-3 flex items-center gap-1.5" style={{ fontSize: 10, color: "#22c55e" }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#22c55e", display: "inline-block" }} />
          Monitoring active
        </div>
        <div className="absolute top-2.5 right-3" style={{ fontSize: 10, color: "#64748b" }}>Chicago → Detroit</div>
      </div>
      {/* cards */}
      <div className="px-3 mt-3 space-y-2">
        <div className="rounded-2xl px-3 py-2.5 flex items-center gap-3"
          style={{ background: "#0d1e30" }}>
          <span style={{ fontSize: 20 }}>📍</span>
          <div>
            <div style={{ fontSize: 10, color: "#64748b" }}>Background · no battery drain</div>
            <div style={{ fontSize: 13, color: "#e2e8f0", fontWeight: 600 }}>Route auto-detected</div>
          </div>
        </div>
        <div className="rounded-2xl px-3 py-2.5 flex items-center gap-3"
          style={{ background: "#180e0e", border: "1px solid #3f1515" }}>
          <span style={{ fontSize: 20 }}>⚠️</span>
          <div>
            <div style={{ fontSize: 10, color: "#f87171" }}>Dead zone · 18 min away</div>
            <div style={{ fontSize: 13, color: "#e2e8f0", fontWeight: 600 }}>Building your pack now…</div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   Screen 2 — Push Notification (lock screen)
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
      <div className="mt-10 text-center">
        <div style={{ fontSize: 54, fontWeight: 200, color: "#fff", lineHeight: 1 }}>10:47</div>
        <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 4 }}>Tuesday, May 24</div>
      </div>
      {/* notification card */}
      <div
        className="absolute bottom-14 left-3 right-3 rounded-2xl p-3"
        style={{
          background: "rgba(15,18,32,.88)",
          backdropFilter: "blur(16px)",
          border: "1px solid rgba(255,255,255,.07)",
        }}
      >
        <div className="flex items-center gap-2 mb-2">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center"
            style={{ background: "rgba(0,212,255,.12)", border: "1px solid rgba(0,212,255,.2)" }}>
            <span style={{ fontSize: 14 }}>📡</span>
          </div>
          <span style={{ fontSize: 11, color: "#94a3b8" }}>DeadZone</span>
          <span style={{ fontSize: 10, color: "#475569", marginLeft: "auto" }}>now</span>
        </div>
        <div style={{ fontSize: 13, color: "#f1f5f9", fontWeight: 700, marginBottom: 2 }}>
          Dead zone in 3 min
        </div>
        <div style={{ fontSize: 12, color: "#94a3b8" }}>
          Your offline pack is ready ✓ — tap to view
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   Screen 3 — Smart Contact Alerts
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
        <div className="w-full h-full opacity-20"
          style={{ background: "radial-gradient(circle at 65% 35%, #00d4ff30, transparent)" }} />
      </div>
      {/* bottom sheet */}
      <div className="rounded-t-3xl px-4 pt-3 pb-4" style={{ background: "#0e1420", border: "1px solid #1a2535" }}>
        <div className="w-8 h-1 rounded-full mx-auto mb-3" style={{ background: "#2a3044" }} />
        <div style={{ fontSize: 15, color: "#f1f5f9", fontWeight: 700, marginBottom: 2 }}>Notify before you go dark?</div>
        <div style={{ fontSize: 11, color: "#64748b", marginBottom: 10 }}>Messaged 5 people in the last hour</div>
        <div className="space-y-2 mb-4">
          {contacts.map((c) => (
            <div key={c.name} className="flex items-center gap-2.5">
              <div
                className="flex-shrink-0 w-4 h-4 rounded flex items-center justify-center"
                style={{
                  background:  c.checked ? "#00d4ff"                      : "transparent",
                  border:      c.checked ? "none"                          : "1.5px solid #334155",
                }}
              >
                {c.checked && <span style={{ fontSize: 9, color: "#000", fontWeight: 800 }}>✓</span>}
              </div>
              <span style={{ fontSize: 13, color: c.checked ? "#e2e8f0" : "#475569" }}>{c.name}</span>
            </div>
          ))}
        </div>
        {/* time window */}
        <div className="flex items-center gap-2 mb-3">
          <span style={{ fontSize: 11, color: "#64748b" }}>Time window:</span>
          <span className="px-2 py-0.5 rounded-lg" style={{ background: "#1a2535", color: "#94a3b8", fontSize: 11 }}>Last hour ▾</span>
        </div>
        <div className="flex gap-2">
          <button className="flex-1 py-2 rounded-xl font-bold"
            style={{ background: "#00d4ff", color: "#000", fontSize: 12 }}>
            Notify 3 contacts
          </button>
          <button className="px-4 py-2 rounded-xl"
            style={{ background: "#1a2535", color: "#64748b", fontSize: 12 }}>
            Skip
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   Screen 4 — Traffic Detection
───────────────────────────────────────────────────────── */
function TrafficScreen() {
  return (
    <div className="h-full flex flex-col" style={{ background: "#060b14", fontFamily: "'Space Grotesk', sans-serif" }}>
      <div className="flex justify-between px-4 pt-1 pb-1" style={{ fontSize: 10, color: "#666" }}>
        <span>9:41</span><span>●●● 87%</span>
      </div>
      {/* mini map */}
      <div className="relative mx-3 rounded-2xl overflow-hidden" style={{ background: "#0a1828", height: 156 }}>
        <svg className="absolute inset-0 w-full h-full">
          {/* congested segment */}
          <polyline points="20,130 58,108 98,96" stroke="#ef4444" strokeWidth="5" fill="none" opacity=".6" />
          {/* normal route */}
          <polyline points="98,96 148,66 198,40" stroke="#00d4ff" strokeWidth="2.5" fill="none" strokeDasharray="4 3" opacity=".5" />
          {/* alternate */}
          <polyline points="98,96 118,128 168,138 210,88 198,40" stroke="#22c55e" strokeWidth="2" fill="none" strokeDasharray="4 3" opacity=".55" />
          <circle cx="58" cy="108" r="5" fill="#00d4ff" />
        </svg>
        <div className="absolute top-2 left-3" style={{ fontSize: 10, color: "#f87171" }}>⚠ Heavy traffic · I-94 E</div>
        <div className="absolute bottom-2 right-3" style={{ fontSize: 10, color: "#22c55e" }}>Alt route →</div>
      </div>
      {/* speed + reroute */}
      <div className="px-3 mt-3 space-y-2">
        <div className="rounded-2xl px-3 py-2.5 flex items-center justify-between"
          style={{ background: "#0d1e30" }}>
          <div>
            <div style={{ fontSize: 10, color: "#64748b" }}>Current speed</div>
            <div style={{ fontSize: 26, color: "#ef4444", fontWeight: 700, lineHeight: 1.1 }}>8 mph</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 10, color: "#64748b" }}>Dead zone ETA</div>
            <div style={{ fontSize: 20, color: "#f59e0b", fontWeight: 700 }}>9 min</div>
          </div>
        </div>
        <div className="rounded-2xl px-3 py-2.5" style={{ background: "#091a0f", border: "1px solid #142b1a" }}>
          <div style={{ fontSize: 11, color: "#22c55e", marginBottom: 2 }}>Alternate via I-90 E</div>
          <div style={{ fontSize: 12, color: "#e2e8f0", fontWeight: 600, marginBottom: 8 }}>
            Saves 14 min · dead zone ETA jumps to 23 min
          </div>
          <div className="flex gap-2">
            <button className="px-3 py-1 rounded-lg font-bold"
              style={{ background: "#22c55e", color: "#000", fontSize: 11 }}>Reroute</button>
            <button className="px-3 py-1 rounded-lg"
              style={{ background: "#1a2535", color: "#64748b", fontSize: 11 }}>Stay</button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   Screen 5 — AI Content Pre-fetch
───────────────────────────────────────────────────────── */
function ContentScreen() {
  return (
    <div className="h-full flex flex-col items-center justify-center relative overflow-hidden"
      style={{ background: "#000", fontFamily: "'Space Grotesk', sans-serif" }}>
      <div className="absolute inset-0"
        style={{ background: "linear-gradient(180deg, #050510 0%, #080515 50%, #050510 100%)" }} />
      {/* no signal badge */}
      <div className="absolute top-3 right-4 flex items-center gap-1.5 px-2 py-1 rounded-full"
        style={{ background: "rgba(239,68,68,.12)", border: "1px solid rgba(239,68,68,.2)", fontSize: 10, color: "#f87171" }}>
        <span>📵</span><span>No Signal</span>
      </div>
      {/* reel playing indicator */}
      <div className="absolute inset-0 flex items-center justify-center"
        style={{ fontSize: 56, color: "rgba(255,255,255,.06)" }}>▶</div>
      {/* pre-fetch card */}
      <div
        className="relative z-10 mx-4 rounded-2xl p-4 text-center"
        style={{
          background: "rgba(0,16,8,.92)",
          border: "1px solid rgba(34,197,94,.18)",
          backdropFilter: "blur(10px)",
        }}
      >
        <div style={{ fontSize: 13, color: "#22c55e", fontWeight: 700, marginBottom: 6 }}>
          ✓  Content pre-fetched
        </div>
        <div style={{ fontSize: 32, color: "#fff", fontWeight: 700, lineHeight: 1 }}>22 min</div>
        <div style={{ fontSize: 11, color: "#64748b", marginBottom: 12 }}>staged for your 20-min tunnel</div>
        <div className="flex justify-center gap-4" style={{ fontSize: 11 }}>
          <span style={{ color: "#f97316" }}>4 reels</span>
          <span style={{ color: "#333" }}>·</span>
          <span style={{ color: "#a78bfa" }}>3 articles</span>
          <span style={{ color: "#333" }}>·</span>
          <span style={{ color: "#38bdf8" }}>1 episode</span>
        </div>
      </div>
      <div className="absolute bottom-4 left-0 right-0 text-center"
        style={{ fontSize: 10, color: "#1e293b" }}>
        feed continues as if you never lost signal
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   Screen 6 — SMS Fallback
───────────────────────────────────────────────────────── */
function SMSScreen() {
  return (
    <div className="h-full flex flex-col" style={{ background: "#08080f", fontFamily: "'Space Grotesk', sans-serif" }}>
      {/* messages header */}
      <div className="px-4 pt-2 pb-3" style={{ borderBottom: "1px solid #111820" }}>
        <div style={{ fontSize: 11, color: "#475569", marginBottom: 1 }}>← Messages</div>
        <div style={{ fontSize: 15, color: "#f1f5f9", fontWeight: 600 }}>Mom</div>
      </div>
      {/* thread */}
      <div className="flex-1 px-4 pt-4 flex flex-col justify-end pb-2">
        {/* incoming */}
        <div className="mb-3 self-start" style={{ maxWidth: "72%" }}>
          <div className="rounded-2xl rounded-tl-sm px-3 py-2"
            style={{ background: "#1a1a2a", fontSize: 12, color: "#cbd5e1" }}>
            Are you almost here?
          </div>
          <div style={{ fontSize: 10, color: "#334155", marginTop: 3, marginLeft: 4 }}>3:47 PM</div>
        </div>
        {/* auto-sent */}
        <div className="self-end" style={{ maxWidth: "82%" }}>
          <div className="rounded-2xl rounded-tr-sm px-3 py-2.5"
            style={{
              background: "rgba(0,212,255,.08)",
              border: "1px solid rgba(0,212,255,.18)",
              fontSize: 12,
              color: "#e2e8f0",
              lineHeight: 1.45,
            }}>
            Going dark near Lincoln Tunnel — back around 5:42pm.
          </div>
          <div className="flex items-center justify-end gap-2 mt-1.5">
            <span style={{ fontSize: 9, color: "rgba(0,212,255,.5)" }}>Sent by DeadZone</span>
            <span style={{ fontSize: 10, color: "#334155" }}>Delivered ✓</span>
          </div>
        </div>
      </div>
      {/* SOS indicator */}
      <div className="flex items-center justify-center gap-1.5 py-3"
        style={{ borderTop: "1px solid #111820", fontSize: 11, color: "#ef4444" }}>
        <span>📵</span><span>SOS Only — no data</span>
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
      "DeadZone runs silently in the background. The moment you start moving, it detects your route, monitors signal strength ahead, and starts building your pack — no tapping, no setup.",
    accent: "#00d4ff",
    screen: <GPSScreen />,
  },
  {
    num: "02",
    title: "Dead Zone Countdown",
    tagline: "A heads-up before you disappear.",
    description:
      "A lock screen notification lands while you still have full signal. Your pack is already built and waiting. You go underground knowing you're covered.",
    accent: "#a78bfa",
    screen: <NotificationScreen />,
  },
  {
    num: "03",
    title: "Smart Contact Alerts",
    tagline: "Nobody wonders where you went.",
    description:
      "Before you go dark, DeadZone checks who you've been talking to and asks if you'd like to let them know. A checklist, a customisable time window, and a hardcoded list for the people who matter most.",
    accent: "#00d4ff",
    screen: <ContactScreen />,
  },
  {
    num: "04",
    title: "Traffic Detection",
    tagline: "Your speed tells the whole story.",
    description:
      "Phone sensors detect when you're crawling. Dead zone ETAs recalculate in real time, and faster alternate routes surface automatically — all before you've thought to check.",
    accent: "#22c55e",
    screen: <TrafficScreen />,
  },
  {
    num: "05",
    title: "AI Content Pre-fetch",
    tagline: "Never freeze on a reel mid-tunnel.",
    description:
      "Four minutes before you lose signal, DeadZone stages the next 20 minutes of your feed — fresh reels, articles you'd actually read, the next podcast episode. You didn't save anything. You didn't have to.",
    accent: "#f97316",
    screen: <ContentScreen />,
  },
  {
    num: "06",
    title: "SMS Fallback",
    tagline: "Last resort. Fully automatic.",
    description:
      "When data drops completely, critical messages go out via SMS — the one protocol that survives anything. No action needed from you. You emerge, your phone already handled it.",
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
      className={`flex flex-col items-center gap-12 lg:gap-20 transition-all duration-700
        ${visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-10"}
        ${flip ? "lg:flex-row-reverse" : "lg:flex-row"}`}
    >
      {/* phone */}
      <div className="flex-shrink-0">
        <Phone>{feature.screen}</Phone>
      </div>
      {/* text */}
      <div className="flex-1 text-center lg:text-left">
        <div
          className="text-xs font-mono tracking-[0.2em] mb-4"
          style={{ color: feature.accent }}
        >
          {feature.num}
        </div>
        <h2
          className="text-3xl sm:text-4xl font-bold mb-3 leading-tight"
          style={{ letterSpacing: "-0.02em" }}
        >
          {feature.title}
        </h2>
        <p className="text-lg font-medium mb-5" style={{ color: feature.accent }}>
          {feature.tagline}
        </p>
        <p className="text-base leading-relaxed max-w-md mx-auto lg:mx-0" style={{ color: "#94a3b8" }}>
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
          borderBottom: "1px solid rgba(0,212,255,.07)",
          background: "rgba(5,8,16,.92)",
          backdropFilter: "blur(16px)",
        }}
      >
        <Link
          href="/"
          className="flex items-center gap-2 text-sm transition-colors"
          style={{ color: "#64748b" }}
        >
          <span>←</span>
          <span>Back to app</span>
        </Link>
        <span className="text-sm font-semibold tracking-tight" style={{ color: "#00d4ff" }}>
          DeadZone
        </span>
        {/* spacer keeps title centred */}
        <div style={{ width: 88 }} />
      </nav>

      {/* hero */}
      <section className="max-w-3xl mx-auto px-6 pt-24 pb-28 text-center">
        <div
          className="inline-flex items-center gap-2 px-3 py-1 rounded-full mb-8 text-xs font-medium"
          style={{
            background: "rgba(167,139,250,.08)",
            border: "1px solid rgba(167,139,250,.2)",
            color: "#a78bfa",
          }}
        >
          <span>📱</span>
          <span>Coming to iOS &amp; Android</span>
        </div>
        <h1
          className="text-5xl sm:text-6xl font-bold mb-6 leading-tight"
          style={{ letterSpacing: "-0.03em" }}
        >
          Six features.
          <br />
          <span style={{ color: "#00d4ff" }}>Zero signal required.</span>
        </h1>
        <p
          className="text-xl mx-auto"
          style={{ color: "#64748b", lineHeight: 1.75, maxWidth: 480 }}
        >
          DeadZone on mobile becomes an ambient layer — aware of where you&apos;re
          going, who you&apos;re talking to, and what you want to read before you go dark.
        </p>
      </section>

      {/* feature rows */}
      <section className="max-w-5xl mx-auto px-6 pb-36 space-y-36">
        {FEATURES.map((f, i) => (
          <FeatureRow key={f.num} feature={f} flip={i % 2 !== 0} />
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
            background: "rgba(0,212,255,.06)",
            border: "1px solid rgba(0,212,255,.12)",
            color: "#00d4ff",
          }}
        >
          Built at Agentic Engineering Hack · Datadog NYC 2026
        </div>
        <p className="mb-6" style={{ color: "#334155", fontSize: 14 }}>
          The web demo is live. The phone is next.
        </p>
        <Link
          href="/"
          className="text-sm transition-colors"
          style={{ color: "#00d4ff" }}
        >
          ← Try the live demo
        </Link>
      </footer>
    </main>
  );
}
