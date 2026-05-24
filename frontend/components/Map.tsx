"use client";
import { MapContainer, TileLayer, Polyline, Circle, CircleMarker, Tooltip } from "react-leaflet";
import { DEFAULT_ROUTE_POLYLINE, DEFAULT_DEAD_ZONES, MAP_CENTER, MAP_ZOOM, type LatLng, type DeadZone } from "@/lib/route";

type Dot = { user: "user_a" | "user_b"; pos: LatLng | null };

type MapProps = {
  dots: Dot[];
  activeUser: string;
  deadZones?: DeadZone[];
  routePolyline?: LatLng[];
  nextZone?: DeadZone | null;
};

function severityIcon(severity?: string): string {
  if (severity === "high") return "⚠️ High";
  if (severity === "medium") return "🟡 Medium";
  if (severity === "low") return "🟢 Low";
  return "";
}

export default function Map({ dots, activeUser, deadZones, routePolyline, nextZone }: MapProps) {
  const zones = deadZones && deadZones.length > 0 ? deadZones : DEFAULT_DEAD_ZONES;
  const route = routePolyline && routePolyline.length > 0 ? routePolyline : DEFAULT_ROUTE_POLYLINE;
  const polylinePos: [number, number][] = route.map((p) => [p.lat, p.lng]);

  return (
    <MapContainer
      center={MAP_CENTER}
      zoom={MAP_ZOOM}
      style={{ height: "100%", width: "100%" }}
      scrollWheelZoom={true}
    >
      <TileLayer
        attribution='&copy; OpenStreetMap'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <Polyline positions={polylinePos} pathOptions={{ color: "#60a5fa", weight: 4 }} />
      {zones.map((dz) => {
        const isNext = nextZone?.id === dz.id;
        // Next zone: pulsing orange-red; others use severity color
        const color = isNext
          ? "#ef4444"
          : dz.severity === "high"
          ? "#f97316"
          : dz.severity === "low"
          ? "#22c55e"
          : "#f97316";
        const fillOpacity = isNext ? 0.35 : 0.18;
        const weight = isNext ? 2 : 1;
        const className = isNext ? "animate-pulse" : undefined;
        return (
          <Circle
            key={dz.id}
            center={[dz.lat, dz.lng]}
            radius={dz.radius_km * 1000}
            pathOptions={{ color, fillColor: color, fillOpacity, weight, className }}
          >
            <Tooltip>
              <div className="text-sm font-medium">{dz.name}</div>
              {dz.severity && (
                <div className="text-xs mt-0.5">
                  {severityIcon(dz.severity)}
                  {dz.duration_minutes ? ` — ${dz.duration_minutes} min blackout` : ""}
                </div>
              )}
              {isNext && <div className="text-xs text-red-400 mt-0.5">Next dead zone</div>}
            </Tooltip>
          </Circle>
        );
      })}
      {dots.map(
        (d) =>
          d.pos && (
            <CircleMarker
              key={d.user}
              center={[d.pos.lat, d.pos.lng]}
              radius={d.user === activeUser ? 10 : 7}
              pathOptions={{
                color: d.user === "user_a" ? "#34d399" : "#a78bfa",
                fillColor: d.user === "user_a" ? "#34d399" : "#a78bfa",
                fillOpacity: d.user === activeUser ? 1 : 0.55,
                weight: 2,
              }}
            >
              <Tooltip permanent direction="top" offset={[0, -10]}>
                {d.user}
              </Tooltip>
            </CircleMarker>
          )
      )}
    </MapContainer>
  );
}
