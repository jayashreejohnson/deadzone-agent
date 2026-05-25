"use client";

type Common = { onDismiss?: () => void };

export function AlertCard({
  deadzoneName, etaSeconds, confidence, onPrepare, onSwitch, onStay,
}: Common & {
  deadzoneName: string; etaSeconds: number; confidence: number;
  onPrepare: () => void; onSwitch: () => void; onStay: () => void;
}) {
  const mins = Math.floor(etaSeconds / 60);
  const secs = etaSeconds % 60;
  return (
    <Shell accent="#f59e0b" glow="rgba(245,158,11,0.18)">
      <div className="flex items-center gap-3 mb-5">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center text-xl shrink-0"
          style={{ background: "rgba(245,158,11,0.12)", border: "1px solid rgba(245,158,11,0.3)" }}
        >
          ⚠
        </div>
        <div>
          <h3 className="text-base font-semibold text-slate-100">Dead zone ahead</h3>
          <p className="text-xs text-slate-500 mt-0.5">Weak connectivity predicted</p>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3 mb-5">
        <StatTile label="Location"       value={deadzoneName} color="#f59e0b" />
        <StatTile label="Est. blackout"  value={`${mins}m ${secs.toString().padStart(2, "0")}s`} color="#f59e0b" />
        <StatTile label="Confidence"     value={`${confidence}%`} color="#10b981" />
      </div>
      <div className="flex gap-2">
        <button
          onClick={onPrepare}
          className="flex-1 px-4 py-2.5 rounded-xl font-semibold text-sm tracking-wide transition-all duration-200"
          style={{
            background: "linear-gradient(135deg, #d97706 0%, #f59e0b 100%)",
            color:      "#050810",
            boxShadow:  "0 0 20px rgba(245,158,11,0.3)",
          }}
        >
          Prepare Pack
        </button>
        <button
          onClick={onSwitch}
          className="px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-200"
          style={{ background: "rgba(255,255,255,0.05)", color: "#94a3b8", border: "1px solid rgba(255,255,255,0.08)" }}
        >
          Reroute
        </button>
        <button
          onClick={onStay}
          className="px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-200"
          style={{ background: "rgba(255,255,255,0.05)", color: "#94a3b8", border: "1px solid rgba(255,255,255,0.08)" }}
        >
          Stay
        </button>
      </div>
    </Shell>
  );
}

export function PreparingCard() {
  return (
    <Shell accent="#00d4ff" glow="rgba(0,212,255,0.14)">
      <div className="flex items-center gap-3">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
          style={{ background: "rgba(0,212,255,0.08)", border: "1px solid rgba(0,212,255,0.25)" }}
        >
          <span
            className="inline-block w-5 h-5 rounded-full border-2 animate-spin"
            style={{ borderColor: "rgba(0,212,255,0.2)", borderTopColor: "#00d4ff" }}
          />
        </div>
        <div>
          <h3 className="text-base font-semibold text-slate-100">Building offline pack…</h3>
          <p className="text-xs text-slate-500 mt-0.5">Agents sourcing local intelligence</p>
        </div>
      </div>
    </Shell>
  );
}

export function CachedFoundCard() {
  return (
    <Shell accent="#8b5cf6" glow="rgba(139,92,246,0.15)">
      <div className="flex items-center gap-3">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center text-xl shrink-0"
          style={{ background: "rgba(139,92,246,0.1)", border: "1px solid rgba(139,92,246,0.3)" }}
        >
          ⚡
        </div>
        <div>
          <h3 className="text-base font-semibold text-slate-100">Cached pack found</h3>
          <p className="text-xs text-slate-500 mt-0.5">Reusing prior route intelligence via x402</p>
        </div>
      </div>
    </Shell>
  );
}

export function ReadyCard({
  cached, paidAmount, evalScore, slaPass, onOpen,
}: { cached: boolean; paidAmount?: number; evalScore?: number; slaPass?: boolean; onOpen: () => void }) {
  const scoreColor = evalScore !== undefined
    ? (evalScore >= 80 ? "#10b981" : evalScore >= 60 ? "#f59e0b" : "#ef4444")
    : undefined;
  return (
    <Shell accent="#10b981" glow="rgba(16,185,129,0.16)">
      <div className="flex items-center gap-3 mb-4">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center text-xl shrink-0"
          style={{ background: "rgba(16,185,129,0.1)", border: "1px solid rgba(16,185,129,0.3)" }}
        >
          ✅
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold text-slate-100">Offline continuity ready</h3>
          <p className="text-xs text-slate-500 mt-0.5">Your journey is secured for the dead zone</p>
        </div>
        {evalScore !== undefined && scoreColor && (
          <div
            className="shrink-0 flex flex-col items-center justify-center w-12 h-12 rounded-xl"
            style={{ background: `${scoreColor}12`, border: `1px solid ${scoreColor}30` }}
            title={`Quality score ${evalScore}/100 · SLA ${slaPass ? "passed" : "missed"}`}
          >
            <span className="text-sm font-bold tabular-nums" style={{ color: scoreColor }}>{evalScore}</span>
            <span className="text-[8px] uppercase tracking-wider" style={{ color: scoreColor }}>score</span>
          </div>
        )}
      </div>

      {/* Pack contents summary */}
      <div
        className="flex items-center gap-2 flex-wrap mb-4 px-3 py-2 rounded-xl"
        style={{ background: "rgba(16,185,129,0.05)", border: "1px solid rgba(16,185,129,0.12)" }}
      >
        <span className="text-[9px] uppercase tracking-[0.18em] text-slate-600 shrink-0">Pack includes</span>
        {[
          { icon: "🌦", label: "Weather" },
          { icon: "🛣", label: "Road conditions" },
          { icon: "📰", label: "Local news" },
          { icon: "📡", label: "Nearby services" },
        ].map(({ icon, label }) => (
          <span
            key={label}
            className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full"
            style={{ background: "rgba(16,185,129,0.1)", color: "#6ee7b7", border: "1px solid rgba(16,185,129,0.2)" }}
          >
            {icon} {label}
          </span>
        ))}
      </div>

      {cached && (
        <div
          className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium mb-4"
          style={{
            background: "rgba(139,92,246,0.12)",
            color:      "#c4b5fd",
            border:     "1px solid rgba(139,92,246,0.25)",
          }}
        >
          <span>⚡</span>
          Served from network cache — instant delivery
        </div>
      )}

      <button
        onClick={onOpen}
        className="w-full px-4 py-3 rounded-xl font-semibold text-sm tracking-wide transition-all duration-200"
        style={{
          background: "linear-gradient(135deg, #059669 0%, #10b981 100%)",
          color:      "#fff",
          boxShadow:  "0 0 24px rgba(16,185,129,0.3)",
        }}
      >
        Open Continuity Pack →
      </button>
    </Shell>
  );
}

// ── Internals ────────────────────────────────────────────────────

function Shell({
  accent, glow, children,
}: { accent: string; glow: string; children: React.ReactNode }) {
  return (
    <div
      className="rounded-2xl p-5 animate-[fadeInUp_0.35s_ease-out]"
      style={{
        background:    "rgba(5, 8, 16, 0.92)",
        backdropFilter:"blur(20px)",
        border:        `1px solid ${accent}28`,
        boxShadow:     `0 0 50px -12px ${glow}, 0 24px 48px -16px rgba(0,0,0,0.7)`,
      }}
    >
      {children}
    </div>
  );
}

function StatTile({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div
      className="rounded-xl px-3 py-2.5"
      style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}
    >
      <div className="text-[9px] uppercase tracking-[0.18em] text-slate-600 mb-1">{label}</div>
      <div className="text-sm font-semibold leading-tight" style={{ color }}>
        {value}
      </div>
    </div>
  );
}
