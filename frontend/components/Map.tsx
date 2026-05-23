"use client";
import { MapContainer, TileLayer, Polyline, Circle, CircleMarker, Tooltip } from "react-leaflet";
import { ROUTE_POLYLINE, DEAD_ZONES, MAP_CENTER, MAP_ZOOM, type LatLng } from "@/lib/route";

type Dot = { user: "user_a" | "user_b"; pos: LatLng | null };

export default function Map({ dots, activeUser }: { dots: Dot[]; activeUser: string }) {
  const polylinePos: [number, number][] = ROUTE_POLYLINE.map((p) => [p.lat, p.lng]);
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
      {DEAD_ZONES.map((dz) => (
        <Circle
          key={dz.id}
          center={[dz.lat, dz.lng]}
          radius={dz.radius_km * 1000}
          pathOptions={{ color: "#f97316", fillColor: "#f97316", fillOpacity: 0.18, weight: 1 }}
        >
          <Tooltip>{dz.name} (dead zone)</Tooltip>
        </Circle>
      ))}
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
