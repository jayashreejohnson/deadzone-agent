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
    <Shell tone="amber">
      <Header icon="⚠" title="Weak connectivity predicted ahead" tone="amber" />
      <div className="grid grid-cols-3 gap-4 mt-5">
        <Stat label="Location" value={deadzoneName} />
        <Stat label="Est. interruption" value={`${mins}m ${secs.toString().padStart(2, "0")}s`} />
        <Stat label="Signal confidence" value={`${confidence}%`} />
      </div>
      <div className="mt-6 flex gap-2 flex-wrap">
        <button onClick={onPrepare}
          className="flex-1 min-w-[140px] px-4 py-2.5 rounded-lg bg-amber-400 text-slate-950 font-medium hover:bg-amber-300">
          Prepare Continuity
        </button>
        <button onClick={onSwitch}
          className="px-4 py-2.5 rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700">
          Switch Route
        </button>
        <button onClick={onStay}
          className="px-4 py-2.5 rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700">
          Stay on Current Route
        </button>
      </div>
    </Shell>
  );
}

export function PreparingCard() {
  return (
    <Shell tone="sky">
      <div className="flex items-center gap-3">
        <span className="inline-block w-3 h-3 rounded-full bg-sky-400 animate-pulse" />
        <h3 className="text-lg font-medium text-slate-100">Preparing continuity pack…</h3>
      </div>
      <p className="mt-2 text-sm text-slate-400">
        Building offline route intelligence before signal loss.
      </p>
    </Shell>
  );
}

export function CachedFoundCard() {
  return (
    <Shell tone="violet">
      <div className="flex items-center gap-3">
        <span className="text-xl">⚡</span>
        <h3 className="text-lg font-medium text-slate-100">Existing continuity pack found</h3>
      </div>
      <p className="mt-2 text-sm text-slate-400">
        Reusing previously generated route intelligence.
      </p>
    </Shell>
  );
}

export function ReadyCard({
  cached, paidAmount, onOpen,
}: { cached: boolean; paidAmount?: number; onOpen: () => void }) {
  return (
    <Shell tone="emerald">
      <div className="flex items-center gap-3">
        <span className="text-xl">✅</span>
        <h3 className="text-lg font-medium text-slate-100">Offline continuity ready</h3>
      </div>
      <p className="mt-2 text-sm text-slate-400">
        Your journey experience has been prepared locally.
      </p>
      {cached && (
        <div className="mt-3 inline-flex items-center gap-2 px-2.5 py-1 rounded-full
                        bg-violet-500/15 text-violet-200 text-xs">
          bought from agent_a · ${(paidAmount ?? 0.02).toFixed(2)}
        </div>
      )}
      <button onClick={onOpen}
        className="mt-5 w-full px-4 py-2.5 rounded-lg bg-emerald-500 text-white font-medium hover:bg-emerald-400">
        Open Continuity Pack
      </button>
    </Shell>
  );
}

// ----- internals -----

function Shell({ tone, children }: { tone: "amber" | "sky" | "violet" | "emerald";
                                     children: React.ReactNode }) {
  const ring = {
    amber: "ring-amber-400/40 shadow-[0_0_60px_-15px_rgba(251,191,36,0.4)]",
    sky: "ring-sky-400/40 shadow-[0_0_60px_-15px_rgba(56,189,248,0.4)]",
    violet: "ring-violet-400/40 shadow-[0_0_60px_-15px_rgba(167,139,250,0.4)]",
    emerald: "ring-emerald-400/40 shadow-[0_0_60px_-15px_rgba(52,211,153,0.5)]",
  }[tone];
  return (
    <div className={`bg-slate-900/95 backdrop-blur-md rounded-2xl p-6 ring-1 ${ring}
                     animate-[fadeInUp_0.35s_ease-out]`}>
      {children}
    </div>
  );
}

function Header({ icon, title, tone }: { icon: string; title: string; tone: "amber" }) {
  return (
    <div className="flex items-center gap-3">
      <span className={`text-2xl ${tone === "amber" ? "text-amber-300" : ""}`}>{icon}</span>
      <h3 className="text-lg font-medium text-slate-100">{title}</h3>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className="mt-1 text-slate-100 text-sm font-medium">{value}</div>
    </div>
  );
}
