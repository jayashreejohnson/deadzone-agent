"use client";

export default function OfflinePill() {
  return (
    <div
      className="flex items-center gap-2.5 rounded-full px-4 py-2 animate-[fadeIn_0.4s_ease-out]"
      style={{
        background:    "rgba(5, 8, 16, 0.92)",
        backdropFilter:"blur(16px)",
        border:        "1px solid rgba(239, 68, 68, 0.3)",
        boxShadow:     "0 0 20px rgba(239, 68, 68, 0.15)",
      }}
    >
      <span
        className="inline-block w-2 h-2 rounded-full animate-pulse"
        style={{ background: "#ef4444", boxShadow: "0 0 6px rgba(239,68,68,0.8)" }}
      />
      <div className="text-xs">
        <span className="font-semibold" style={{ color: "#fca5a5" }}>Offline continuity active</span>
        <span className="text-slate-600 ml-2 hidden sm:inline">pack loaded</span>
      </div>
    </div>
  );
}
