"use client";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import PackModal from "@/components/PackModal";
import LiveLogs, { type AgentEvent } from "@/components/LiveLogs";
import Dashboard from "@/components/Dashboard";
import Toast from "@/components/Toast";
import OfflinePill from "@/components/OfflinePill";
import { AlertCard, PreparingCard, CachedFoundCard, ReadyCard } from "@/components/OverlayCard";
import {
  ROUTE_ID, ROUTE_POLYLINE, DEAD_ZONES, distanceKm, lerp, type LatLng,
} from "@/lib/route";

const Map = dynamic(() => import("@/components/Map"), { ssr: false });

const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
// Ensure wss:// for https:// backends and ws:// for http:// backends.
const WS_URL = API.replace(/^https:\/\//, "wss://").replace(/^http:\/\//, "ws://") + "/ws";

type User = "user_a" | "user_b";
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

const STEP_MS = 350;
const STEP_PROGRESS = 0.07;

const initialTrip = (): TripState => ({
  pos: ROUTE_POLYLINE[0], segIdx: 0, segT: 0,
  running: false, insideZone: null, triggered: new Set(),
});

let _toastSeq = 1;

export default function Page() {
  const [activeUser, setActiveUser] = useState<User>("user_a");
  const [trips, setTrips] = useState<Record<User, TripState>>({
    user_a: initialTrip(), user_b: initialTrip(),
  });

  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [overlay, setOverlay] = useState<Overlay>({ kind: "none" });
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [offlineActive, setOfflineActive] = useState(false);
  const [packModalOpen, setPackModalOpen] = useState(false);
  const [lastPack, setLastPack] = useState<{ url: string; cached: boolean; paidAmount?: number; html?: string | null } | null>(null);

  // ---- WebSocket: drive overlays/toasts/logs from server events ----
  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnect: ReturnType<typeof setTimeout> | undefined;
    // lastPaymentRef lets the pack_ready handler read the latest payment without
    // needing lastPayment in the effect deps (which would cause reconnect churn).
    const lastPaymentRef = { current: null as { amount: number; from: string; to: string } | null };

    const connect = () => {
      ws = new WebSocket(WS_URL);
      ws.onmessage = (e) => {
        try {
          const ev = JSON.parse(e.data) as Record<string, unknown> & { type: string };
          setEvents((prev) => [...prev.slice(-200), ev]);

          if (ev.type === "payment") {
            // Cache-hit detection: payment arrives → switch overlay if still in alert/preparing
            const payment = { amount: Number(ev.amount), from: String(ev.from), to: String(ev.to) };
            lastPaymentRef.current = payment;
            setOverlay((cur) =>
              cur.kind === "alert" || cur.kind === "preparing"
                ? { kind: "cached_found" }
                : cur
            );
            pushToast({
              id: _toastSeq++, variant: "payment",
              detail: `${ev.from} → ${ev.to}  $${Number(ev.amount).toFixed(2)}`,
            });
          } else if (ev.type === "pack_ready") {
            const paidAmount = ev.cached ? (lastPaymentRef.current?.amount) : undefined;
            const pack = {
              url: String(ev.url), cached: !!ev.cached,
              paidAmount,
              html: null as string | null,
            };
            setLastPack(pack);
            setOverlay({
              kind: "ready", url: String(ev.url), cached: !!ev.cached,
              paidAmount,
            });
            // Pre-fetch the pack HTML and cache it client-side so the modal
            // can render even if the network drops afterwards.
            fetch(String(ev.url))
              .then((r) => r.text())
              .then((html) =>
                setLastPack((p) => (p && p.url === ev.url ? { ...p, html } : p))
              )
              .catch(() => {});
          }
        } catch {
          // Ignore malformed WebSocket messages
        }
      };
      ws.onerror = () => {
        // Errors are followed by a close event; close handler manages reconnect.
        // Explicitly close to ensure the onclose handler fires consistently.
        ws?.close();
      };
      ws.onclose = () => { reconnect = setTimeout(connect, 1500); };
    };
    connect();
    return () => { clearTimeout(reconnect); ws?.close(); };
  }, []);

  // Pending zone-enter side effects collected by the animation loop.
  // Using a ref avoids triggering re-renders and lets us fire side effects
  // outside the setState updater (which must be pure).
  type ZoneEntry = { user: User; pos: LatLng; dzId: string; dzName: string };
  const pendingZoneEntries = useRef<ZoneEntry[]>([]);

  // ---- Zone enter handler (fires side-effects; safe to call outside updater) ----
  const handleZoneEnter = useCallback((user: User, pos: LatLng, dzId: string, dzName: string) => {
    setOverlay({ kind: "alert", deadzoneName: dzName, etaSeconds: 192, confidence: 92 });
    // Auto-advance to preparing after 1.6s (unless cache-hit payment lands first)
    setTimeout(() => {
      setOverlay((cur) => cur.kind === "alert" ? { kind: "preparing" } : cur);
    }, 1600);
    // Fire signal to backend
    fetch(`${API}/signal`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: user, lat: pos.lat, lng: pos.lng,
        eta_seconds: 240, route_id: ROUTE_ID, deadzone_id: dzId,
      }),
    }).catch(() => {});
    setOfflineActive(true);
  }, []);

  // ---- Animation loop ----
  // The setState updater must be pure — it only mutates trip state and enqueues
  // zone-entry records into a ref. Side effects run in the effect below.
  useEffect(() => {
    const id = setInterval(() => {
      setTrips((prev) => {
        const next = { ...prev };
        (["user_a", "user_b"] as User[]).forEach((u) => {
          const t = prev[u];
          if (!t.running) return;
          let segIdx = t.segIdx, segT = t.segT + STEP_PROGRESS;
          while (segT >= 1 && segIdx < ROUTE_POLYLINE.length - 2) {
            segT -= 1; segIdx += 1;
          }
          const atEnd = segIdx >= ROUTE_POLYLINE.length - 2 && segT >= 1;
          const pos = atEnd
            ? ROUTE_POLYLINE[ROUTE_POLYLINE.length - 1]
            : lerp(ROUTE_POLYLINE[segIdx], ROUTE_POLYLINE[segIdx + 1], segT);

          // Zone enter detection — only enqueue, do NOT call side-effects here
          const triggered = new Set(t.triggered);
          let insideZone: string | null = null;
          let justEntered = false;
          for (const dz of DEAD_ZONES) {
            const d = distanceKm(pos, { lat: dz.lat, lng: dz.lng });
            if (d <= dz.radius_km) {
              insideZone = dz.id;
              if (!triggered.has(dz.id)) {
                triggered.add(dz.id);
                justEntered = true;
                pendingZoneEntries.current.push({ user: u, pos, dzId: dz.id, dzName: dz.name });
              }
              break;
            }
          }
          // Park the dot inside the first zone it enters — gives the demo time
          // for the Ready card / Open Continuity Pack interaction.
          next[u] = {
            ...t, segIdx, segT: atEnd ? 1 : segT,
            pos, insideZone, triggered,
            running: !atEnd && !justEntered,
          };
        });
        return next;
      });
    }, STEP_MS);
    return () => clearInterval(id);
  }, []);

  // Drain pending zone entries and fire side effects after each render tick.
  useEffect(() => {
    const entries = pendingZoneEntries.current.splice(0);
    entries.forEach(({ user, pos, dzId, dzName }) =>
      handleZoneEnter(user, pos, dzId, dzName)
    );
  });

  // (handleZoneExit removed — the dot parks inside the zone, never exits in the demo)

  function pushToast(t: ToastItem) {
    setToasts((arr) => [...arr, t]);
  }
  function dropToast(id: number) {
    setToasts((arr) => arr.filter((t) => t.id !== id));
  }

  // ---- Trip control ----
  function startTrip(u: User) {
    setOverlay({ kind: "none" });
    setOfflineActive(false);
    setToasts([]);                  // clear any stale toasts
    setEvents([]);                  // fresh log per trip
    setTrips((p) => ({ ...p, [u]: { ...initialTrip(), running: true } }));
    setActiveUser(u);
  }
  function resetTrip(u: User) {
    setTrips((p) => ({ ...p, [u]: initialTrip() }));
    setOverlay({ kind: "none" });
    setOfflineActive(false);
    setToasts([]);
  }

  const dots = useMemo(
    () => (["user_a", "user_b"] as User[]).map((u) => ({ user: u, pos: trips[u].pos })),
    [trips]
  );

  // ----------- Render -----------
  return (
    <div className="flex flex-col h-screen">
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-slate-900 border-b border-slate-800 shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="font-semibold text-slate-100">DeadZone Agent</span>
          </div>
          <span className="text-xs text-slate-500">intelligent navigation · live</span>
        </div>
        <div className="flex items-center gap-1">
          {(["user_a", "user_b"] as User[]).map((u) => (
            <button key={u} onClick={() => setActiveUser(u)}
              className={`px-3 py-1 text-sm rounded ${
                activeUser === u
                  ? (u === "user_a" ? "bg-emerald-500 text-white" : "bg-violet-500 text-white")
                  : "bg-slate-800 text-slate-300 hover:bg-slate-700"
              }`}>
              {u}
            </button>
          ))}
          <button onClick={() => startTrip(activeUser)}
            className="ml-3 px-3 py-1 text-sm rounded bg-sky-500 text-white hover:bg-sky-400">
            ▶ Start trip ({activeUser})
          </button>
          <button onClick={() => resetTrip(activeUser)}
            className="px-3 py-1 text-sm rounded bg-slate-800 text-slate-300 hover:bg-slate-700">
            reset
          </button>
        </div>
      </div>

      {/* Main */}
      <div className="flex flex-1 min-h-0 relative">
        <div className="flex-[3] min-h-0 relative">
          <Map dots={dots} activeUser={activeUser} />

          {/* Center overlay card */}
          {overlay.kind !== "none" && (
            <div className="absolute top-6 left-1/2 -translate-x-1/2 z-[1200] w-[min(520px,90%)]">
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
              {overlay.kind === "preparing" && <PreparingCard />}
              {overlay.kind === "cached_found" && <CachedFoundCard />}
              {overlay.kind === "ready" && (
                <ReadyCard
                  cached={overlay.cached}
                  paidAmount={overlay.paidAmount}
                  onOpen={() => setPackModalOpen(true)}
                />
              )}
            </div>
          )}

          {/* Toasts (top-right stack) */}
          <div className="absolute top-6 right-6 z-[1200] flex flex-col gap-2">
            {toasts.map((t) => (
              <Toast
                key={t.id}
                variant={t.variant}
                detail={"detail" in t ? t.detail : undefined}
                onDismiss={() => dropToast(t.id)}
              />
            ))}
          </div>

          {/* Offline pill (bottom-right) */}
          {offlineActive && (
            <div className="absolute bottom-4 right-4 z-[1200]">
              <OfflinePill />
            </div>
          )}
        </div>

        <div className="flex-[2] min-h-0">
          <LiveLogs events={events} />
        </div>
      </div>

      <Dashboard />

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
