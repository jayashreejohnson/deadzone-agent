"use client";
import { useEffect, useState } from "react";

type OfflineOverlayProps = {
  durationSeconds: number; // total simulated offline duration
  onDone: () => void;
};

export default function OfflineOverlay({ durationSeconds, onDone }: OfflineOverlayProps) {
  const [elapsed, setElapsed] = useState(0);
  const [fading, setFading] = useState(false);

  useEffect(() => {
    if (durationSeconds <= 0) {
      onDone();
      return;
    }
    const id = setInterval(() => {
      setElapsed((prev) => {
        const next = prev + 0.1;
        if (next >= durationSeconds) {
          clearInterval(id);
          setFading(true);
          setTimeout(onDone, 600);
        }
        return next;
      });
    }, 100);
    return () => clearInterval(id);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [durationSeconds]);

  const progress = Math.min(elapsed / Math.max(durationSeconds, 1), 1);

  return (
    <div
      className={`absolute inset-0 z-[2000] flex flex-col items-center justify-center bg-slate-950/80 backdrop-blur-sm transition-opacity duration-500 ${
        fading ? "opacity-0" : "opacity-100"
      }`}
    >
      <div className="text-center space-y-4 px-8 max-w-sm">
        <div className="text-5xl">📵</div>
        <div className="text-2xl font-bold text-slate-100">No Signal</div>
        <div className="text-slate-400 text-sm">Offline pack playing...</div>

        <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
          <div
            className="h-full bg-sky-500 rounded-full transition-all duration-100"
            style={{ width: `${progress * 100}%` }}
          />
        </div>

        <div className="text-xs text-slate-500">
          {Math.ceil(Math.max(durationSeconds - elapsed, 0))}s remaining
        </div>
      </div>
    </div>
  );
}
