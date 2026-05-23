"use client";

export default function Home({ onStart }: { onStart: () => void }) {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6 text-center
                    bg-gradient-to-b from-slate-950 via-slate-950 to-slate-900">
      <div className="mb-6 flex items-center gap-2 text-xs uppercase tracking-[0.25em] text-slate-500">
        <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
        DeadZone Agent
      </div>
      <h1 className="text-5xl md:text-6xl font-bold tracking-tight text-white max-w-2xl">
        Navigate without interruption.
      </h1>
      <p className="mt-5 text-lg md:text-xl text-slate-400 max-w-xl">
        Predict connectivity disruptions before they happen.
      </p>
      <button
        onClick={onStart}
        className="mt-12 px-7 py-3.5 rounded-xl text-base font-medium
                   bg-emerald-500 text-white hover:bg-emerald-400 transition
                   shadow-[0_0_40px_rgba(52,211,153,0.35)]"
      >
        Start Intelligent Navigation
      </button>
      <div className="mt-16 text-xs text-slate-600">
        autonomous · LLM-driven · agent-to-agent settlement
      </div>
    </div>
  );
}
