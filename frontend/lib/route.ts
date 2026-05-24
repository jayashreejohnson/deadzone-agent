// Route and dead zone configuration with dynamic update support.

export const ROUTE_ID = "test_route";

export type LatLng = { lat: number; lng: number };

export type DeadZone = {
  id: string;
  name: string;
  lat: number;
  lng: number;
  radius_km: number;
  duration_minutes?: number;
  severity?: "high" | "medium" | "low";
};

// Default Manhattan → Newark route
export const DEFAULT_ROUTE_POLYLINE: LatLng[] = [
  { lat: 40.7549, lng: -73.9840 }, // Penn Station area
  { lat: 40.7621, lng: -74.0312 }, // Lincoln Tunnel approach
  { lat: 40.7282, lng: -74.0776 }, // Jersey City
  { lat: 40.7357, lng: -74.1724 }, // Newark approach
  { lat: 40.7357, lng: -74.1800 }, // Newark
];

export const DEFAULT_DEAD_ZONES: DeadZone[] = [
  { id: "lincoln_tunnel", name: "Lincoln Tunnel", lat: 40.7621, lng: -74.0312, radius_km: 0.8, duration_minutes: 4, severity: "high" },
  { id: "newark_mccarter", name: "Newark McCarter Hwy", lat: 40.7357, lng: -74.1724, radius_km: 0.5, duration_minutes: 1, severity: "low" },
];

// Legacy exports kept for backwards compatibility (page.tsx still imports ROUTE_POLYLINE/DEAD_ZONES)
export const ROUTE_POLYLINE: LatLng[] = DEFAULT_ROUTE_POLYLINE;
export const DEAD_ZONES: DeadZone[] = DEFAULT_DEAD_ZONES;

// Map view defaults
export let MAP_CENTER: [number, number] = [40.748, -74.080];
export let MAP_ZOOM = 12;

/** Update the map center/zoom defaults at runtime. */
export function setMapView(center: [number, number], zoom: number) {
  MAP_CENTER = center;
  MAP_ZOOM = zoom;
}

/** Haversine distance in kilometers. */
export function distanceKm(a: LatLng, b: LatLng): number {
  const R = 6371;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLng = ((b.lng - a.lng) * Math.PI) / 180;
  const la1 = (a.lat * Math.PI) / 180;
  const la2 = (b.lat * Math.PI) / 180;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(la1) * Math.cos(la2) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

/** Linearly interpolate between two lat/lngs. */
export function lerp(a: LatLng, b: LatLng, t: number): LatLng {
  return { lat: a.lat + (b.lat - a.lat) * t, lng: a.lng + (b.lng - a.lng) * t };
}
