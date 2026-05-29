"use client";
import Link from "next/link";

/**
 * Shared top-navigation tabs used on both / (demo) and /mobile pages.
 * The visitor can switch between sections anytime, both presented as peers,
 * per the winning design from the 30-agent test.
 */

type ActiveTab = "demo" | "mobile";

type Props = {
  active: ActiveTab;
  /** Extra slot (right side) for page-specific controls, e.g. demo buttons. */
  rightSlot?: React.ReactNode;
  /** Optional live-status indicator (only used on the demo page). */
  wsConnected?: boolean;
};

export default function TopNavTabs({ active, rightSlot, wsConnected }: Props) {
  return (
    <div
      className="flex items-center justify-between px-4 py-2.5"
      style={{
        background:    "rgba(5, 8, 16, 0.88)",
        backdropFilter:"blur(18px)",
        borderBottom:  "1px solid rgba(0, 212, 255, 0.12)",
        boxShadow:     "0 1px 40px rgba(0,0,0,0.4)",
      }}
    >
      {/* Left, logo + status */}
      <div className="flex items-center gap-3">
        <Link href="/" className="flex items-center gap-2">
          <div className="relative">
            <span
              className="inline-block w-2 h-2 rounded-full"
              style={{ background: "#00d4ff", boxShadow: "0 0 8px #00d4ff" }}
            />
            <span
              className="absolute inset-0 inline-block w-2 h-2 rounded-full animate-ping"
              style={{ background: "#00d4ff", opacity: 0.4 }}
            />
          </div>
          <span
            className="font-bold text-sm tracking-tight"
            style={{ color: "#e2e8f0", letterSpacing: "-0.01em" }}
          >
            DeadZone
          </span>
        </Link>
        {wsConnected !== undefined && (
          <span
            className="hidden sm:flex items-center gap-1 text-[10px] font-medium tracking-wide"
            style={{ color: wsConnected ? "#10b981" : "#94a3b8" }}
          >
            <span
              className="inline-block w-1.5 h-1.5 rounded-full"
              style={{
                background: wsConnected ? "#10b981" : "#475569",
                boxShadow: wsConnected ? "0 0 6px #10b981" : "none",
              }}
            />
            {wsConnected ? "live" : "connecting"}
          </span>
        )}
      </div>

      {/* Center, tabs */}
      <div className="absolute left-1/2 -translate-x-1/2 hidden sm:flex items-center gap-1 p-1 rounded-xl"
        style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}
      >
        <Link
          href="/"
          className="px-3.5 py-1 text-xs rounded-lg font-medium transition-all duration-200"
          style={
            active === "demo"
              ? { background: "rgba(0,212,255,0.15)", color: "#00d4ff", border: "1px solid rgba(0,212,255,0.3)" }
              : { background: "transparent", color: "#64748b", border: "1px solid transparent" }
          }
        >
          Try it now
        </Link>
        <Link
          href="/mobile"
          className="px-3.5 py-1 text-xs rounded-lg font-medium transition-all duration-200 flex items-center gap-1.5"
          style={
            active === "mobile"
              ? { background: "rgba(167,139,250,0.15)", color: "#c4b5fd", border: "1px solid rgba(167,139,250,0.3)" }
              : { background: "transparent", color: "#64748b", border: "1px solid transparent" }
          }
        >
          <span>📱</span>
          <span>On your phone</span>
        </Link>
      </div>

      {/* Right, page-specific controls */}
      <div className="flex items-center gap-1.5">
        {rightSlot}
      </div>
    </div>
  );
}
