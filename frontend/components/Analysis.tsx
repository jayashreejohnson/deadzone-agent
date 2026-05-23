"use client";
import { useEffect, useState } from "react";

const CHECKS = [
  "Checking signal stability",
  "Predicting interruption zones",
  "Evaluating route intelligence",
  "Preparing continuity options",
];

const STEP_MS = 700;       // delay between checks
const HOLD_AFTER_MS = 600; // pause after last check before advancing

export default function Analysis({ onComplete }: { onComplete: () => void }) {
  const [done, setDone] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const id = setInterval(() => {
      setDone((d) => {
        if (d >= CHECKS.length) {
          clearInterval(id);
          if (!cancelled) setTimeout(onComplete, HOLD_AFTER_MS);
          return d;
        }
        return d + 1;
      });
    }, STEP_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, [onComplete]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6
                    bg-gradient-to-b from-slate-950 to-slate-900">
      <div className="mb-10 flex items-center gap-3">
        <span className="inline-block w-3 h-3 rounded-full bg-sky-400 animate-pulse" />
        <h2 className="text-xl font-medium text-slate-200">
          Building your connectivity profile…
        </h2>
      </div>
      <ul className="space-y-4 w-full max-w-md">
        {CHECKS.map((c, i) => {
          const active = i < done;
          return (
            <li
              key={c}
              className={`flex items-center gap-4 text-base transition-all duration-500 ${
                active ? "opacity-100 translate-x-0" : "opacity-30 -translate-x-1"
              }`}
            >
              <span
                className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs ${
                  active
                    ? "bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-400/50"
                    : "bg-slate-800 text-slate-600"
                }`}
              >
                ✓
              </span>
              <span className={active ? "text-slate-100" : "text-slate-500"}>{c}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
