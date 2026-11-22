/**
 * Geographic destinations shared by the landing page and the explorer.
 * Context sentences are standard physical-geography descriptions; data keys map each destination to the
 * regional breakdowns the APIs and presentation files actually provide (nothing is invented per region).
 */
export interface Region {
  id: string;
  name: string;
  kicker: string;
  context: string;
  /** camera: a point (lat, lon, height m) or a geographic box (degrees) */
  view: { lat: number; lon: number; height: number } | { rect: [number, number, number, number] };
  centre: [number, number]; // lat, lon for the readout
  imagery?: string; // /data/imagery/<id>.jpg
  ml01Sectors?: string[]; // /forecast/latest sectors[].sector
  climateSector?: string; // climate_series.json sector key (NSIDC)
  ml02Region?: string; // /temperature/forecast/latest regions[].region
  ml04Regions?: string[]; // /api/ml04/latest latest_multivariate.regions[].region
}

export const REGIONS: Region[] = [
  {
    id: "global",
    name: "Global Earth",
    kicker: "Planet",
    context: "The whole Earth. Polar regions hold most of the planet's ice; their sea ice, ice sheets and oceans shape climate far beyond the poles.",
    view: { lat: -15, lon: 20, height: 24_000_000 },
    centre: [0, 20],
  },
  {
    id: "antarctica",
    name: "Antarctica",
    kicker: "Continent",
    context: "The southernmost continent, almost entirely covered by the Antarctic ice sheet and ringed by seasonal sea ice in the Southern Ocean.",
    view: { lat: -90, lon: 0, height: 10_500_000 },
    centre: [-82, 0],
    imagery: "continent",
    ml01Sectors: ["weddell", "indian", "west_pacific", "ross", "bellingshausen_amundsen"],
    ml02Region: "antarctica_land",
  },
  {
    id: "peninsula",
    name: "Antarctic Peninsula",
    kicker: "Region",
    context: "A mountainous spine reaching toward South America. It warmed rapidly in the second half of the 20th century and has lost several ice shelves, including Larsen A and B.",
    view: { rect: [-76, -72, -52, -61] },
    centre: [-67.5, -63],
    imagery: "peninsula",
    ml02Region: "antarctic_peninsula",
    ml04Regions: ["antarctic_peninsula"],
  },
  {
    id: "ross",
    name: "Ross Sea",
    kicker: "Sea",
    context: "A deep embayment bounded by the Ross Ice Shelf, the largest ice shelf on Earth. Persistent offshore winds open polynyas that produce sea ice and dense shelf water.",
    view: { rect: [158, -86, -142, -67] },
    centre: [-76.5, -178],
    imagery: "ross",
    ml01Sectors: ["ross"],
    climateSector: "ross",
    ml04Regions: ["ross"],
  },
  {
    id: "weddell",
    name: "Weddell Sea",
    kicker: "Sea",
    context: "Home of the Filchner–Ronne Ice Shelf and a major source of Antarctic Bottom Water. Its sea ice is among the most extensive and longest-lived around Antarctica.",
    view: { rect: [-66, -81, -8, -60] },
    centre: [-72.5, -42],
    imagery: "weddell",
    ml01Sectors: ["weddell"],
    climateSector: "weddell",
    ml04Regions: ["weddell"],
  },
  {
    id: "east",
    name: "East Antarctica",
    kicker: "Ice sheet",
    context: "The largest and coldest part of the ice sheet, much of it a high plateau above 3,000 m. It holds most of Antarctica's ice and includes Dome A, Dome C and Vostok.",
    view: { rect: [15, -88, 168, -62] },
    centre: [-75, 100],
    imagery: "east",
    ml01Sectors: ["indian", "west_pacific"],
    ml02Region: "east_antarctica",
    ml04Regions: ["east_antarctica", "indian", "west_pacific"],
  },
  {
    id: "west",
    name: "West Antarctica",
    kicker: "Ice sheet",
    context: "A marine-based ice sheet whose bed lies largely below sea level. Thwaites and Pine Island glaciers drain it into the Amundsen Sea and are among the fastest-changing on the continent.",
    view: { rect: [-150, -86, -62, -68] },
    centre: [-78, -110],
    imagery: "west",
    ml01Sectors: ["bellingshausen_amundsen"],
    climateSector: "bellingshausen_amundsen",
    ml02Region: "west_antarctica",
    ml04Regions: ["west_antarctica", "bellingshausen_amundsen"],
  },
  {
    id: "pole",
    name: "South Pole",
    kicker: "Pole",
    context: "The geographic South Pole sits on the polar plateau at about 2,835 m elevation, on ice roughly 2.7 km thick. Amundsen–Scott Station has operated there since 1956.",
    view: { lat: -90, lon: 0, height: 2_600_000 },
    centre: [-90, 0],
    imagery: "pole",
    ml02Region: "inland",
  },
  {
    id: "southern-ocean",
    name: "Southern Ocean",
    kicker: "Ocean",
    context: "The ocean encircling Antarctica, carried by the Antarctic Circumpolar Current — the largest ocean current. Its sea ice and heat uptake are central to global climate.",
    view: { lat: -62, lon: 20, height: 13_000_000 },
    centre: [-60, 20],
    imagery: "southern_ocean",
    ml01Sectors: ["weddell", "indian", "west_pacific", "ross", "bellingshausen_amundsen"],
    ml02Region: "southern_ocean",
  },
];

export const regionById = (id: string | null | undefined) => REGIONS.find((r) => r.id === id);
