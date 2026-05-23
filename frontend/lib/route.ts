// Short test route — 4 waypoints, ~15km total. One dead zone in the middle.
// Designed so the full trip takes ~6 seconds and clearly triggers the agent.

export const ROUTE_ID = "test_route";

export type LatLng = { lat: number; lng: number };

export const ROUTE_POLYLINE: LatLng[] = [
  { lat: 40.70, lng: -74.00 },  // start
  { lat: 40.76, lng: -73.96 },  // approaching dead zone
  { lat: 40.82, lng: -73.92 },  // through the middle
  { lat: 40.88, lng: -73.88 },  // end
];

export type DeadZone = {
  id: string;
  name: string;
  lat: number;
  lng: number;
  radius_km: number;
};

export const DEAD_ZONES: DeadZone[] = [
  { id: "test_zone_1", name: "Test dead zone", lat: 40.79, lng: -73.94, radius_km: 4 },
];

// Map view defaults — keep the whole route + zone visible at a glance.
export const MAP_CENTER: [number, number] = [40.79, -73.94];
export const MAP_ZOOM = 11;

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
