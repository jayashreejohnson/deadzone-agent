"use client";
import { useState } from "react";
import type { DeadZone } from "@/lib/route";

type TripPlannerProps = {
  onPlanComplete: (zones: DeadZone[], routeId: string, route: string) => void;
  onStartTrip: () => void;
  apiBase: string;
  planState: "idle" | "planning" | "ready";
};

function getDefaultDepartureTime(): string {
  const d = new Date(Date.now() + 30 * 60 * 1000);
  const h = d.getHours().toString().padStart(2, "0");
  const m = d.getMinutes().toString().padStart(2, "0");
  return `${h}:${m}`;
}

function SeverityChip({ severity }: { severity?: string }) {
  if (severity === "high")
    return (
      <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full tracking-wider"
            style={{ background: "rgba(239,68,68,0.18)", color: "#fca5a5", border: "1px solid rgba(239,68,68,0.35)" }}>
        HIGH
      </span>
    );
  if (severity === "medium")
    return (
      <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full tracking-wider"
            style={{ background: "rgba(245,158,11,0.15)", color: "#fcd34d", border: "1px solid rgba(245,158,11,0.3)" }}>
        MEDIUM
      </span>
    );
  return (
    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full tracking-wider"
          style={{ background: "rgba(16,185,129,0.15)", color: "#6ee7b7", border: "1px solid rgba(16,185,129,0.3)" }}>
      LOW
    </span>
  );
}

export default function TripPlanner({ onPlanComplete, onStartTrip, apiBase, planState }: TripPlannerProps) {
  const [route, setRoute]               = useState("Manhattan to Newark");
  const [departureTime, setDepartureTime] = useState(getDefaultDepartureTime);
  const [loading, setLoading]           = useState(false);
  const [error, setError]               = useState<string | null>(null);
  const [detectedZones, setDetectedZones] = useState<DeadZone[]>([]);

  async function handlePlan() {
    setLoading(true);
    setError(null);
    setDetectedZones([]);
    try {
      const res = await fetch(`${apiBase}/plan`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ route, departure_time: departureTime }),
      });
      if (!res.ok) throw new Error(`API error ${res.status}`);
      const data = await res.json();

      const zones: DeadZone[] = (data.dead_zones || data.zones || []).map((z: Record<string, unknown>) => ({
        id:               String(z.id || z.deadzone_id || "zone"),
        name:             String(z.description || z.name || z.id || "Dead zone"),
        lat:              Number(z.lat),
        lng:              Number(z.lng),
        radius_km:        Number(z.radius_km || 0.6),
        duration_minutes: z.duration_minutes ? Number(z.duration_minutes) : undefined,
        severity:         (z.severity as DeadZone["severity"]) || "medium",
      }));

      const rid = String(data.route_id || "test_route");
      setDetectedZones(zones);
      onPlanComplete(zones, rid, route);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to reach planning API");
    } finally {
      setLoading(false);
    }
  }

  const isReady = planState === "ready" && detectedZones.length > 0;

  return (
    <div
      className="w-full max-w-lg mx-auto rounded-2xl p-6 animate-[fadeInUp_0.4s_ease-out]"
      style={{
        background:    "rgba(5, 8, 16, 0.92)",
        backdropFilter:"blur(24px)",
        border:        "1px solid rgba(0, 212, 255, 0.2)",
        boxShadow:     "0 0 60px -10px rgba(0, 212, 255, 0.18), 0 32px 64px -24px rgba(0,0,0,0.8)",
      }}
    >
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div
          className="w-9 h-9 rounded-lg flex items-center justify-center text-lg shrink-0"
          style={{ background: "rgba(0,212,255,0.1)", border: "1px solid rgba(0,212,255,0.25)" }}
        >
          🛰
        </div>
        <div>
          <h2 className="text-base font-semibold text-slate-100 tracking-tight">Neural Route Scan</h2>
          <p className="text-[11px] text-slate-500 tracking-wide">AI predicts dead zones before you leave</p>
        </div>
      </div>

      <div className="space-y-4">
        {/* Route input */}
        <div>
          <label className="block text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-1.5">
            Route
          </label>
          <input
            type="text"
            value={route}
            onChange={(e) => setRoute(e.target.value)}
            placeholder="Manhattan to Newark"
            disabled={loading || isReady}
            className="w-full rounded-lg px-3.5 py-2.5 text-slate-100 text-sm placeholder-slate-600
                       focus:outline-none disabled:opacity-40 transition-all duration-200"
            style={{
              background:   "rgba(255,255,255,0.04)",
              border:       "1px solid rgba(0,212,255,0.18)",
              fontFamily:   "inherit",
            }}
            onFocus={(e) => (e.currentTarget.style.borderColor = "rgba(0,212,255,0.5)")}
            onBlur={(e)  => (e.currentTarget.style.borderColor = "rgba(0,212,255,0.18)")}
          />
        </div>

        {/* Departure time */}
        <div>
          <label className="block text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-1.5">
            Departure Time
          </label>
          <input
            type="time"
            value={departureTime}
            onChange={(e) => setDepartureTime(e.target.value)}
            disabled={loading || isReady}
            className="w-full rounded-lg px-3.5 py-2.5 text-slate-100 text-sm
                       focus:outline-none disabled:opacity-40 transition-all duration-200"
            style={{
              background:  "rgba(255,255,255,0.04)",
              border:      "1px solid rgba(0,212,255,0.18)",
              fontFamily:  "inherit",
              colorScheme: "dark",
            }}
            onFocus={(e) => (e.currentTarget.style.borderColor = "rgba(0,212,255,0.5)")}
            onBlur={(e)  => (e.currentTarget.style.borderColor = "rgba(0,212,255,0.18)")}
          />
        </div>

        {/* Error */}
        {error && (
          <div className="text-red-300 text-sm rounded-lg px-3.5 py-2.5"
               style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.25)" }}>
            {error}
          </div>
        )}

        {/* Plan button */}
        {!isReady && (
          <button
            onClick={handlePlan}
            disabled={loading || !route.trim()}
            className="w-full px-4 py-3 rounded-lg font-semibold text-sm tracking-wide
                       disabled:opacity-40 disabled:cursor-not-allowed
                       flex items-center justify-center gap-2.5 transition-all duration-200"
            style={{
              background: loading
                ? "rgba(0,212,255,0.08)"
                : "linear-gradient(135deg, #0ea5e9 0%, #00d4ff 100%)",
              color:     loading ? "#00d4ff" : "#050810",
              border:    loading ? "1px solid rgba(0,212,255,0.3)" : "none",
              boxShadow: loading ? "none" : "0 0 24px rgba(0,212,255,0.3)",
            }}
          >
            {loading ? (
              <>
                <span
                  className="inline-block w-4 h-4 rounded-full border-2 animate-spin"
                  style={{ borderColor: "rgba(0,212,255,0.25)", borderTopColor: "#00d4ff" }}
                />
                <span style={{ color: "#00d4ff" }}>Agent scanning route…</span>
              </>
            ) : (
              <>
                <span>⚡</span>
                Scan for Dead Zones
              </>
            )}
          </button>
        )}
      </div>

      {/* Results */}
      {isReady && detectedZones.length > 0 && (
        <div className="mt-5 space-y-3 animate-[fadeInUp_0.35s_ease-out]">
          {/* Divider */}
          <div className="flex items-center gap-3">
            <div className="flex-1 h-px" style={{ background: "rgba(0,212,255,0.12)" }} />
            <span className="text-[10px] uppercase tracking-[0.2em] text-slate-500">
              {detectedZones.length} zone{detectedZones.length !== 1 ? "s" : ""} detected
            </span>
            <div className="flex-1 h-px" style={{ background: "rgba(0,212,255,0.12)" }} />
          </div>

          {/* Zone list */}
          <div className="space-y-2">
            {detectedZones.map((zone, idx) => (
              <div
                key={zone.id}
                className="flex items-center gap-3 rounded-xl px-3.5 py-2.5 animate-[fadeInUp_0.3s_ease-out]"
                style={{
                  background:    "rgba(255,255,255,0.03)",
                  border:        "1px solid rgba(255,255,255,0.07)",
                  animationDelay:`${idx * 60}ms`,
                }}
              >
                <span className="text-slate-500 text-xs font-mono w-4 shrink-0 text-center">
                  {idx + 1}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-slate-100 text-sm font-medium truncate">{zone.name}</div>
                  {zone.duration_minutes && (
                    <div className="text-[11px] text-slate-500 mt-0.5">
                      {zone.duration_minutes} min blackout
                    </div>
                  )}
                </div>
                <SeverityChip severity={zone.severity} />
              </div>
            ))}
          </div>

          {/* Action buttons */}
          <button
            onClick={onStartTrip}
            className="w-full px-4 py-3 rounded-xl font-semibold text-sm tracking-wide
                       flex items-center justify-center gap-2 transition-all duration-200"
            style={{
              background: "linear-gradient(135deg, #059669 0%, #10b981 100%)",
              color:      "#fff",
              boxShadow:  "0 0 24px rgba(16,185,129,0.3)",
            }}
          >
            🚗 Start Trip
          </button>

          <button
            onClick={() => { setDetectedZones([]); setError(null); }}
            className="w-full px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-200"
            style={{
              background: "rgba(255,255,255,0.04)",
              color:      "#94a3b8",
              border:     "1px solid rgba(255,255,255,0.08)",
            }}
          >
            ↺ Re-plan
          </button>
        </div>
      )}
    </div>
  );
}
