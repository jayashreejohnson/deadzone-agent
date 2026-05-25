"use client";
import { useState, useRef, useEffect } from "react";
import type { DeadZone } from "@/lib/route";

// ── Types ──────────────────────────────────────────────────────────────────
type Severity = "high" | "medium" | "low";
type Mode = "driving" | "transit";

type SubwayLine = {
  code:      string;            // "E", "A", "1", "BART", etc.
  color:     string;            // official hex
  textColor: "white" | "black";
};

type Route = {
  label:    string;
  api:      string;
  region:   string;
  hint:     string;
  severity: Severity;
  mode:     Mode;
  line?:    SubwayLine;
};

// ── Driving routes ─────────────────────────────────────────────────────────
const DRIVING_ROUTES: Route[] = [
  { label: "Manhattan → Newark",          api: "Manhattan to Newark",          region: "Northeast",  hint: "Lincoln Tunnel",                    severity: "high",   mode: "driving" },
  { label: "Washington DC → Baltimore",   api: "Washington DC to Baltimore",   region: "Northeast",  hint: "Baltimore Harbor Tunnel",            severity: "high",   mode: "driving" },
  { label: "New York → Philadelphia",     api: "New York to Philadelphia",     region: "Northeast",  hint: "NJ Turnpike underpasses",            severity: "medium", mode: "driving" },
  { label: "New York → Boston",           api: "New York to Boston",           region: "Northeast",  hint: "I-95 CT/RI coverage gaps",           severity: "medium", mode: "driving" },
  { label: "Atlanta → Charlotte",         api: "Atlanta to Charlotte",         region: "Southeast",  hint: "Blue Ridge mountain gaps",           severity: "high",   mode: "driving" },
  { label: "Miami → Orlando",             api: "Miami to Orlando",             region: "Southeast",  hint: "Everglades rural corridor",          severity: "medium", mode: "driving" },
  { label: "Denver → Vail",               api: "Denver to Vail",               region: "Mountain",   hint: "Eisenhower Tunnel + I-70 canyons",  severity: "high",   mode: "driving" },
  { label: "Phoenix → Sedona",            api: "Phoenix to Sedona",            region: "Mountain",   hint: "AZ-89A mountain switchbacks",        severity: "high",   mode: "driving" },
  { label: "Salt Lake City → Moab",       api: "Salt Lake City to Moab",       region: "Mountain",   hint: "US-191 canyon country",              severity: "high",   mode: "driving" },
  { label: "Los Angeles → Las Vegas",     api: "Los Angeles to Las Vegas",     region: "West",       hint: "Mojave Desert dead zones",           severity: "high",   mode: "driving" },
  { label: "Los Angeles → San Diego",     api: "Los Angeles to San Diego",     region: "West",       hint: "Camp Pendleton corridor",            severity: "medium", mode: "driving" },
  { label: "San Francisco → Los Angeles", api: "San Francisco to Los Angeles", region: "West",       hint: "Coastal I-5 remote stretches",       severity: "medium", mode: "driving" },
  { label: "Seattle → Spokane",           api: "Seattle to Spokane",           region: "Pacific NW", hint: "Cascade Mountain passes",            severity: "high",   mode: "driving" },
  { label: "Dallas → Houston",            api: "Dallas to Houston",            region: "South",      hint: "Rural I-45 Texas Hill Country",      severity: "medium", mode: "driving" },
];

// ── Transit routes — real lines, official MTA / agency colors ─────────────
const TRANSIT_ROUTES: Route[] = [
  // ── New York City Subway ──────────────────────────────────────────────
  {
    label: "E: Jamaica → World Trade Center",
    api:   "E train Jamaica Center to World Trade Center via NYC Subway",
    region: "New York", hint: "Midtown tunnel + Lower Manhattan underground",
    severity: "high", mode: "transit",
    line: { code: "E", color: "#0039A6", textColor: "white" },
  },
  {
    label: "A: Far Rockaway → Penn Station",
    api:   "A train Far Rockaway to Penn Station via NYC Subway",
    region: "New York", hint: "East River tunnel + Manhattan underground",
    severity: "high", mode: "transit",
    line: { code: "A", color: "#0039A6", textColor: "white" },
  },
  {
    label: "1: Van Cortlandt Park → South Ferry",
    api:   "1 train Van Cortlandt Park to South Ferry via NYC Subway",
    region: "New York", hint: "Entire Manhattan stretch underground",
    severity: "high", mode: "transit",
    line: { code: "1", color: "#EE352E", textColor: "white" },
  },
  {
    label: "L: Canarsie → 8th Ave",
    api:   "L train Canarsie to 8th Avenue via NYC Subway",
    region: "New York", hint: "Canarsie tunnel under East River",
    severity: "high", mode: "transit",
    line: { code: "L", color: "#A7A9AC", textColor: "black" },
  },
  {
    label: "N: Astoria → Bay Ridge",
    api:   "N train Astoria to Bay Ridge-95th Street via NYC Subway",
    region: "New York", hint: "Manhattan Bridge + 4th Ave tunnel",
    severity: "high", mode: "transit",
    line: { code: "N", color: "#FCCC0A", textColor: "black" },
  },
  {
    label: "7: Flushing → Hudson Yards",
    api:   "7 train Flushing Main Street to Hudson Yards via NYC Subway",
    region: "New York", hint: "Elevated in Queens → underground Midtown",
    severity: "medium", mode: "transit",
    line: { code: "7", color: "#B933AD", textColor: "white" },
  },
  // ── Boston MBTA ───────────────────────────────────────────────────────
  {
    label: "Red Line: Harvard → Braintree",
    api:   "Red Line Harvard Square to Braintree via Boston MBTA",
    region: "Boston", hint: "Charles River tunnel + downtown stations",
    severity: "high", mode: "transit",
    line: { code: "RL", color: "#DA291C", textColor: "white" },
  },
  {
    label: "Green Line: Lechmere → Heath St",
    api:   "Green Line Lechmere to Heath Street via Boston MBTA",
    region: "Boston", hint: "Boylston Street subway tunnel",
    severity: "medium", mode: "transit",
    line: { code: "GL", color: "#00843D", textColor: "white" },
  },
  // ── SF BART ───────────────────────────────────────────────────────────
  {
    label: "BART: Embarcadero → SFO",
    api:   "BART Embarcadero to SFO Airport via Bay Area Rapid Transit",
    region: "San Francisco", hint: "Transbay tube under the Bay",
    severity: "high", mode: "transit",
    line: { code: "BART", color: "#009AC7", textColor: "white" },
  },
  // ── Chicago CTA ───────────────────────────────────────────────────────
  {
    label: "Blue Line: O'Hare → Forest Park",
    api:   "Blue Line OHare to Forest Park via Chicago CTA",
    region: "Chicago", hint: "O'Hare tunnel + State St subway loop",
    severity: "high", mode: "transit",
    line: { code: "BL", color: "#00A1DE", textColor: "white" },
  },
  // ── DC Metro ──────────────────────────────────────────────────────────
  {
    label: "Red Line: Shady Grove → Glenmont",
    api:   "Red Line Shady Grove to Glenmont via DC Metro",
    region: "Washington DC", hint: "Dupont Circle + Gallery Pl underground",
    severity: "medium", mode: "transit",
    line: { code: "RED", color: "#BF0D3E", textColor: "white" },
  },
];

// ── Popular picks ──────────────────────────────────────────────────────────
const POPULAR_DRIVING: Route[] = [
  DRIVING_ROUTES.find(r => r.api === "Manhattan to Newark")!,
  DRIVING_ROUTES.find(r => r.api === "Los Angeles to Las Vegas")!,
  DRIVING_ROUTES.find(r => r.api === "Denver to Vail")!,
  DRIVING_ROUTES.find(r => r.api === "Phoenix to Sedona")!,
];

const POPULAR_TRANSIT: Route[] = [
  TRANSIT_ROUTES.find(r => r.line?.code === "E")!,
  TRANSIT_ROUTES.find(r => r.line?.code === "A")!,
  TRANSIT_ROUTES.find(r => r.line?.code === "L")!,
  TRANSIT_ROUTES.find(r => r.line?.code === "BART")!,
];

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

/** Colored subway / transit line pill — e.g. [E] in MTA blue */
function LinePill({ line }: { line: SubwayLine }) {
  const wide = line.code.length > 2;
  return (
    <span
      className="inline-flex items-center justify-center rounded font-bold shrink-0"
      style={{
        height:    22,
        minWidth:  22,
        width:     wide ? "auto" : 22,
        padding:   wide ? "0 5px" : 0,
        fontSize:  wide ? 9 : 11,
        background: line.color,
        color:     line.textColor === "black" ? "#000" : "#fff",
        letterSpacing: wide ? "0.04em" : 0,
      }}
    >
      {line.code}
    </span>
  );
}

/** Left-side indicator — LinePill for transit, SeverityDot for driving */
function RouteIcon({ route }: { route: Route }) {
  if (route.line) return <LinePill line={route.line} />;
  return <SeverityDot severity={route.severity} />;
}

// ── Main component ───────────────────────────────────────────────────────────

type TripPlannerProps = {
  onPlanComplete: (zones: DeadZone[], routeId: string, route: string) => void;
  onStartTrip: () => void;
  apiBase: string;
  planState: "idle" | "planning" | "ready";
};

export default function TripPlanner({ onPlanComplete, onStartTrip, apiBase, planState }: TripPlannerProps) {
  const [mode, setMode]                   = useState<Mode>("driving");
  const [selected, setSelected]           = useState<Route | null>(null);
  const [query, setQuery]                 = useState("");
  const [dropdownOpen, setDropdownOpen]   = useState(false);
  const [departureTime, setDepartureTime] = useState(getDefaultDepartureTime);
  const [loading, setLoading]             = useState(false);
  const [error, setError]                 = useState<string | null>(null);
  const [detectedZones, setDetectedZones] = useState<DeadZone[]>([]);

  const containerRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node))
        setDropdownOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Active routes for current mode
  const activeRoutes = mode === "driving" ? DRIVING_ROUTES : TRANSIT_ROUTES;
  const popularRoutes = mode === "driving" ? POPULAR_DRIVING : POPULAR_TRANSIT;

  // Filter + group by region
  const q = query.toLowerCase();
  const filtered = q
    ? activeRoutes.filter(r =>
        r.label.toLowerCase().includes(q) ||
        r.hint.toLowerCase().includes(q) ||
        r.region.toLowerCase().includes(q)
      )
    : activeRoutes;

  const regions = Array.from(new Set(activeRoutes.map(r => r.region)));
  const grouped = regions.flatMap(region => {
    const routes = filtered.filter(r => r.region === region);
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

  function switchMode(m: Mode) {
    setMode(m);
    clearSelection();
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

  const isReady  = planState === "ready" && detectedZones.length > 0;
  const isLocked = loading || isReady;

  return (
    <div
      className="w-full max-w-lg mx-auto rounded-2xl p-6 animate-[fadeInUp_0.4s_ease-out]"
      style={{
        background:     "rgba(5, 8, 16, 0.92)",
        backdropFilter: "blur(24px)",
        border:         "1px solid rgba(0, 212, 255, 0.2)",
        boxShadow:      "0 0 60px -10px rgba(0, 212, 255, 0.18), 0 32px 64px -24px rgba(0,0,0,0.8)",
      }}
    >
      {/* ── Header ── */}
      <div className="flex items-center gap-3 mb-4">
        <div
          className="w-9 h-9 rounded-lg flex items-center justify-center text-lg shrink-0"
          style={{ background: "rgba(0,212,255,0.1)", border: "1px solid rgba(0,212,255,0.25)" }}
        >
          🛰
        </div>
        <div>
          <h2 className="text-base font-semibold text-slate-100 tracking-tight">Route Dead Zone Scan</h2>
          <p className="text-[11px] text-slate-500 tracking-wide">Select a route — AI predicts coverage gaps</p>
        </div>
      </div>

      {/* ── Mode tabs: Driving / Transit ── */}
      {!isLocked && (
        <div
          className="flex rounded-lg p-0.5 mb-5"
          style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)" }}
        >
          {(["driving", "transit"] as Mode[]).map(m => (
            <button
              key={m}
              onClick={() => switchMode(m)}
              className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md text-sm font-medium transition-all duration-150"
              style={{
                background: mode === m ? "rgba(0,212,255,0.12)" : "transparent",
                color:      mode === m ? "#00d4ff" : "#475569",
                border:     mode === m ? "1px solid rgba(0,212,255,0.25)" : "1px solid transparent",
              }}
            >
              <span>{m === "driving" ? "🚗" : "🚇"}</span>
              <span className="capitalize">{m}</span>
            </button>
          ))}
        </div>
      )}

      <div className="space-y-4">
        {/* ── Popular chips ── */}
        {!isLocked && !selected && (
          <div>
            <p className="text-[10px] uppercase tracking-[0.15em] text-slate-600 mb-2">
              Popular {mode === "transit" ? "lines" : "routes"}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {popularRoutes.map(r => (
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
                  <RouteIcon route={r} />
                  {r.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── Combobox ── */}
        <div ref={containerRef} className="relative">
          <label className="block text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-1.5">
            {mode === "transit" ? "Line" : "Route"}
          </label>

          {selected ? (
            /* Selected state */
            <div
              className="flex items-center gap-2 rounded-lg px-3.5 py-2.5"
              style={{
                background: "rgba(0,212,255,0.06)",
                border:     "1px solid rgba(0,212,255,0.35)",
              }}
            >
              <RouteIcon route={selected} />
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
            /* Search input */
            <input
              type="text"
              value={query}
              onChange={e => { setQuery(e.target.value); setDropdownOpen(true); }}
              onFocus={e => { setDropdownOpen(true); e.currentTarget.style.borderColor = "rgba(0,212,255,0.5)"; }}
              onBlur={e  => (e.currentTarget.style.borderColor = "rgba(0,212,255,0.18)")}
              placeholder={mode === "transit" ? "Search transit lines…" : "Search routes…"}
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

          {/* Dropdown */}
          {dropdownOpen && !selected && !isLocked && (
            <div
              className="absolute z-50 w-full mt-1.5 rounded-xl overflow-y-auto"
              style={{
                background:     "rgba(5, 8, 16, 0.97)",
                backdropFilter: "blur(20px)",
                border:         "1px solid rgba(0,212,255,0.18)",
                boxShadow:      "0 16px 40px -8px rgba(0,0,0,0.7)",
                maxHeight:      "260px",
              }}
            >
              {grouped.length === 0 ? (
                <div className="px-4 py-3 text-sm text-slate-500 text-center">No matching routes</div>
              ) : (
                grouped.map(({ region, routes }) => (
                  <div key={region}>
                    <div
                      className="px-3.5 pt-2.5 pb-1 text-[9px] uppercase tracking-[0.2em]"
                      style={{ color: "#334155" }}
                    >
                      {region}
                    </div>
                    {routes.map(r => (
                      <button
                        key={r.api}
                        onMouseDown={e => { e.preventDefault(); pickRoute(r); }}
                        className="w-full flex items-center gap-2.5 px-3.5 py-2 text-left
                                   transition-colors duration-100 hover:bg-white/5"
                      >
                        <RouteIcon route={r} />
                        <span className="flex-1 text-sm text-slate-200 font-medium">{r.label}</span>
                        <span className="text-[11px] text-slate-500 hidden sm:inline shrink-0">{r.hint}</span>
                        {!r.line && <SeverityChip severity={r.severity} />}
                      </button>
                    ))}
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* ── Departure time ── */}
        <div>
          <label className="block text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-1.5">
            Departure Time
          </label>
          <input
            type="time"
            value={departureTime}
            onChange={e => setDepartureTime(e.target.value)}
            disabled={isLocked}
            className="w-full rounded-lg px-3.5 py-2.5 text-slate-100 text-sm
                       focus:outline-none disabled:opacity-40 transition-all duration-200"
            style={{
              background:  "rgba(255,255,255,0.04)",
              border:      "1px solid rgba(0,212,255,0.18)",
              fontFamily:  "inherit",
              colorScheme: "dark",
            }}
            onFocus={e => (e.currentTarget.style.borderColor = "rgba(0,212,255,0.5)")}
            onBlur={e  => (e.currentTarget.style.borderColor = "rgba(0,212,255,0.18)")}
          />
        </div>

        {/* ── Error ── */}
        {error && (
          <div className="text-red-300 text-sm rounded-lg px-3.5 py-2.5"
               style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.25)" }}>
            {error}
          </div>
        )}

        {/* ── Scan button ── */}
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

      {/* ── Results ── */}
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
            {mode === "transit" ? "🚇" : "🚗"} Start Trip
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
