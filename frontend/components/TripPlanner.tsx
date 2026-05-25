"use client";
import { useState, useRef, useEffect } from "react";
import type { DeadZone } from "@/lib/route";

// ── Curated US routes ──────────────────────────────────────────────────────
type Severity = "high" | "medium" | "low";
type Route = {
  label:    string;   // Display name  e.g. "Manhattan → Newark"
  api:      string;   // Sent to /plan  e.g. "Manhattan to Newark"
  region:   string;
  hint:     string;   // Dead-zone characteristic
  severity: Severity; // Dominant severity on this route
};

const ROUTES: Route[] = [
  // Northeast — tunnel routes guarantee dead zones
  { label: "Manhattan → Newark",          api: "Manhattan to Newark",          region: "Northeast", hint: "Lincoln Tunnel",                    severity: "high"   },
  { label: "Washington DC → Baltimore",   api: "Washington DC to Baltimore",   region: "Northeast", hint: "Baltimore Harbor Tunnel",            severity: "high"   },
  { label: "New York → Philadelphia",     api: "New York to Philadelphia",     region: "Northeast", hint: "NJ Turnpike underpasses",            severity: "medium" },
  { label: "New York → Boston",           api: "New York to Boston",           region: "Northeast", hint: "I-95 CT/RI coverage gaps",           severity: "medium" },
  // Southeast — mountain terrain & remote corridors
  { label: "Atlanta → Charlotte",         api: "Atlanta to Charlotte",         region: "Southeast", hint: "Blue Ridge mountain gaps",           severity: "high"   },
  { label: "Miami → Orlando",             api: "Miami to Orlando",             region: "Southeast", hint: "Everglades rural corridor",          severity: "medium" },
  // Mountain — tunnels + canyon roads
  { label: "Denver → Vail",               api: "Denver to Vail",               region: "Mountain",  hint: "Eisenhower Tunnel + I-70 canyons",  severity: "high"   },
  { label: "Phoenix → Sedona",            api: "Phoenix to Sedona",            region: "Mountain",  hint: "AZ-89A mountain switchbacks",        severity: "high"   },
  { label: "Salt Lake City → Moab",       api: "Salt Lake City to Moab",       region: "Mountain",  hint: "US-191 canyon country",              severity: "high"   },
  // West — desert & coastal
  { label: "Los Angeles → Las Vegas",     api: "Los Angeles to Las Vegas",     region: "West",      hint: "Mojave Desert dead zones",           severity: "high"   },
  { label: "Los Angeles → San Diego",     api: "Los Angeles to San Diego",     region: "West",      hint: "Camp Pendleton corridor",            severity: "medium" },
  { label: "San Francisco → Los Angeles", api: "San Francisco to Los Angeles", region: "West",      hint: "Coastal I-5 remote stretches",       severity: "medium" },
  // Pacific NW — mountain passes
  { label: "Seattle → Spokane",           api: "Seattle to Spokane",           region: "Pacific NW",hint: "Cascade Mountain passes",            severity: "high"   },
  // South — rural highways
  { label: "Dallas → Houston",            api: "Dallas to Houston",            region: "South",     hint: "Rural I-45 Texas Hill Country",      severity: "medium" },
  // Transit — subway tunnels (complete blackouts underground)
  { label: "NYC: Times Square → Brooklyn",      api: "Times Square to Atlantic Terminal Brooklyn via NYC Subway",         region: "Transit", hint: "East River subway tunnel",          severity: "high"   },
  { label: "Boston: South Station → Harvard",   api: "South Station Boston to Harvard Square via Red Line Subway",        region: "Transit", hint: "Charles River underwater tunnel",    severity: "high"   },
  { label: "SF: Embarcadero → SFO Airport",     api: "Embarcadero San Francisco to SFO Airport via BART",                region: "Transit", hint: "BART transbay tube under the Bay",  severity: "high"   },
];

const POPULAR: Route[] = [
  ROUTES.find((r) => r.api === "Manhattan to Newark")!,
  ROUTES.find((r) => r.api === "Times Square to Atlantic Terminal Brooklyn via NYC Subway")!,
  ROUTES.find((r) => r.api === "Los Angeles to Las Vegas")!,
  ROUTES.find((r) => r.api === "Denver to Vail")!,
  ROUTES.find((r) => r.api === "Phoenix to Sedona")!,
];

const REGIONS = Array.from(new Set(ROUTES.map((r) => r.region)));

// ── Helpers ─────────────────────────────────────────────────────────────────

function getDefaultDepartureTime(): string {
  const d = new Date(Date.now() + 30 * 60 * 1000);
  return `${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
}

function SeverityDot({ severity }: { severity: Severity }) {
  const color = severity === "high" ? "#ef4444" : severity === "medium" ? "#f59e0b" : "#10b981";
  return (
    <span
      className="inline-block w-1.5 h-1.5 rounded-full shrink-0"
      style={{ background: color, boxShadow: `0 0 4px ${color}80` }}
    />
  );
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
        MED
      </span>
    );
  return (
    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full tracking-wider"
          style={{ background: "rgba(16,185,129,0.15)", color: "#6ee7b7", border: "1px solid rgba(16,185,129,0.3)" }}>
      LOW
    </span>
  );
}

// ── Main component ───────────────────────────────────────────────────────────

type TripPlannerProps = {
  onPlanComplete: (zones: DeadZone[], routeId: string, route: string) => void;
  onStartTrip: () => void;
  apiBase: string;
  planState: "idle" | "planning" | "ready";
};

export default function TripPlanner({ onPlanComplete, onStartTrip, apiBase, planState }: TripPlannerProps) {
  const [selected, setSelected]         = useState<Route | null>(null);
  const [query, setQuery]               = useState("");
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [departureTime, setDepartureTime] = useState(getDefaultDepartureTime);
  const [loading, setLoading]           = useState(false);
  const [error, setError]               = useState<string | null>(null);
  const [detectedZones, setDetectedZones] = useState<DeadZone[]>([]);

  const containerRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Filter routes by query
  const q = query.toLowerCase();
  const filtered = q
    ? ROUTES.filter((r) => r.label.toLowerCase().includes(q) || r.hint.toLowerCase().includes(q) || r.region.toLowerCase().includes(q))
    : ROUTES;

  // Group filtered routes by region (preserve region order)
  const grouped = REGIONS.flatMap((region) => {
    const routes = filtered.filter((r) => r.region === region);
    return routes.length ? [{ region, routes }] : [];
  });

  function pickRoute(r: Route) {
    setSelected(r);
    setQuery("");
    setDropdownOpen(false);
    setDetectedZones([]);
    setError(null);
  }

  function clearSelection() {
    setSelected(null);
    setQuery("");
    setDetectedZones([]);
    setError(null);
  }

  async function handlePlan() {
    if (!selected) return;
    setLoading(true);
    setError(null);
    setDetectedZones([]);
    const abort = new AbortController();
    const timeoutId = setTimeout(() => abort.abort(), 25_000);
    try {
      const res = await fetch(`${apiBase}/plan`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ route: selected.api, departure_time: departureTime }),
        signal:  abort.signal,
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
      onPlanComplete(zones, rid, selected.api);
    } catch (e) {
      setError(
        e instanceof Error && e.name === "AbortError"
          ? "Scan timed out — please try again"
          : e instanceof Error ? e.message : "Failed to reach planning API"
      );
    } finally {
      clearTimeout(timeoutId);
      setLoading(false);
    }
  }

  const isReady   = planState === "ready" && detectedZones.length > 0;
  const isLocked  = loading || isReady;

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
      <div className="flex items-center gap-3 mb-5">
        <div
          className="w-9 h-9 rounded-lg flex items-center justify-center text-lg shrink-0"
          style={{ background: "rgba(0,212,255,0.1)", border: "1px solid rgba(0,212,255,0.25)" }}
        >
          🛰
        </div>
        <div>
          <h2 className="text-base font-semibold text-slate-100 tracking-tight">Route Dead Zone Scan</h2>
          <p className="text-[11px] text-slate-500 tracking-wide">Select a US route — AI predicts coverage gaps</p>
        </div>
      </div>

      <div className="space-y-4">
        {/* ── Quick-pick chips ───────────────────────────────── */}
        {!isLocked && !selected && (
          <div>
            <p className="text-[10px] uppercase tracking-[0.15em] text-slate-600 mb-2">Popular routes</p>
            <div className="flex flex-wrap gap-1.5">
              {POPULAR.map((r) => (
                <button
                  key={r.api}
                  onClick={() => pickRoute(r)}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium
                             transition-all duration-150 hover:scale-[1.03] active:scale-95"
                  style={{
                    background: "rgba(0,212,255,0.06)",
                    border:     "1px solid rgba(0,212,255,0.2)",
                    color:      "#94a3b8",
                  }}
                >
                  <SeverityDot severity={r.severity} />
                  {r.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── Combobox ──────────────────────────────────────── */}
        <div ref={containerRef} className="relative">
          <label className="block text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-1.5">
            Route
          </label>

          {selected ? (
            /* ── Selected state ── */
            <div
              className="flex items-center gap-2 rounded-lg px-3.5 py-2.5"
              style={{
                background: "rgba(0,212,255,0.06)",
                border:     "1px solid rgba(0,212,255,0.35)",
              }}
            >
              <SeverityDot severity={selected.severity} />
              <span className="flex-1 text-slate-100 text-sm font-medium">{selected.label}</span>
              <span className="text-[11px] text-slate-500 hidden sm:inline">{selected.hint}</span>
              {!isLocked && (
                <button
                  onClick={clearSelection}
                  className="ml-2 text-slate-500 hover:text-slate-300 transition-colors text-base leading-none"
                  title="Change route"
                >
                  ×
                </button>
              )}
            </div>
          ) : (
            /* ── Search input ── */
            <input
              type="text"
              value={query}
              onChange={(e) => { setQuery(e.target.value); setDropdownOpen(true); }}
              onFocus={(e) => { setDropdownOpen(true); e.currentTarget.style.borderColor = "rgba(0,212,255,0.5)"; }}
              onBlur={(e)  => (e.currentTarget.style.borderColor = "rgba(0,212,255,0.18)")}
              placeholder="Search US routes…"
              disabled={isLocked}
              className="w-full rounded-lg px-3.5 py-2.5 text-slate-100 text-sm placeholder-slate-600
                         focus:outline-none disabled:opacity-40 transition-all duration-200"
              style={{
                background: "rgba(255,255,255,0.04)",
                border:     "1px solid rgba(0,212,255,0.18)",
                fontFamily: "inherit",
              }}
            />
          )}

          {/* ── Dropdown ── */}
          {dropdownOpen && !selected && !isLocked && (
            <div
              className="absolute z-50 w-full mt-1.5 rounded-xl overflow-y-auto"
              style={{
                background:    "rgba(5, 8, 16, 0.97)",
                backdropFilter:"blur(20px)",
                border:        "1px solid rgba(0,212,255,0.18)",
                boxShadow:     "0 16px 40px -8px rgba(0,0,0,0.7)",
                maxHeight:     "260px",
              }}
            >
              {grouped.length === 0 ? (
                <div className="px-4 py-3 text-sm text-slate-500 text-center">
                  No matching routes
                </div>
              ) : (
                grouped.map(({ region, routes }) => (
                  <div key={region}>
                    <div
                      className="px-3.5 pt-2.5 pb-1 text-[9px] uppercase tracking-[0.2em]"
                      style={{ color: "#334155" }}
                    >
                      {region}
                    </div>
                    {routes.map((r) => (
                      <button
                        key={r.api}
                        onMouseDown={(e) => { e.preventDefault(); pickRoute(r); }}
                        className="w-full flex items-center gap-2.5 px-3.5 py-2 text-left
                                   transition-colors duration-100 hover:bg-white/5"
                      >
                        <SeverityDot severity={r.severity} />
                        <span className="flex-1 text-sm text-slate-200 font-medium">{r.label}</span>
                        <span className="text-[11px] text-slate-500 hidden sm:inline shrink-0">{r.hint}</span>
                        <SeverityChip severity={r.severity} />
                      </button>
                    ))}
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* ── Departure time ────────────────────────────────── */}
        <div>
          <label className="block text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-1.5">
            Departure Time
          </label>
          <input
            type="time"
            value={departureTime}
            onChange={(e) => setDepartureTime(e.target.value)}
            disabled={isLocked}
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

        {/* ── Error ─────────────────────────────────────────── */}
        {error && (
          <div className="text-red-300 text-sm rounded-lg px-3.5 py-2.5"
               style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.25)" }}>
            {error}
          </div>
        )}

        {/* ── Scan button ───────────────────────────────────── */}
        {!isReady && (
          <button
            onClick={handlePlan}
            disabled={loading || !selected}
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
                <span style={{ color: "#00d4ff" }}>Scanning route…</span>
              </>
            ) : (
              <>⚡ Scan for Dead Zones</>
            )}
          </button>
        )}
      </div>

      {/* ── Results ───────────────────────────────────────────── */}
      {isReady && detectedZones.length > 0 && (
        <div className="mt-5 space-y-3 animate-[fadeInUp_0.35s_ease-out]">
          <div className="flex items-center gap-3">
            <div className="flex-1 h-px" style={{ background: "rgba(0,212,255,0.12)" }} />
            <span className="text-[10px] uppercase tracking-[0.2em] text-slate-500">
              {detectedZones.length} zone{detectedZones.length !== 1 ? "s" : ""} detected
            </span>
            <div className="flex-1 h-px" style={{ background: "rgba(0,212,255,0.12)" }} />
          </div>

          <div className="space-y-2">
            {detectedZones.map((zone, idx) => (
              <div
                key={zone.id}
                className="flex items-center gap-3 rounded-xl px-3.5 py-2.5"
                style={{
                  background:     "rgba(255,255,255,0.03)",
                  border:         "1px solid rgba(255,255,255,0.07)",
                  animationDelay: `${idx * 60}ms`,
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
            onClick={() => { clearSelection(); }}
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
