export const NAV = [
  { href: "/", label: "Home" },
  { href: "/explore", label: "Explore" },
  { href: "/intelligence", label: "Intelligence" },
  { href: "/models", label: "ML Models", mega: true },
  { href: "/data", label: "Data" },
  { href: "/research", label: "Research" },
  { href: "/about", label: "About" },
] as const;

export const MODELS = [
  {
    slug: "ml-01",
    code: "ML-01",
    name: "Sea-Ice Forecasting",
    short: "Weekly-mean sea-ice concentration, one week ahead",
    accent: "#48c8e8",
  },
  {
    slug: "ml-02",
    code: "ML-02",
    name: "Temperature & Anomaly Forecasting",
    short: "Weekly-mean 2 m temperature and anomaly, one week ahead",
    accent: "#f4a261",
  },
  {
    slug: "ml-03",
    code: "ML-03",
    name: "Satellite Sea-Ice Detection",
    short: "Sentinel-1 SAR ice / open-water segmentation",
    accent: "#c9e6f5",
  },
  {
    slug: "ml-04",
    code: "ML-04",
    name: "Climate Anomaly Intelligence",
    short: "Unsupervised multivariate monthly anomaly detection",
    accent: "#e76f6a",
  },
] as const;

export type ModelSlug = (typeof MODELS)[number]["slug"];
