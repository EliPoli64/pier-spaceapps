export interface PlaceResult {
  label: string;
  region: string;
  lat: number;
  lon: number;
}

export const BUILTIN_PLACES: PlaceResult[] = [
  { label: "Ames, Iowa", region: "US Midwest", lat: 42.0308, lon: -93.6319 },
  { label: "Des Moines, Iowa", region: "US Midwest", lat: 41.5868, lon: -93.625 },
  { label: "Harare / Dire Dawa", region: "Horn of Africa", lat: 9.0, lon: 41.0 },
  { label: "Nairobi", region: "Kenya", lat: -1.2921, lon: 36.8219 },
  { label: "Cape Town / Western Cape", region: "South Africa", lat: -33.9249, lon: 18.4241 },
  { label: "Córdoba", region: "Argentina", lat: -31.4201, lon: -64.1888 },
  { label: "Culiacán, Sinaloa", region: "Mexico", lat: 24.8091, lon: -107.394 },
  { label: "Ludhiana, Punjab", region: "India", lat: 30.901, lon: 75.8573 },
];

export async function searchPlaces(
  query: string,
  signal?: AbortSignal,
): Promise<PlaceResult[]> {
  const q = query.trim().toLowerCase();
  if (!q) return [];

  const localMatches = BUILTIN_PLACES.filter(
    (p) =>
      p.label.toLowerCase().includes(q) || p.region.toLowerCase().includes(q),
  );

  try {
    const url = `https://nominatim.openstreetmap.org/search?format=json&limit=5&q=${encodeURIComponent(query.trim())}`;
    const res = await fetch(url, {
      headers: { Accept: "application/json" },
      signal,
    });
    if (!res.ok) return localMatches;
    const raw = (await res.json()) as Array<{
      display_name?: string;
      lat?: string;
      lon?: string;
    }>;
    const remote: PlaceResult[] = [];
    for (const item of raw) {
      const lat = Number.parseFloat(item.lat ?? "");
      const lon = Number.parseFloat(item.lon ?? "");
      if (!Number.isFinite(lat) || !Number.isFinite(lon) || !item.display_name) {
        continue;
      }
      const parts = item.display_name.split(",").map((s) => s.trim());
      const label = parts.slice(0, 2).join(", ");
      const region = parts.slice(2, 4).join(", ");
      remote.push({ label, region, lat, lon });
    }
    return remote.length > 0 ? remote : localMatches;
  } catch {
    return localMatches;
  }
}
