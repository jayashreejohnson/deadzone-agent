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

function severityBadge(severity?: string) {
  if (severity === "high") return { label: "⚠️ High", cls: "bg-red-500/20 text-red-300 border border-red-500/30" };
  if (severity === "medium") return { label: "🟡 Medium", cls: "bg-yellow-500/20 text-yellow-300 border border-yellow-500/30" };
  if (severity === "low") return { label: "🟢 Low", cls: "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30" };
  return { label: "Unknown", cls: "bg-slate-700 text-slate-300" };
}

export default function TripPlanner({ onPlanComplete, onStartTrip, apiBase, planState }: TripPlannerProps) {
  const [route, setRoute] = useState("Manhattan to Newark");
  const [departureTime, setDepartureTime] = useState(getDefaultDepartureTime);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detectedZones, setDetectedZones] = useState<DeadZone[]>([]);
  const [routeId, setRouteId] = useState<string>("test_route");

  async function handlePlan() {
    setLoading(true);
    setError(null);
    setDetectedZones([]);
    try {
      const res = await fetch(`${apiBase}/plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ route, departure_time: departureTime }),
      });
      if (!res.ok) throw new Error(`API error ${res.status}`);
      const data = await res.json();

      // Map API response to DeadZone type
      // Response shape: { route_id, dead_zones: [{ id, lat, lng, description, start_time, duration_minutes, severity }] }
      const zones: DeadZone[] = (data.dead_zones || data.zones || []).map((z: Record<string, unknown>) => ({
        id: String(z.id || z.deadzone_id || "zone"),
        name: String(z.description || z.name || z.id || "Dead zone"),
        lat: Number(z.lat),
        lng: Number(z.lng),
        radius_km: Number(z.radius_km || 0.6),
        duration_minutes: z.duration_minutes ? Number(z.duration_minutes) : undefined,
        severity: (z.severity as DeadZone["severity"]) || "medium",
      }));

      const rid = String(data.route_id || "test_route");
      setDetectedZones(zones);
      setRouteId(rid);
      onPlanComplete(zones, rid, route);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to reach planning API");
    } finally {
      setLoading(false);
    }
  }

  const isReady = planState === "ready" && detectedZones.length > 0;

  return (
    <div className="bg-slate-900/95 backdrop-blur-md rounded-2xl p-6 ring-1 ring-sky-400/40 shadow-[0_0_60px_-15px_rgba(56,189,248,0.4)] w-full max-w-lg mx-auto animate-[fadeInUp_0.35s_ease-out]">
      <div className="flex items-center gap-3 mb-5">
        <span className="text-2xl">🗺️</span>
        <h2 className="text-lg font-semibold text-slate-100">Plan Your Trip</h2>
      </div>

      <div className="space-y-4">
        <div>
          <label className="block text-xs uppercase tracking-wider text-slate-500 mb-1">Route</label>
          <input
            type="text"
            value={route}
            onChange={(e) => setRoute(e.target.value)}
            placeholder="Manhattan to Newark"
            disabled={loading || isReady}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-100 text-sm placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-sky-500 disabled:opacity-50"
          />
        </div>

        <div>
          <label className="block text-xs uppercase tracking-wider text-slate-500 mb-1">Departure Time</label>
          <input
            type="time"
            value={departureTime}
            onChange={(e) => setDepartureTime(e.target.value)}
            disabled={loading || isReady}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 disabled:opacity-50"
          />
        </div>

        {error && (
          <div className="text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        {!isReady && (
          <button
            onClick={handlePlan}
            disabled={loading || !route.trim()}
            className="w-full px-4 py-2.5 rounded-lg bg-sky-500 text-white font-medium hover:bg-sky-400 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Agent 1 predicting dead zones...
              </>
            ) : (
              "Plan Trip →"
            )}
          </button>
        )}
      </div>

      {isReady && detectedZones.length > 0 && (
        <div className="mt-5 space-y-3">
          <div className="text-xs uppercase tracking-wider text-slate-500">Detected dead zones</div>
          <div className="space-y-2">
            {detectedZones.map((zone) => {
              const badge = severityBadge(zone.severity);
              return (
                <div key={zone.id} className="flex items-center gap-2 bg-slate-800/60 rounded-lg px-3 py-2">
                  <span className="text-slate-400">📍</span>
                  <span className="text-slate-100 text-sm flex-1">{zone.name}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${badge.cls}`}>{badge.label}</span>
                  {zone.duration_minutes && (
                    <span className="text-xs text-slate-500">{zone.duration_minutes} min blackout</span>
                  )}
                </div>
              );
            })}
          </div>

          <button
            onClick={onStartTrip}
            className="w-full px-4 py-2.5 rounded-lg bg-emerald-500 text-white font-medium hover:bg-emerald-400 flex items-center justify-center gap-2"
          >
            🚗 Start Trip
          </button>

          <button
            onClick={() => {
              setDetectedZones([]);
              setError(null);
            }}
            className="w-full px-4 py-2 rounded-lg bg-slate-800 text-slate-400 text-sm hover:bg-slate-700"
          >
            Re-plan
          </button>
        </div>
      )}
    </div>
  );
}
