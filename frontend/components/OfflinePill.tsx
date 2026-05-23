"use client";

export default function OfflinePill() {
  return (
    <div className="bg-slate-900/95 backdrop-blur-md rounded-full px-4 py-2
                    ring-1 ring-slate-700 flex items-center gap-2
                    animate-[fadeIn_0.4s_ease-out]">
      <span className="text-base">📴</span>
      <div className="text-xs text-slate-300">
        <span className="font-medium">Offline continuity active</span>
        <span className="text-slate-500 ml-2">maintaining prepared experience locally</span>
      </div>
    </div>
  );
}
