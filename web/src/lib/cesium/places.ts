/** Curated Antarctic gazetteer for search / fly-to. Coordinates in decimal degrees (WGS84). */
export interface Place {
  name: string;
  kind: "region" | "sea" | "station" | "ice" | "pole" | "passage";
  lat: number;
  lon: number;
  height: number; // camera height in metres for the fly-to
}

export const PLACES: Place[] = [
  { name: "South Pole (Amundsen–Scott Station)", kind: "pole", lat: -90, lon: 0, height: 9_000_000 },
  { name: "Antarctic Peninsula", kind: "region", lat: -66.5, lon: -63, height: 2_200_000 },
  { name: "Weddell Sea", kind: "sea", lat: -72.5, lon: -45, height: 3_200_000 },
  { name: "Ross Sea", kind: "sea", lat: -75, lon: -175, height: 3_000_000 },
  { name: "Ross Ice Shelf", kind: "ice", lat: -81.5, lon: -175, height: 2_200_000 },
  { name: "Amundsen Sea", kind: "sea", lat: -73, lon: -112, height: 2_400_000 },
  { name: "Bellingshausen Sea", kind: "sea", lat: -71, lon: -85, height: 2_400_000 },
  { name: "Thwaites Glacier", kind: "ice", lat: -75.5, lon: -106.75, height: 900_000 },
  { name: "Pine Island Glacier", kind: "ice", lat: -75.17, lon: -100, height: 900_000 },
  { name: "Larsen C Ice Shelf", kind: "ice", lat: -67.5, lon: -62.5, height: 900_000 },
  { name: "Filchner–Ronne Ice Shelf", kind: "ice", lat: -78.5, lon: -60, height: 2_000_000 },
  { name: "Amery Ice Shelf / Prydz Bay", kind: "ice", lat: -69.5, lon: 72, height: 1_600_000 },
  { name: "East Antarctic Plateau (Dome C)", kind: "region", lat: -75.1, lon: 123.35, height: 3_500_000 },
  { name: "Vostok Station", kind: "station", lat: -78.46, lon: 106.84, height: 1_500_000 },
  { name: "McMurdo Station", kind: "station", lat: -77.85, lon: 166.67, height: 800_000 },
  { name: "Rothera Research Station", kind: "station", lat: -67.57, lon: -68.13, height: 700_000 },
  { name: "Halley Research Station", kind: "station", lat: -75.58, lon: -26.66, height: 900_000 },
  { name: "Casey Station", kind: "station", lat: -66.28, lon: 110.53, height: 900_000 },
  { name: "Mawson Station", kind: "station", lat: -67.6, lon: 62.87, height: 900_000 },
  { name: "Drake Passage", kind: "passage", lat: -58, lon: -65, height: 2_600_000 },
  { name: "Southern Ocean (Indian sector)", kind: "sea", lat: -60, lon: 60, height: 6_000_000 },
  { name: "Southern Ocean (Pacific sector)", kind: "sea", lat: -60, lon: -150, height: 6_000_000 },
];

export const VIEWS = {
  global: { lat: -15, lon: 20, height: 24_000_000 },
  antarctica: { lat: -90, lon: 0, height: 10_500_000 },
} as const;
