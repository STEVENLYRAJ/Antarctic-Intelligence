/**
 * Response types for the AETHENTRA backend. Only the fields the UI reads are typed strictly;
 * everything else is kept as `unknown` so the UI never invents structure the backend does not return.
 */

export type DataType =
  | "model_prediction"
  | "observation"
  | "reanalysis_observation"
  | "statistical_anomaly"
  | "reanalysis_anomaly"
  | "evaluation"
  | string;

export interface Health {
  status: string;
  model_available: boolean;
  time_utc: string;
}

export interface LayerStyle {
  cmap: string;
  vmin: number | null;
  vmax: number | null;
  colors: string[];
}

export interface Layer {
  id: string;
  title: string;
  data_type: DataType;
  units: string;
  period: string | [string, string];
  issue_date: string;
  style: LayerStyle;
  png_url?: string;
  tif_url?: string;
  globe_png_url?: string;
  globe_bounds?: Bounds;
  vector_urls: string[];
}

export interface Bounds {
  west: number;
  south: number;
  east: number;
  north: number;
}

export interface LayerManifest {
  product: "sic" | "t2m" | "sar" | "anom";
  forecast_id: string;
  issue_date: string | null;
  model_version: string | null;
  source: unknown;
  limitations: unknown;
  display_rules: string[] | null;
  summary: Record<string, unknown> | null;
  layers: Layer[];
}

export interface SicSector {
  sector: string;
  extent_km2: number;
  area_km2: number;
  persistence_extent_km2?: number;
}

export interface SicForecast {
  forecast_id: string;
  product: string;
  data_type: DataType;
  issue_date: string;
  issue_time_utc: string;
  target_start: string;
  target_end: string;
  quantity: string;
  units: string;
  grid: string;
  sic_threshold_percent: number;
  extent_km2: number;
  area_km2: number;
  persistence_extent_km2: number;
  climatology_extent_km2: number;
  sectors: SicSector[];
  model_version?: string;
  [k: string]: unknown;
}

export type MetricBlock = Record<string, number>;

export interface SicMetrics {
  evaluation_period: [string, string];
  issue_dates: number;
  climatology_period: [string, string];
  metrics: Record<string, Record<string, MetricBlock>>;
  [k: string]: unknown;
}

export interface ModelInfo {
  model_version: string;
  [k: string]: unknown;
}

export interface T2mRegion {
  region: string;
  area_km2: number;
  forecast_mean_t2m_degC: number;
  climatology_mean_t2m_degC: number;
  forecast_mean_anomaly_degC: number;
  last_week_observed_anomaly_degC?: number;
  [k: string]: unknown;
}

export interface T2mForecast {
  forecast_id: string;
  data_type: DataType;
  product: string;
  issue_date: string;
  target_start: string;
  target_end: string;
  units: Record<string, string>;
  climatology_reference_period: [number, number];
  model_version: string;
  model_name: string;
  reanalysis_source: string;
  regions: T2mRegion[];
  [k: string]: unknown;
}

export interface T2mMetrics {
  split: string;
  issue_dates: [string, string];
  n_issue_dates: number;
  source: string;
  metrics: Record<string, Record<string, MetricBlock>>;
  [k: string]: unknown;
}

export interface SarScene {
  scene_id: string;
  acquired: string;
  processed_utc: string;
  data_type: DataType;
  sensor: string;
  mode: string;
  polarization: string;
  resolution_m: number;
  model_version: string;
  model_name: string;
  pixel_counts: Record<string, number>;
  nominal_ice_area_km2: number;
  warnings: string[];
  [k: string]: unknown;
}

export interface SarMetrics {
  split: string;
  n_scenes: number;
  charts: [string, string];
  label_source: string;
  metrics: Record<string, Record<string, number>>;
  [k: string]: unknown;
}

export interface SarWeekly {
  week_start: string;
  week_end: string;
  data_type: DataType;
  grid: string;
  n_acquisitions: number;
  observed_area_km2_nominal: number;
  cells_weekly_ice: number;
  cells_weekly_water: number;
  cells_variable: number;
  model_version: string;
  methodology: string;
  [k: string]: unknown;
}

export interface Ml04ModelInfo {
  model_version: string;
  selected_multivariate: string;
  family: string;
  features: string[];
  train_period: string;
  baseline_model: string;
  baseline_reporting: string;
  severity_thresholds: Record<string, number>;
  rank_sum_validation: Record<string, number>;
  reference_methods: string[];
  [k: string]: unknown;
}

export interface Ml04MonthRow {
  month: string;
  split: string;
  cells: number;
  multivariate_flag_cells: number;
  multivariate_flag_area_fraction: number;
  strong_or_extreme_cells: number;
  most_affected_region: string;
  [k: string]: number | string;
}

export interface Ml04MonthlySummary {
  baseline: string;
  rows: Ml04MonthRow[];
  note: string;
}

export interface Ml04Event {
  event_id: number;
  start: string;
  end: string;
  n_months: number;
  max_area_km2: number;
  peak_score: number;
  mean_agreement: number;
  regions: string;
}

export interface Ml04Events {
  definition: string;
  events: Ml04Event[];
  note: string;
}

export interface Ml04Metrics {
  evaluation: string;
  decision: Record<string, unknown>;
  validation: Record<string, Record<string, number>>;
  test?: Record<string, Record<string, number>>;
  [k: string]: unknown;
}

export interface Ml04Latest {
  latest_multivariate: {
    product: string;
    month: string;
    period: [string, string];
    model_version: string;
    selected_method: string;
    statistics: Record<string, number>;
    regions: { region: string; cells: number; flagged: number }[];
    [k: string]: unknown;
  };
  [k: string]: unknown;
}

/* ---------- static climate products (public/data) ---------- */

export interface SeriesPack {
  t: string[];
  v: number[];
  anom: number[];
}

export interface ClimateSeries {
  title: string;
  units: string;
  source: string;
  domain: string;
  note?: string;
  /** anomaly reference period when it differs from the file default (e.g. "2003-2020") */
  clim?: string;
  antarctic: SeriesPack;
  sectors?: Record<string, SeriesPack>;
}

export interface ClimateSeriesFile {
  meta: { generated_utc: string; climatology: string; area_weighting: string; data_type: string; [k: string]: unknown };
  series: Record<string, ClimateSeries>;
}

export interface GlobeImage {
  id: string;
  title: string;
  units: string;
  vmin: number;
  vmax: number;
  colors: string[];
  month: string;
  data_type: DataType;
  source: string;
  url: string;
  bounds: Bounds;
}

/* ---------- time-enabled globe catalogue (public/data/globe/catalog.json) ---------- */
export interface CatalogFrame {
  t: string;
  url: string;
  vectors?: string;
}

export interface CatalogLayer {
  id: string;
  group: string;
  title: string;
  units: string;
  data_type: DataType;
  source: string;
  method: string;
  colors: string[];
  vmin: number;
  vmax: number;
  bounds: Bounds;
  coverage: string;
  frames: CatalogFrame[];
  default?: string | null;
}

export interface GlobeCatalog {
  generated_utc: string;
  layers: CatalogLayer[];
}

/* ---------- daily records (public/data/daily_series.json) ---------- */
export interface DailyRecord {
  title: string;
  units: string;
  source: string;
  data_type: DataType;
  note?: string;
  years: Record<string, (number | null)[]>;
  clim: { base: string; mean: (number | null)[]; min: (number | null)[]; max: (number | null)[]; p10: (number | null)[]; p90: (number | null)[] };
}

export interface DailySeriesFile {
  meta: { generated_utc: string; day_index: string };
  sea_ice_extent?: DailyRecord;
  t2m?: DailyRecord;
  era5_msl?: DailyRecord;
  era5_t850?: DailyRecord;
  era5_z500?: DailyRecord;
  era5_wind10?: DailyRecord;
}
