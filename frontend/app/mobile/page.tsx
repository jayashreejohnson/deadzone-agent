"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

/* ── Fade-in ─────────────────────────────────────────────── */
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

/* ── Scroll arrow — lives inside each panel at the bottom ── */
const NAV_H = 62;

function ScrollArrow({ targetId }: { targetId: string }) {
  function jump() {
    const container = document.getElementById("snap-container");
    const t = document.getElementById(targetId);
    if (!container || !t) return;
    container.scrollTo({
      top: container.scrollTop + t.getBoundingClientRect().top - container.getBoundingClientRect().top - NAV_H,
      behavior: "smooth",
    });
  }

  return (
    <div className="flex justify-center" style={{ padding: "12px 0 28px" }}>
      <button
        onClick={jump}
        aria-label="Next section"
        style={{
          background: "rgba(148,163,184,0.07)",
          border: "1px solid rgba(148,163,184,0.15)",
          borderRadius: "50%",
          cursor: "pointer",
          padding: "0.65rem",
          opacity: 0.8,
          transition: "opacity 0.2s ease, transform 0.2s ease",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          width: 48,
          height: 48,
        }}
      >
        <svg width="24" height="24" viewBox="0 0 34 34" fill="none" className="animate-bounce">
          <path d="M8 13l9 9 9-9" stroke="#94a3b8" strokeWidth="2.5"
            strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
    </div>
  );
}

/* ── Mobile phone wrapper — scales full-size phone to 75% ── */
// Renders Phone at its native 560px (so all screen content looks identical
// to desktop) then shrinks it via CSS transform. No squashing.
const MOBILE_SCALE = 0.75;
const MOBILE_PHONE_W = Math.round(290 * MOBILE_SCALE); // 218
const MOBILE_PHONE_H = Math.round(560 * MOBILE_SCALE); // 420

function MobilePhone({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ width: MOBILE_PHONE_W, height: MOBILE_PHONE_H, position: "relative", flexShrink: 0 }}>
      <div style={{ position: "absolute", top: 0, left: 0, transformOrigin: "top left", transform: `scale(${MOBILE_SCALE})` }}>
        <Phone height={560}>{children}</Phone>
      </div>
    </div>
  );
}

/* ── Phone frame — height-aware ──────────────────────────── */
function Phone({ children, height = 560 }: { children: React.ReactNode; height?: number }) {
  const sc = height / 590;
  const w  = Math.round(290 * sc);
  return (
    <div className="relative mx-auto select-none" style={{ width: w, height }}>
      <div
        className="absolute inset-0 overflow-hidden"
        style={{
          borderRadius: Math.round(50 * sc),
          background: "#0c0c18",
          border: "3px solid #252535",
          boxShadow: "0 0 0 1px #111, 0 40px 100px rgba(0,0,0,.9), inset 0 0 0 1px #2a2a3c",
        }}
      >
        <div className="absolute z-20"
          style={{ top: 16, left: "50%", transform: "translateX(-50%)",
            width: Math.round(96 * sc), height: 26, background: "#000", borderRadius: 13 }} />
        <div className="absolute inset-0 overflow-hidden" style={{ paddingTop: 48 }}>
          {children}
        </div>
        <div className="absolute inset-0 pointer-events-none"
          style={{ borderRadius: Math.round(50 * sc),
            background: "linear-gradient(135deg, rgba(255,255,255,.045) 0%, transparent 52%)" }} />
      </div>
      <div className="absolute rounded-l-sm"
        style={{ left: -4, top: Math.round(100 * sc), width: 3, height: Math.round(38 * sc), background: "#202030" }} />
      <div className="absolute rounded-l-sm"
        style={{ left: -4, top: Math.round(150 * sc), width: 3, height: Math.round(38 * sc), background: "#202030" }} />
      <div className="absolute rounded-r-sm"
        style={{ right: -4, top: Math.round(122 * sc), width: 3, height: Math.round(62 * sc), background: "#202030" }} />
    </div>
  );
}

/* ── CarPlay head-unit frame ─────────────────────────────── */
function CarPlayFrame() {
  return (
    <div className="select-none" style={{
      width: 310,
      borderRadius: 10,
      overflow: "hidden",
      border: "3px solid #252535",
      boxShadow: "0 0 0 1px #111, 0 32px 80px rgba(0,0,0,.9), inset 0 0 0 1px #2a2a3c",
      fontFamily: "'Space Grotesk', sans-serif",
    }}>

      {/* ── Status bar ── */}
      <div className="flex items-center justify-between px-3 py-1.5"
        style={{ background: "#060a14", borderBottom: "1px solid rgba(255,255,255,.04)", fontSize: 10 }}>
        <span style={{ color: "#475569", fontWeight: 600 }}>10:47</span>
        <span style={{ color: "#334155" }}>Chicago → Detroit · I-94</span>
        <span style={{ color: "#475569" }}>●●○</span>
      </div>

      {/* ── Map ── */}
      <div className="relative" style={{ height: 118, background: "#0a1422" }}>
        <svg className="absolute inset-0" width="310" height="118" viewBox="0 0 310 118">
          {/* highway body */}
          <path d="M 0 76 Q 80 73 155 70 Q 230 67 310 60"
            stroke="#1a2d42" strokeWidth="20" fill="none" />
          {/* centre line */}
          <path d="M 0 76 Q 80 73 155 70 Q 230 67 310 60"
            stroke="#243d5c" strokeWidth="1.5" fill="none" strokeDasharray="12 8" opacity=".7" />
          {/* dead-zone glow */}
          <circle cx="240" cy="65" r="16" fill="rgba(239,68,68,.1)" />
          <circle cx="240" cy="65" r="6"  fill="#ef4444" opacity=".85" />
          {/* dotted path: current → dead zone */}
          <path d="M 90 74 Q 165 70 240 65"
            stroke="#00d4ff" strokeWidth="1.5" fill="none" strokeDasharray="5 4" opacity=".5" />
          {/* current position */}
          <circle cx="90" cy="74" r="5.5" fill="#00d4ff" />
          <circle cx="90" cy="74" r="10"  fill="none" stroke="#00d4ff" strokeWidth="1.5" opacity=".3" />
        </svg>
        <div className="absolute top-2 left-2 flex items-center gap-1 px-2 py-0.5 rounded-full"
          style={{ background: "rgba(239,68,68,.13)", border: "1px solid rgba(239,68,68,.28)",
            fontSize: 9, color: "#f87171" }}>
          ⚠ Dead zone · exit 218 · 18 mi
        </div>
        <div className="absolute bottom-2 right-2"
          style={{ fontSize: 9, color: "#334155" }}>I-94 E</div>
      </div>

      {/* ── Countdown ── */}
      <div className="flex items-center gap-3 px-3 py-3"
        style={{ background: "rgba(167,139,250,.07)",
          borderTop: "1px solid rgba(167,139,250,.1)",
          borderBottom: "1px solid rgba(167,139,250,.1)" }}>
        <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ background: "rgba(167,139,250,.14)", border: "1px solid rgba(167,139,250,.22)" }}>
          <span style={{ fontSize: 22 }}>📡</span>
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 10, color: "#a78bfa", fontWeight: 600, marginBottom: 1 }}>Dead zone in</div>
          <div style={{ fontSize: 32, color: "#fff", fontWeight: 700, lineHeight: 1 }}>3:00</div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 10, color: "#22c55e", marginBottom: 2 }}>Pack ready</div>
          <div style={{ fontSize: 18, color: "#22c55e", fontWeight: 700 }}>✓</div>
        </div>
      </div>

      {/* ── Voice + media controls ── */}
      <div className="flex items-center gap-2 px-3 py-2.5"
        style={{ background: "#070b15" }}>
        <span style={{ fontSize: 15 }}>🔊</span>
        <span style={{ fontSize: 9, color: "#475569", flex: 1, fontStyle: "italic", lineHeight: 1.4 }}>
          "Dead zone in 3 minutes. Your offline pack is ready."
        </span>
        <div className="flex items-center gap-2">
          {["⏮", "▶", "⏭"].map((ic, i) => (
            <div key={ic} className="flex items-center justify-center rounded-lg"
              style={{ width: 24, height: 24, background: "#0d1420",
                fontSize: 11, color: i === 1 ? "#00d4ff" : "#334155" }}>
              {ic}
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}

/* ── Screen 1 — GPS Auto-Detection ───────────────────────── */
function GPSScreen() {
  return (
    <div className="h-full flex flex-col" style={{ background: "#060b14", fontFamily: "'Space Grotesk', sans-serif" }}>
      <div className="flex justify-between px-4 pt-1 pb-1" style={{ fontSize: 11, color: "#555" }}>
        <span>9:41</span><span>●●● 87%</span>
      </div>
      <div className="relative mx-3 rounded-2xl overflow-hidden" style={{ background: "#0a1828", height: 200 }}>
        <svg className="absolute inset-0 w-full h-full">
          <polyline points="28,168 80,122 136,82 190,52 232,32"
            stroke="#00d4ff" strokeWidth="2.5" fill="none" strokeDasharray="5 3" opacity=".7" />
          <circle cx="232" cy="32" r="20" fill="#ef4444" opacity=".14" />
          <circle cx="232" cy="32" r="20" stroke="#ef4444" strokeWidth="1.5" fill="none" opacity=".7" />
          <circle cx="80" cy="122" r="5.5" fill="#00d4ff" />
          <circle cx="80" cy="122" r="5" fill="none" stroke="#00d4ff" strokeWidth="1.2" opacity=".5">
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

/* ── Screen 2 — Countdown (phone half of the dual panel) ─── */
function CountdownScreen() {
  return (
    <div className="h-full flex flex-col items-center relative"
      style={{ background: "linear-gradient(160deg, #090e1e 0%, #18082e 50%, #090e1e 100%)", fontFamily: "'Space Grotesk', sans-serif" }}>
      <div className="mt-10 text-center">
        <div style={{ fontSize: 56, fontWeight: 200, color: "#fff", lineHeight: 1 }}>10:47</div>
        <div style={{ fontSize: 12, color: "#64748b", marginTop: 5 }}>Tuesday, May 24</div>
      </div>
      <div className="absolute bottom-28 left-3 right-3 rounded-2xl p-3.5"
        style={{ background: "rgba(14,16,30,.9)", backdropFilter: "blur(18px)", border: "1px solid rgba(255,255,255,.07)" }}>
        <div className="flex items-center gap-2 mb-2">
          <div className="w-8 h-8 rounded-xl flex items-center justify-center"
            style={{ background: "rgba(0,212,255,.1)", border: "1px solid rgba(0,212,255,.18)" }}>
            <span style={{ fontSize: 16 }}>📡</span>
          </div>
          <span style={{ fontSize: 12, color: "#64748b" }}>DeadZone</span>
          <span style={{ fontSize: 11, color: "#334155", marginLeft: "auto" }}>now</span>
        </div>
        <div style={{ fontSize: 14, color: "#f1f5f9", fontWeight: 700, marginBottom: 3 }}>Dead zone in 3 min</div>
        <div style={{ fontSize: 12, color: "#64748b" }}>Your offline pack is ready. Tap to view.</div>
      </div>
      <div className="absolute bottom-10 left-3 right-3 flex gap-2 justify-center">
        {[{ icon: "📱", label: "Lock screen" }, { icon: "🚗", label: "CarPlay" },
          { icon: "🔊", label: "Voice" }, { icon: "⌚", label: "Watch" }].map((s) => (
          <div key={s.label} className="flex items-center gap-1 px-2 py-1 rounded-lg"
            style={{ background: "rgba(0,212,255,.06)", border: "1px solid rgba(0,212,255,.12)", fontSize: 10, color: "#64748b" }}>
            <span>{s.icon}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Screen 3 — Contact Alerts ───────────────────────────── */
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
        <div className="flex items-center gap-2 mb-3 px-2 py-1.5 rounded-xl"
          style={{ background: "#0a1a10", border: "1px solid #142b1a" }}>
          <span style={{ fontSize: 13 }}>📍</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 11, color: "#22c55e", fontWeight: 600 }}>Location pinned</div>
            <div style={{ fontSize: 10, color: "#334155" }}>Times Square, New York · shared with message</div>
          </div>
        </div>
        <div style={{ fontSize: 14, color: "#f1f5f9", fontWeight: 700, marginBottom: 2 }}>Notify before you go dark?</div>
        <div style={{ fontSize: 11, color: "#475569", marginBottom: 10 }}>5 people messaged in the last hour</div>
        <div className="space-y-2 mb-4">
          {contacts.map((c) => (
            <div key={c.name} className="flex items-start gap-3">
              <div className="flex-shrink-0 mt-0.5 w-4 h-4 rounded flex items-center justify-center"
                style={{ background: c.checked ? "#00d4ff" : "transparent", border: c.checked ? "none" : "1.5px solid #334155" }}>
                {c.checked && <span style={{ fontSize: 9, color: "#000", fontWeight: 800 }}>✓</span>}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span style={{ fontSize: 13, color: c.checked ? "#e2e8f0" : "#334155" }}>{c.name}</span>
                  {c.checked && <span style={{ fontSize: 10, color: "#334155" }}>✏️</span>}
                </div>
                {c.msg && (
                  <div className="truncate"
                    style={{ fontSize: 10, color: c.msg === "Default message" ? "#334155" : "#475569", marginTop: 1 }}>
                    {c.msg}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
        <div className="flex gap-2">
          <button className="flex-1 py-2 rounded-xl font-bold"
            style={{ background: "#00d4ff", color: "#000", fontSize: 12 }}>Notify 3 contacts</button>
          <button className="px-4 py-2 rounded-xl"
            style={{ background: "#1a2535", color: "#475569", fontSize: 12 }}>Skip</button>
        </div>
      </div>
    </div>
  );
}

/* ── Screen 4 — Traffic + Offline Maps ───────────────────── */
function TrafficScreen() {
  return (
    <div className="h-full flex flex-col" style={{ background: "#060b14", fontFamily: "'Space Grotesk', sans-serif" }}>
      <div className="flex justify-between px-4 pt-1 pb-1" style={{ fontSize: 11, color: "#555" }}>
        <span>9:41</span><span>●●● 87%</span>
      </div>
      <div className="relative mx-3 rounded-2xl overflow-hidden" style={{ background: "#0a1828", height: 148 }}>
        <svg className="absolute inset-0 w-full h-full">
          <polyline points="20,120 62,96 106,82" stroke="#ef4444" strokeWidth="5" fill="none" opacity=".65" />
          <polyline points="106,82 154,56 206,30" stroke="#00d4ff" strokeWidth="2.5" fill="none" strokeDasharray="4 3" opacity=".5" />
          <polyline points="106,82 128,114 178,124 220,76 206,30" stroke="#22c55e" strokeWidth="2" fill="none" strokeDasharray="4 3" opacity=".55" />
          <circle cx="62" cy="96" r="5.5" fill="#00d4ff" />
        </svg>
        <div className="absolute top-3 left-3" style={{ fontSize: 11, color: "#f87171" }}>⚠ Heavy traffic · I-94 E</div>
        <div className="absolute bottom-3 right-3" style={{ fontSize: 11, color: "#22c55e" }}>Alt route →</div>
      </div>
      <div className="px-3 mt-2 space-y-2">
        <div className="rounded-2xl px-3.5 py-2.5 flex items-center justify-between" style={{ background: "#0d1e30" }}>
          <div>
            <div style={{ fontSize: 11, color: "#475569" }}>Current speed</div>
            <div style={{ fontSize: 24, color: "#ef4444", fontWeight: 700, lineHeight: 1.1 }}>8 mph</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 11, color: "#475569" }}>Dead zone ETA</div>
            <div style={{ fontSize: 20, color: "#f59e0b", fontWeight: 700 }}>9 min</div>
          </div>
        </div>
        <div className="rounded-2xl px-3.5 py-2.5" style={{ background: "#091a0f", border: "1px solid #142b1a" }}>
          <div style={{ fontSize: 12, color: "#22c55e", marginBottom: 2 }}>Alternate via I-90 E</div>
          <div style={{ fontSize: 12, color: "#e2e8f0", fontWeight: 600, marginBottom: 8 }}>
            Saves 14 min · dead zone ETA moves to 23 min
          </div>
          <div className="flex gap-2">
            <button className="px-4 py-1.5 rounded-lg font-bold"
              style={{ background: "#22c55e", color: "#000", fontSize: 12 }}>Reroute</button>
            <button className="px-4 py-1.5 rounded-lg"
              style={{ background: "#1a2535", color: "#475569", fontSize: 12 }}>Stay</button>
          </div>
        </div>
        <div className="rounded-2xl px-3.5 py-2.5 flex items-center gap-3"
          style={{ background: "#0d1020", border: "1px solid #1a1a35" }}>
          <span style={{ fontSize: 18 }}>🗺</span>
          <div>
            <div style={{ fontSize: 11, color: "#a78bfa" }}>Offline map downloading</div>
            <div style={{ fontSize: 12, color: "#e2e8f0", fontWeight: 600 }}>12 mi ahead cached · nav stays live</div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Screen 5 — AI Content Pre-fetch ─────────────────────── */
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
        <div style={{ fontSize: 13, color: "#22c55e", fontWeight: 700, marginBottom: 8 }}>Content pre-fetched</div>
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

/* ── Screen 6 — Seamless Re-emergence ────────────────────── */
function SeamlessScreen() {
  const events = [
    { icon: "💬", label: "3 messages delivered",            color: "#a78bfa" },
    { icon: "✉️", label: "\"I'm back\" sent to 3 contacts", color: "#00d4ff" },
    { icon: "🗺",  label: "Navigation resumed",              color: "#22c55e" },
    { icon: "🎧", label: "Podcast resumed · 24:18",          color: "#f97316" },
    { icon: "📰", label: "Articles refreshed to live",       color: "#38bdf8" },
  ];
  return (
    <div className="h-full flex flex-col" style={{ background: "#060b14", fontFamily: "'Space Grotesk', sans-serif" }}>
      <div className="flex justify-between px-4 pt-1 pb-1" style={{ fontSize: 11, color: "#555" }}>
        <span>9:49</span><span>●●● 87%</span>
      </div>
      <div className="mx-3 rounded-2xl px-4 py-3 mb-2"
        style={{ background: "#091a0f", border: "1px solid #14301a" }}>
        <div className="flex items-center gap-2 mb-1">
          <div className="flex items-end gap-0.5" style={{ height: 14 }}>
            {[4, 7, 10, 13].map((h, i) => (
              <div key={i} style={{ width: 3, height: h, background: "#22c55e", borderRadius: 1, opacity: 0.9 }} />
            ))}
          </div>
          <span style={{ fontSize: 13, color: "#22c55e", fontWeight: 700 }}>Signal restored</span>
        </div>
        <div style={{ fontSize: 11, color: "#334155" }}>You were offline for 8 min 32 sec</div>
      </div>
      <div className="px-3 space-y-1.5">
        <div style={{ fontSize: 11, color: "#334155", marginBottom: 4, paddingLeft: 2 }}>Syncing automatically…</div>
        {events.map((e) => (
          <div key={e.label} className="rounded-xl px-3 py-2 flex items-center gap-3"
            style={{ background: "#0d1420" }}>
            <span style={{ fontSize: 16 }}>{e.icon}</span>
            <span style={{ fontSize: 12, color: "#cbd5e1", flex: 1 }}>{e.label}</span>
            <span style={{ fontSize: 13, color: e.color, fontWeight: 700 }}>✓</span>
          </div>
        ))}
      </div>
      <div className="mt-auto mx-3 mb-3 rounded-xl px-3 py-2.5 text-center"
        style={{ background: "rgba(0,212,255,.05)", border: "1px solid rgba(0,212,255,.12)" }}>
        <span style={{ fontSize: 12, color: "#00d4ff", fontWeight: 600 }}>
          Back online · everything caught up
        </span>
      </div>
    </div>
  );
}

/* ── Feature data ────────────────────────────────────────── */
type Feature = {
  num: string;
  title: string;
  tagline: string;
  description: string;
  accent: string;
  screen: React.ReactNode;
  extraFrame?: React.ReactNode;
};

const FEATURES: Feature[] = [
  {
    num: "01",
    title: "GPS Auto-Detection",
    tagline: "It just knows.",
    description:
      "DeadZone runs silently in the background the moment you start moving. It reads your speed and heading, identifies your route from GPS data alone, and begins monitoring signal quality at every point ahead of you. No app to open. No destination to type in. By the time a dead zone appears on the horizon, your offline pack is already being assembled behind the scenes, ready before you ever feel the signal drop.",
    accent: "#00d4ff",
    screen: <GPSScreen />,
  },
  {
    num: "02",
    title: "Dead Zone Countdown",
    tagline: "Every surface. At the right moment.",
    description:
      "Three minutes before you lose signal, DeadZone reaches every screen you have with you. Your phone lock screen confirms the blackout duration and that your pack is ready. CarPlay and Android Auto show the same live countdown while your cabin speakers announce it aloud so your hands stay on the wheel. An Apple Watch tap gives you one last moment before you go dark. None of this requires you to touch anything.",
    accent: "#a78bfa",
    screen: <CountdownScreen />,
    extraFrame: <CarPlayFrame />,
  },
  {
    num: "03",
    title: "Contact Alerts",
    tagline: "Nobody wonders where you went.",
    description:
      "Before you go underground, DeadZone handles the two things that matter most when you disappear mid-conversation. First, it checks who you have been actively messaging and offers to send each of them a personalised update. You write your message templates once in settings and forget about them. Mom gets one message, your partner gets another, and work gets the professional version. DeadZone fills in your exact location and estimated return time automatically, every single time it fires. Second, it drops a precise GPS location pin to your selected contacts the instant before signal drops. If you do not act before the dead zone arrives, DeadZone falls back to SMS automatically, because SMS reaches signal levels where data simply cannot.",
    accent: "#00d4ff",
    screen: <ContactScreen />,
  },
  {
    num: "04",
    title: "Traffic Detection",
    tagline: "Reroutes you above. Navigates you below.",
    description:
      "Your phone already knows your speed at every moment of the drive. When DeadZone detects you have slowed to a crawl, it immediately recalculates your dead zone ETA, adjusts the timing of your pack build, and checks whether an alternate route would give you more signal window. At the same time, DeadZone downloads the map tiles covering the next stretch of your route while you still have data. When you enter the dead zone, your navigation does not freeze. The blue dot keeps moving, turn-by-turn directions continue, and your position tracks accurately at zero signal.",
    accent: "#22c55e",
    screen: <TrafficScreen />,
  },
  {
    num: "05",
    title: "AI Content Pre-fetch",
    tagline: "Never freeze on a reel mid-tunnel.",
    description:
      "The real problem with saving content offline is that you never know what you want until you want it. DeadZone monitors what you are currently watching, reading, and listening to, then quietly stages the next stretch of fresh content before the signal drops. Reels keep playing. Articles open instantly. Your podcast continues from exactly where it was. You did not save anything. You did not have to. You just stop noticing the tunnels.",
    accent: "#f97316",
    screen: <ContentScreen />,
  },
  {
    num: "06",
    title: "Seamless Return",
    tagline: "The app never looked like it stopped.",
    description:
      "Everything else on this page is about going dark. Seamless Return is about what happens when you come back. The moment your phone detects signal, DeadZone triggers a quiet, automatic sequence. Messages that queued deliver instantly. A short confirmation goes to everyone you notified. Your navigation session resumes from your current position. Your podcast picks up from the exact second it paused. Articles refresh to their live versions. There is no moment of catching up, no backlog to sort through. You surface and everything is already where it should be.",
    accent: "#00d4ff",
    screen: <SeamlessScreen />,
  },
];

/* ── Desktop feature row (lg+ only) ─────────────────────── */
function FeatureRow({ feature, flip }: { feature: Feature; flip: boolean }) {
  const { ref, visible } = useFadeIn();
  const hasExtra = !!feature.extraFrame;
  return (
    <div
      ref={ref}
      className={`transition-all duration-700 ${visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-10"}`}
    >
      <div className={`flex items-center gap-20 ${flip ? "flex-row-reverse" : "flex-row"}`}>
        <div className={`flex-shrink-0 ${hasExtra ? "flex flex-row items-center gap-4" : ""}`}>
          <Phone height={hasExtra ? 490 : 560}>{feature.screen}</Phone>
          {hasExtra && <div className="self-center">{feature.extraFrame}</div>}
        </div>
        <div className="flex-1 text-left">
          <div className="text-xs font-mono mb-4" style={{ color: feature.accent, letterSpacing: "0.2em" }}>
            {feature.num}
          </div>
          <h2 className="text-4xl font-bold mb-4 leading-tight" style={{ letterSpacing: "-0.02em" }}>
            {feature.title}
          </h2>
          <p className="text-lg font-medium mb-6" style={{ color: feature.accent }}>
            {feature.tagline}
          </p>
          <p className="text-base leading-relaxed max-w-md" style={{ color: "#64748b" }}>
            {feature.description}
          </p>
        </div>
      </div>
    </div>
  );
}

/* ── Page ────────────────────────────────────────────────── */
export default function MobilePage() {
  const PANEL_H = `calc(100vh - ${NAV_H}px)`;

  return (
    <div
      id="snap-container"
      style={{
        height: "100vh",
        overflowY: "scroll",
        scrollSnapType: "y mandatory",
        scrollPaddingTop: NAV_H,
        background: "#050810",
        fontFamily: "'Space Grotesk', sans-serif",
        color: "#e2e8f0",
      }}
    >
      {/* Nav — sticky inside the snap container */}
      <nav className="sticky top-0 z-50 flex items-center justify-between px-6 py-4"
        style={{ height: NAV_H, borderBottom: "1px solid rgba(0,212,255,.06)", background: "rgba(5,8,16,.94)", backdropFilter: "blur(18px)" }}>
        <Link href="/" className="flex items-center gap-2 text-sm" style={{ color: "#475569" }}>
          <span>←</span><span>Back to app</span>
        </Link>
        <span className="text-sm font-semibold tracking-tight" style={{ color: "#00d4ff" }}>DeadZone</span>
        <div style={{ width: 88 }} />
      </nav>

      {/* Hero */}
      <section id="hero" className="flex flex-col" style={{ height: PANEL_H, scrollSnapAlign: "start" }}>
        <div className="flex-1 flex flex-col items-center justify-center px-6 text-center max-w-3xl mx-auto w-full">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full mb-10 text-xs font-medium"
            style={{ background: "rgba(167,139,250,.07)", border: "1px solid rgba(167,139,250,.18)", color: "#a78bfa" }}>
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
        </div>
        {/* Mobile → first phone panel; desktop → first feature section */}
        <div className="lg:hidden"><ScrollArrow targetId="m-01-phone" /></div>
        <div className="hidden lg:block"><ScrollArrow targetId="section-01" /></div>
      </section>

      {FEATURES.map((f, i) => {
        const nextId = i < FEATURES.length - 1
          ? `m-${FEATURES[i + 1].num}-phone`
          : "section-footer";

        return (
          <div key={f.num}>

            {/* ── Mobile panel 1: phone + title ── */}
            <div
              id={`m-${f.num}-phone`}
              className="lg:hidden flex flex-col"
              style={{ height: PANEL_H, scrollSnapAlign: "start" }}
            >
              <div className="flex-1 flex items-center justify-center py-4 min-h-0">
                <MobilePhone>{f.screen}</MobilePhone>
              </div>
              <div className="text-center px-6 pb-2 shrink-0">
                <div className="text-xs font-mono mb-1" style={{ color: f.accent, letterSpacing: "0.2em" }}>
                  {f.num}
                </div>
                <h2 className="text-3xl font-bold leading-tight" style={{ letterSpacing: "-0.02em" }}>
                  {f.title}
                </h2>
              </div>
              <ScrollArrow targetId={`m-${f.num}-desc`} />
            </div>

            {/* ── Mobile panel 2: description ── */}
            <div
              id={`m-${f.num}-desc`}
              className="lg:hidden flex flex-col"
              style={{ height: PANEL_H, scrollSnapAlign: "start" }}
            >
              <div className="flex-1 flex flex-col justify-center px-8 py-6 min-h-0 overflow-y-auto">
                <div className="text-xs font-mono mb-3" style={{ color: f.accent, letterSpacing: "0.2em" }}>
                  {f.num}
                </div>
                <h2 className="text-3xl font-bold mb-3 leading-tight" style={{ letterSpacing: "-0.02em" }}>
                  {f.title}
                </h2>
                <p className="text-lg font-medium mb-5" style={{ color: f.accent }}>
                  {f.tagline}
                </p>
                <p className="text-base leading-relaxed" style={{ color: "#64748b" }}>
                  {f.description}
                </p>
              </div>
              <ScrollArrow targetId={nextId} />
            </div>

            {/* ── Desktop panel: side-by-side (unchanged) ── */}
            <div
              id={`section-${f.num}`}
              className="hidden lg:flex flex-col max-w-5xl mx-auto px-6 w-full"
              style={{ height: PANEL_H, scrollSnapAlign: "start" }}
            >
              <div className="flex-1 flex items-center overflow-hidden">
                <div className="w-full">
                  <FeatureRow feature={f} flip={i % 2 !== 0} />
                </div>
              </div>
              {i < FEATURES.length - 1 && (
                <ScrollArrow targetId={`section-${FEATURES[i + 1].num}`} />
              )}
            </div>

          </div>
        );
      })}

      {/* Footer */}
      <footer
        id="section-footer"
        className="border-t flex flex-col items-center justify-center text-center"
        style={{ height: PANEL_H, scrollSnapAlign: "start", borderColor: "rgba(255,255,255,.04)" }}
      >
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full mb-6 text-xs"
          style={{ background: "rgba(0,212,255,.05)", border: "1px solid rgba(0,212,255,.1)", color: "#00d4ff" }}>
          Built at Agentic Engineering Hack · Datadog NYC 2026
        </div>
        <p className="mb-8" style={{ color: "#1e293b", fontSize: 14 }}>The web demo is live. The phone is next.</p>
        <Link href="/" className="text-sm" style={{ color: "#00d4ff" }}>Try the live demo</Link>
      </footer>

    </div>
  );
}
