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

function severityLabel(severity?: string): string {
  if (severity === "high")   return "⚠️ High";
  if (severity === "medium") return "🟡 Medium";
  if (severity === "low")    return "🟢 Low";
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
      {/* CartoDB Dark Matter — free, no API key, cinematic dark aesthetic */}
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>'
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        subdomains="abcd"
        maxZoom={19}
      />

      {/* Route polyline — electric cyan */}
      <Polyline
        positions={polylinePos}
        pathOptions={{ color: "#00d4ff", weight: 3, opacity: 0.85, dashArray: "8 6" }}
      />

      {/* Dead zones */}
      {zones.map((dz) => {
        const isNext = nextZone?.id === dz.id;
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

      {/* User position dots */}
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
                  {d.user}
                </span>
              </Tooltip>
            </CircleMarker>
          )
      )}
    </MapContainer>
  );
}
