"use client";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import PackModal from "@/components/PackModal";
import LiveLogs, { type AgentEvent } from "@/components/LiveLogs";
import Dashboard from "@/components/Dashboard";
import Toast from "@/components/Toast";
import OfflinePill from "@/components/OfflinePill";
import { AlertCard, PreparingCard, CachedFoundCard, ReadyCard } from "@/components/OverlayCard";
import TripPlanner from "@/components/TripPlanner";
import CountdownBanner from "@/components/CountdownBanner";
import OfflineOverlay from "@/components/OfflineOverlay";
import {
  ROUTE_ID, DEFAULT_ROUTE_POLYLINE, DEFAULT_DEAD_ZONES,
  distanceKm, lerp, type LatLng, type DeadZone,
} from "@/lib/route";

const Map = dynamic(() => import("@/components/Map"), { ssr: false });

const API    = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const WS_URL = API.replace(/^https:\/\//, "wss://").replace(/^http:\/\//, "ws://") + "/ws";

type User    = "user_a" | "user_b";
type Overlay =
  | { kind: "none" }
  | { kind: "alert"; deadzoneName: string; etaSeconds: number; confidence: number }
  | { kind: "preparing" }
  | { kind: "cached_found" }
  | { kind: "ready"; url: string; cached: boolean; paidAmount?: number };

type ToastItem =
  | { id: number; variant: "payment"; detail: string }
  | { id: number; variant: "reconnecting" }
  | { id: number; variant: "synced" };

type TripState = {
  pos: LatLng | null; segIdx: number; segT: number;
  running: boolean; insideZone: string | null;
  triggered: Set<string>;
};

type PlanState = "idle" | "planning" | "ready" | "tripping";

const STEP_MS       = 350;
const STEP_PROGRESS = 0.07;

function buildRoutePolyline(zones: DeadZone[]): LatLng[] {
  if (zones.length === 0) return DEFAULT_ROUTE_POLYLINE;
  const first = zones[0];
  const last  = zones[zones.length - 1];
  return [
    { lat: first.lat - 0.05, lng: first.lng - 0.05 },
    ...zones.map((z) => ({ lat: z.lat, lng: z.lng })),
    { lat: last.lat + 0.03, lng: last.lng + 0.05 },
  ];
}

let _toastSeq = 1;

export default function Page() {
  const [activeUser, setActiveUser] = useState<User>("user_a");

  // Plan / trip state
  const [planState, setPlanState]         = useState<PlanState>("idle");
  const [plannedZones, setPlannedZones]   = useState<DeadZone[]>(DEFAULT_DEAD_ZONES);
  const [routePolyline, setRoutePolyline] = useState<LatLng[]>(DEFAULT_ROUTE_POLYLINE);
  const [routeId, setRouteId]             = useState<string>(ROUTE_ID);
  const [routeName, setRouteName]         = useState<string>("");
  const [nextZone, setNextZone]           = useState<DeadZone | null>(null);
  const [countdownSeconds, setCountdownSeconds] = useState<number | null>(null);
  const [zonePackStatus, setZonePackStatus]     = useState<Record<string, "preparing" | "ready" | "cached">>({});
  const [offlineZone, setOfflineZone]           = useState<DeadZone | null>(null);
  const [offlineSimDuration, setOfflineSimDuration] = useState<number>(0);
  const [showOfflineOverlay, setShowOfflineOverlay] = useState(false);

  // UI panels
  const [logOpen, setLogOpen] = useState(true);

  const initialTrip = useCallback(
    (): TripState => ({
      pos: routePolyline[0], segIdx: 0, segT: 0,
      running: false, insideZone: null, triggered: new Set(),
    }),
    [routePolyline]
  );

  const [trips, setTrips] = useState<Record<User, TripState>>({
    user_a: { pos: DEFAULT_ROUTE_POLYLINE[0], segIdx: 0, segT: 0, running: false, insideZone: null, triggered: new Set() },
    user_b: { pos: DEFAULT_ROUTE_POLYLINE[0], segIdx: 0, segT: 0, running: false, insideZone: null, triggered: new Set() },
  });

  const [events, setEvents]           = useState<AgentEvent[]>([]);
  const [overlay, setOverlay]         = useState<Overlay>({ kind: "none" });
  const [toasts, setToasts]           = useState<ToastItem[]>([]);
  const [offlineActive, setOfflineActive] = useState(false);
  const [packModalOpen, setPackModalOpen] = useState(false);
  const [lastPack, setLastPack]           = useState<{
    url: string; cached: boolean; paidAmount?: number; html?: string | null
  } | null>(null);

  void initialTrip; // suppress unused warning

  // ── Countdown timer ───────────────────────────────────────────
  useEffect(() => {
    if (planState !== "tripping" || countdownSeconds === null) return;
    if (countdownSeconds <= 0) {
      const zone = nextZone || plannedZones[0];
      if (zone) {
        setOfflineZone(zone);
        const simDuration = Math.round((zone.duration_minutes || 4) * 60 * 0.3);
        setOfflineSimDuration(Math.max(simDuration, 5));
        setShowOfflineOverlay(true);
        setOfflineActive(true);
      }
      return;
    }
    const id = setTimeout(() => setCountdownSeconds((s) => (s !== null ? s - 1 : null)), 1000);
    return () => clearTimeout(id);
  }, [planState, countdownSeconds, nextZone, plannedZones]);

  // ── WebSocket ─────────────────────────────────────────────────
  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnect: ReturnType<typeof setTimeout> | undefined;
    const lastPaymentRef = { current: null as { amount: number; from: string; to: string } | null };

    const connect = () => {
      ws = new WebSocket(WS_URL);
      ws.onmessage = (e) => {
        try {
          const ev = JSON.parse(e.data) as Record<string, unknown> & { type: string };
          setEvents((prev) => [...prev.slice(-200), ev]);

          if (ev.type === "zones_ready" && Array.isArray(ev.zones)) {
            const zones: DeadZone[] = (ev.zones as Record<string, unknown>[]).map((z) => ({
              id:               String(z.id || "zone"),
              name:             String(z.description || z.name || z.id || "Dead zone"),
              lat:              Number(z.lat),
              lng:              Number(z.lng),
              radius_km:        Number(z.radius_km || 0.6),
              duration_minutes: z.duration_minutes ? Number(z.duration_minutes) : undefined,
              severity:         (z.severity as DeadZone["severity"]) || "medium",
            }));
            setPlannedZones(zones);
            setRoutePolyline(buildRoutePolyline(zones));
          }

          if (ev.type === "payment") {
            const payment = { amount: Number(ev.amount), from: String(ev.from), to: String(ev.to) };
            lastPaymentRef.current = payment;
            setOverlay((cur) =>
              cur.kind === "alert" || cur.kind === "preparing" ? { kind: "cached_found" } : cur
            );
            pushToast({
              id: _toastSeq++, variant: "payment",
              detail: `${ev.from} → ${ev.to}  $${Number(ev.amount).toFixed(2)}`,
            });
          } else if (ev.type === "pack_ready") {
            const paidAmount  = ev.cached ? lastPaymentRef.current?.amount : undefined;
            const deadzoneId  = String(ev.deadzone_id || routeId);
            const pack = { url: String(ev.url), cached: !!ev.cached, paidAmount, html: null as string | null };
            setLastPack(pack);
            setOverlay({ kind: "ready", url: String(ev.url), cached: !!ev.cached, paidAmount });
            setZonePackStatus((prev) => ({ ...prev, [deadzoneId]: ev.cached ? "cached" : "ready" }));
            fetch(String(ev.url))
              .then((r) => r.text())
              .then((html) => setLastPack((p) => (p && p.url === ev.url ? { ...p, html } : p)))
              .catch(() => {});
          }
        } catch { /* Ignore malformed messages */ }
      };
      ws.onerror  = () => { ws?.close(); };
      ws.onclose  = () => { reconnect = setTimeout(connect, 1500); };
    };
    connect();
    return () => { clearTimeout(reconnect); ws?.close(); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Zone entry handling ───────────────────────────────────────
  type ZoneEntry = { user: User; pos: LatLng; dzId: string; dzName: string; zone: DeadZone };
  const pendingZoneEntries = useRef<ZoneEntry[]>([]);

  const handleZoneEnter = useCallback((user: User, pos: LatLng, dzId: string, dzName: string, zone: DeadZone) => {
    setOverlay({ kind: "alert", deadzoneName: dzName, etaSeconds: (zone.duration_minutes || 4) * 60, confidence: 92 });
    setTimeout(() => {
      setOverlay((cur) => cur.kind === "alert" ? { kind: "preparing" } : cur);
    }, 1600);
    setZonePackStatus((prev) => ({ ...prev, [dzId]: "preparing" }));

    fetch(`${API}/signal`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        user_id: user, lat: pos.lat, lng: pos.lng,
        eta_seconds:      (zone.duration_minutes || 4) * 60,
        route_id:         routeId,
        deadzone_id:      dzId,
        duration_minutes: zone.duration_minutes || 4,
        severity:         zone.severity || "medium",
        zone_description: zone.name,
        route:            routeName,
      }),
    }).catch(() => {});
    setOfflineActive(true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeId, routeName]);

  // ── Animation loop ────────────────────────────────────────────
  const routePolylineRef = useRef(routePolyline);
  useEffect(() => { routePolylineRef.current = routePolyline; }, [routePolyline]);
  const plannedZonesRef = useRef(plannedZones);
  useEffect(() => { plannedZonesRef.current = plannedZones; }, [plannedZones]);

  useEffect(() => {
    const id = setInterval(() => {
      setTrips((prev) => {
        const next = { ...prev };
        (["user_a", "user_b"] as User[]).forEach((u) => {
          const t = prev[u];
          if (!t.running) return;
          const poly = routePolylineRef.current;
          let segIdx = t.segIdx, segT = t.segT + STEP_PROGRESS;
          while (segT >= 1 && segIdx < poly.length - 2) { segT -= 1; segIdx += 1; }
          const atEnd = segIdx >= poly.length - 2 && segT >= 1;
          const pos   = atEnd ? poly[poly.length - 1] : lerp(poly[segIdx], poly[segIdx + 1], segT);

          const zones    = plannedZonesRef.current;
          const triggered = new Set(t.triggered);
          let insideZone: string | null = null;
          let justEntered = false;
          let enteredZone: DeadZone | null = null;

          for (const dz of zones) {
            if (distanceKm(pos, { lat: dz.lat, lng: dz.lng }) <= dz.radius_km) {
              insideZone = dz.id;
              if (!triggered.has(dz.id)) {
                triggered.add(dz.id);
                justEntered = true;
                enteredZone = dz;
                pendingZoneEntries.current.push({ user: u, pos, dzId: dz.id, dzName: dz.name, zone: dz });
              }
              break;
            }
          }
          next[u] = { ...t, segIdx, segT: atEnd ? 1 : segT, pos, insideZone, triggered, running: !atEnd && !justEntered };
          void enteredZone;
        });
        return next;
      });
    }, STEP_MS);
    return () => clearInterval(id);
  }, []);

  // Drain pending zone entries
  useEffect(() => {
    const entries = pendingZoneEntries.current.splice(0);
    entries.forEach(({ user, pos, dzId, dzName, zone }) =>
      handleZoneEnter(user, pos, dzId, dzName, zone)
    );
  });

  function pushToast(t: ToastItem) { setToasts((arr) => [...arr, t]); }
  function dropToast(id: number)   { setToasts((arr) => arr.filter((t) => t.id !== id)); }

  // ── Plan complete ─────────────────────────────────────────────
  function handlePlanComplete(zones: DeadZone[], rid: string, route: string) {
    setPlannedZones(zones.length > 0 ? zones : DEFAULT_DEAD_ZONES);
    setRouteId(rid);
    setRouteName(route);
    setPlanState("ready");
    setRoutePolyline(buildRoutePolyline(zones.length > 0 ? zones : DEFAULT_DEAD_ZONES));
    setNextZone(zones[0] || null);
  }

  // ── Start trip ────────────────────────────────────────────────
  function handleStartTrip() {
    const zones = plannedZones.length > 0 ? plannedZones : DEFAULT_DEAD_ZONES;
    const poly  = buildRoutePolyline(zones);
    setRoutePolyline(poly);
    setPlanState("tripping");
    setOverlay({ kind: "none" });
    setOfflineActive(false);
    setToasts([]);
    setEvents([]);
    setShowOfflineOverlay(false);
    setOfflineZone(null);
    setCountdownSeconds(45);
    setNextZone(zones[0] || null);
    setZonePackStatus({});
    const startPos = poly[0];
    setTrips({
      user_a: { pos: startPos, segIdx: 0, segT: 0, running: true,  insideZone: null, triggered: new Set() },
      user_b: { pos: startPos, segIdx: 0, segT: 0, running: false, insideZone: null, triggered: new Set() },
    });
    setActiveUser("user_a");
  }

  // ── Legacy per-user controls ──────────────────────────────────
  function startTrip(u: User) {
    setOverlay({ kind: "none" });
    setOfflineActive(false);
    setToasts([]);
    setEvents([]);
    const poly = routePolyline;
    setTrips((p) => ({
      ...p,
      [u]: { pos: poly[0], segIdx: 0, segT: 0, running: true, insideZone: null, triggered: new Set() },
    }));
    setActiveUser(u);
    if (planState === "idle") {
      setPlanState("tripping");
      setNextZone(plannedZones[0] || null);
      setCountdownSeconds(45);
    }
  }
  function resetTrip(u: User) {
    setTrips((p) => ({
      ...p,
      [u]: { pos: routePolyline[0], segIdx: 0, segT: 0, running: false, insideZone: null, triggered: new Set() },
    }));
    setOverlay({ kind: "none" });
    setOfflineActive(false);
    setToasts([]);
  }

  // ── Offline sim done ──────────────────────────────────────────
  function handleOfflineDone() {
    setShowOfflineOverlay(false);
    setOfflineActive(false);
    setOfflineZone(null);
    pushToast({ id: _toastSeq++, variant: "synced" });
  }

  const dots = useMemo(
    () => (["user_a", "user_b"] as User[]).map((u) => ({ user: u, pos: trips[u].pos })),
    [trips]
  );

  const showPlanner    = planState === "idle" || planState === "planning" || planState === "ready";
  const showCountdown  = planState === "tripping" && nextZone !== null && countdownSeconds !== null;
  const currentPackStatus: "preparing" | "ready" | "cached" =
    nextZone ? (zonePackStatus[nextZone.id] || "preparing") : "preparing";

  // ── LOG_DRAWER_WIDTH ─────────────────────────────────────────
  const LOG_W = 300;

  // ── Render ────────────────────────────────────────────────────
  return (
    <div className="relative h-screen overflow-hidden" style={{ background: "#050810" }}>

      {/* ── Ambient glow orbs ─────────────────────────────────── */}
      <div
        className="pointer-events-none absolute -top-40 -left-40 w-[700px] h-[700px] rounded-full"
        style={{ background: "radial-gradient(circle, rgba(0,212,255,0.06) 0%, transparent 65%)" }}
      />
      <div
        className="pointer-events-none absolute -bottom-40 -right-40 w-[600px] h-[600px] rounded-full"
        style={{ background: "radial-gradient(circle, rgba(139,92,246,0.05) 0%, transparent 65%)" }}
      />

      {/* ── Full-bleed map ────────────────────────────────────── */}
      <div className="absolute inset-0">
        <Map
          dots={dots}
          activeUser={activeUser}
          deadZones={plannedZones}
          routePolyline={routePolyline}
          nextZone={nextZone}
        />
      </div>

      {/* ── Top navigation bar ────────────────────────────────── */}
      <div
        className="absolute top-0 left-0 right-0 z-[1100] px-4 py-2.5 flex items-center justify-between"
        style={{
          background:    "rgba(5, 8, 16, 0.88)",
          backdropFilter:"blur(18px)",
          borderBottom:  "1px solid rgba(0, 212, 255, 0.12)",
          boxShadow:     "0 1px 40px rgba(0,0,0,0.4)",
        }}
      >
        {/* Left — logo */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
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
            <span
              className="text-[10px] tracking-widest uppercase px-1.5 py-0.5 rounded"
              style={{ background: "rgba(0,212,255,0.1)", color: "#00d4ff", border: "1px solid rgba(0,212,255,0.2)" }}
            >
              Neural
            </span>
          </div>
          <span className="text-xs text-slate-600 hidden md:block tracking-wide">
            live · autonomous
          </span>
        </div>

        {/* Right — controls */}
        <div className="flex items-center gap-1.5">
          {/* User switcher */}
          {(["user_a", "user_b"] as User[]).map((u) => (
            <button
              key={u}
              onClick={() => setActiveUser(u)}
              className="px-2.5 py-1 text-xs rounded-lg font-medium transition-all duration-200"
              style={
                activeUser === u
                  ? u === "user_a"
                    ? { background: "rgba(0,212,255,0.15)", color: "#00d4ff", border: "1px solid rgba(0,212,255,0.3)" }
                    : { background: "rgba(139,92,246,0.15)", color: "#a78bfa", border: "1px solid rgba(139,92,246,0.3)" }
                  : { background: "rgba(255,255,255,0.05)", color: "#64748b", border: "1px solid rgba(255,255,255,0.07)" }
              }
            >
              {u}
            </button>
          ))}

          {/* Trip controls */}
          {planState === "tripping" && (
            <>
              <button
                onClick={() => startTrip(activeUser)}
                className="ml-1.5 px-2.5 py-1 text-xs rounded-lg font-medium transition-all duration-200"
                style={{ background: "rgba(0,212,255,0.12)", color: "#00d4ff", border: "1px solid rgba(0,212,255,0.25)" }}
              >
                ▶ restart
              </button>
              <button
                onClick={() => resetTrip(activeUser)}
                className="px-2.5 py-1 text-xs rounded-lg font-medium transition-all duration-200"
                style={{ background: "rgba(255,255,255,0.05)", color: "#64748b", border: "1px solid rgba(255,255,255,0.07)" }}
              >
                reset
              </button>
            </>
          )}
          {planState !== "tripping" && (
            <button
              onClick={() => { setPlanState("idle"); setPlannedZones(DEFAULT_DEAD_ZONES); setRoutePolyline(DEFAULT_ROUTE_POLYLINE); }}
              className="ml-1.5 px-2.5 py-1 text-xs rounded-lg font-medium transition-all duration-200"
              style={{ background: "rgba(255,255,255,0.05)", color: "#64748b", border: "1px solid rgba(255,255,255,0.07)" }}
            >
              new trip
            </button>
          )}

          {/* Log toggle */}
          <button
            onClick={() => setLogOpen((v) => !v)}
            className="ml-1.5 px-2.5 py-1 text-xs rounded-lg font-medium transition-all duration-200 flex items-center gap-1.5"
            style={
              logOpen
                ? { background: "rgba(0,212,255,0.12)", color: "#00d4ff", border: "1px solid rgba(0,212,255,0.25)" }
                : { background: "rgba(255,255,255,0.05)", color: "#64748b", border: "1px solid rgba(255,255,255,0.07)" }
            }
          >
            <span>⚡</span>
            <span className="hidden sm:inline">Log</span>
            <span>{logOpen ? "›" : "‹"}</span>
          </button>
        </div>
      </div>

      {/* ── Trip planner modal ────────────────────────────────── */}
      {showPlanner && (
        <div
          className="absolute inset-0 z-[1500] flex items-center justify-center p-6"
          style={{ background: "rgba(5,8,16,0.7)", backdropFilter: "blur(4px)" }}
        >
          <TripPlanner
            onPlanComplete={handlePlanComplete}
            onStartTrip={handleStartTrip}
            apiBase={API}
            planState={planState === "planning" ? "planning" : planState === "ready" ? "ready" : "idle"}
          />
        </div>
      )}

      {/* ── Countdown banner ──────────────────────────────────── */}
      {showCountdown && !showOfflineOverlay && (
        <div
          className="absolute left-4 z-[1200] transition-all duration-300"
          style={{
            top:   "4.5rem",
            right: logOpen ? `${LOG_W + 16}px` : "1rem",
          }}
        >
          <CountdownBanner
            zone={nextZone!}
            secondsUntil={countdownSeconds!}
            packStatus={currentPackStatus}
          />
        </div>
      )}

      {/* ── Center overlay cards ──────────────────────────────── */}
      {overlay.kind !== "none" && !showPlanner && !showOfflineOverlay && (
        <div
          className="absolute z-[1200] flex justify-center transition-all duration-300"
          style={{
            top:   showCountdown ? "8rem" : "5rem",
            left:  "1rem",
            right: logOpen ? `${LOG_W + 16}px` : "1rem",
          }}
        >
          <div style={{ width: "100%", maxWidth: "520px" }}>
            {overlay.kind === "alert" && (
              <AlertCard
                deadzoneName={overlay.deadzoneName}
                etaSeconds={overlay.etaSeconds}
                confidence={overlay.confidence}
                onPrepare={() => setOverlay({ kind: "preparing" })}
                onSwitch={() => setOverlay({ kind: "none" })}
                onStay={() => setOverlay({ kind: "preparing" })}
              />
            )}
            {overlay.kind === "preparing"    && <PreparingCard />}
            {overlay.kind === "cached_found" && <CachedFoundCard />}
            {overlay.kind === "ready" && (
              <ReadyCard
                cached={overlay.cached}
                paidAmount={overlay.paidAmount}
                onOpen={() => setPackModalOpen(true)}
              />
            )}
          </div>
        </div>
      )}

      {/* ── Toasts ────────────────────────────────────────────── */}
      <div className="absolute top-16 z-[1300] flex flex-col gap-2" style={{ right: logOpen ? `${LOG_W + 12}px` : "1rem" }}>
        {toasts.map((t) => (
          <Toast
            key={t.id}
            variant={t.variant}
            detail={"detail" in t ? t.detail : undefined}
            onDismiss={() => dropToast(t.id)}
          />
        ))}
      </div>

      {/* ── Offline pill ──────────────────────────────────────── */}
      {offlineActive && !showOfflineOverlay && (
        <div className="absolute bottom-14 left-4 z-[1200]">
          <OfflinePill />
        </div>
      )}

      {/* ── Agent log drawer (right side) ─────────────────────── */}
      <div
        className="absolute top-11 bottom-11 right-0 z-[1050] flex flex-col"
        style={{
          width:     `${LOG_W}px`,
          background:"rgba(5, 8, 16, 0.94)",
          backdropFilter: "blur(18px)",
          borderLeft: "1px solid rgba(0, 212, 255, 0.1)",
          transform: logOpen ? "translateX(0)" : `translateX(${LOG_W}px)`,
          transition:"transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
        }}
      >
        <LiveLogs events={events} />
      </div>

      {/* ── Dashboard strip (bottom) ──────────────────────────── */}
      <div className="absolute bottom-0 left-0 right-0 z-[1050]">
        <Dashboard />
      </div>

      {/* ── Offline simulation overlay ────────────────────────── */}
      {showOfflineOverlay && offlineZone && (
        <OfflineOverlay
          durationSeconds={offlineSimDuration}
          onDone={handleOfflineDone}
        />
      )}

      {/* ── Pack modal ────────────────────────────────────────── */}
      {packModalOpen && lastPack && (
        <PackModal
          url={lastPack.url}
          html={lastPack.html}
          cached={lastPack.cached}
          paidAmount={lastPack.paidAmount}
          onClose={() => setPackModalOpen(false)}
        />
      )}
    </div>
  );
}
