"use client";
import { memo, useEffect, useMemo } from "react";
import { MapContainer, TileLayer, Polyline, Circle, CircleMarker, Tooltip, useMap } from "react-leaflet";
import { MAP_CENTER, MAP_ZOOM, type LatLng, type DeadZone } from "@/lib/route";

type Dot = { user: "user_a" | "user_b"; pos: LatLng | null };

type MapProps = {
  dots: Dot[];
  activeUser: string;
  deadZones?: DeadZone[];
  routePolyline?: LatLng[];
  nextZone?: DeadZone | null;
  /** Increment to trigger a fitBounds on the current zones */
  boundsVersion?: number;
};

/** Inner component, has access to the Leaflet map instance via useMap(). */
function MapAutoBounds({ zones, route, boundsVersion }: {
  zones: DeadZone[];
  route: LatLng[];
  boundsVersion?: number;
}) {
  const map = useMap();

  useEffect(() => {
    // Collect all lat/lng points from the route polyline
    const pts: [number, number][] = route.map((p) => [p.lat, p.lng]);
    if (pts.length < 2) return;
    try {
      // Add padding so dead-zone circles aren't clipped
      map.fitBounds(pts, { padding: [48, 48], maxZoom: 14, animate: true });
    } catch {
      // Leaflet can throw if the map isn't ready yet, silently ignore
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boundsVersion]);

  return null;
}

function severityLabel(severity?: string): string {
  if (severity === "high")   return "⚠️ High";
  if (severity === "medium") return "🟡 Medium";
  if (severity === "low")    return "🟢 Low";
  return "";
}

/**
 * Static map layers, route polyline + dead-zone circles.
 *
 * Pulled into its own memoized component so the animation loop (which
 * updates user position ~3x/sec) does NOT re-create these Leaflet layers
 * every tick. Layer churn on the polyline + circles was what caused the
 * map to flash whenever the dot moved.
 *
 * Re-renders only when zones, route, or the highlighted "next" zone id
 * change, none of which happen during the per-tick animation.
 */
const StaticLayers = memo(function StaticLayers({
  zones, polylinePos, nextZoneId,
}: {
  zones: DeadZone[];
  polylinePos: [number, number][];
  nextZoneId: string | undefined;
}) {
  return (
    <>
      <Polyline
        positions={polylinePos}
        pathOptions={{ color: "#00d4ff", weight: 3, opacity: 0.85, dashArray: "8 6" }}
      />
      {zones.map((dz) => {
        const isNext = nextZoneId === dz.id;
        const color =
          isNext
            ? "#ef4444"
            : dz.severity === "high"
            ? "#f97316"
            : dz.severity === "low"
            ? "#22c55e"
            : "#f59e0b";
        const fillOpacity = isNext ? 0.28 : 0.14;
        const weight      = isNext ? 2 : 1.5;
        return (
          <Circle
            key={dz.id}
            center={[dz.lat, dz.lng]}
            radius={dz.radius_km * 1000}
            pathOptions={{
              color,
              fillColor: color,
              fillOpacity,
              weight,
              dashArray: isNext ? undefined : "4 3",
            }}
          >
            <Tooltip>
              <div className="text-sm font-semibold" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                {dz.name}
              </div>
              {dz.severity && (
                <div className="text-xs mt-0.5 opacity-80">
                  {severityLabel(dz.severity)}
                  {dz.duration_minutes ? ` · ${dz.duration_minutes} min` : ""}
                </div>
              )}
              {isNext && (
                <div className="text-xs text-red-400 mt-0.5 font-medium">▶ Next dead zone</div>
              )}
            </Tooltip>
          </Circle>
        );
      })}
    </>
  );
});

export default function Map({ dots, activeUser, deadZones, routePolyline, nextZone, boundsVersion }: MapProps) {
  // Use exactly what's passed in, never fall back to the default Manhattan/Newark data
  // so the map is clean before a route is scanned.
  const zones = deadZones ?? [];
  const route = routePolyline ?? [];

  // Stable references, without these the memoized StaticLayers would
  // re-render every animation tick because the array identities change.
  const polylinePos: [number, number][] = useMemo(
    () => route.map((p) => [p.lat, p.lng]),
    // Hash on coordinate values, not array identity, so animation-loop
    // re-renders of `routePolyline` with the same values are a no-op.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [route.length, route[0]?.lat, route[0]?.lng, route[route.length - 1]?.lat, route[route.length - 1]?.lng],
  );
  const stableZones = useMemo(
    () => zones,
    // Re-memo when the zone set actually changes (new plan), not on every
    // parent render with a fresh-but-equivalent array.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [zones.length, zones.map((z) => z.id).join(",")],
  );

  return (
    <MapContainer
      center={MAP_CENTER}
      zoom={MAP_ZOOM}
      style={{ height: "100%", width: "100%" }}
      scrollWheelZoom={true}
    >
      {/* CartoDB Dark Matter, free, no API key, cinematic dark aesthetic */}
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>'
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        subdomains="abcd"
        maxZoom={19}
      />

      {/* Auto-pan to route bounds when a new plan comes in */}
      <MapAutoBounds zones={stableZones} route={route} boundsVersion={boundsVersion} />

      {/* Static layers: route + zones. Memoized so animation ticks don't
          re-create the Leaflet polyline/circle layers (was causing flash). */}
      <StaticLayers zones={stableZones} polylinePos={polylinePos} nextZoneId={nextZone?.id} />

      {/* User position dots, these intentionally update with every tick */}
      {dots.map(
        (d) =>
          d.pos && (
            <CircleMarker
              key={d.user}
              center={[d.pos.lat, d.pos.lng]}
              radius={d.user === activeUser ? 9 : 6}
              pathOptions={{
                color:       d.user === "user_a" ? "#00d4ff" : "#a78bfa",
                fillColor:   d.user === "user_a" ? "#00d4ff" : "#a78bfa",
                fillOpacity: d.user === activeUser ? 1 : 0.5,
                weight:      2,
              }}
            >
              <Tooltip permanent direction="top" offset={[0, -10]}>
                <span style={{ fontFamily: "'Space Grotesk', sans-serif", fontSize: 11 }}>
                  {d.user === "user_a" ? "Driver" : "Rider"}
                </span>
              </Tooltip>
            </CircleMarker>
          )
      )}
    </MapContainer>
  );
}
