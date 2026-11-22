import type { NextConfig } from "next";

// Server-side proxy to the AETHENTRA FastAPI backend: the browser calls /backend/*, so no CORS change is needed
// and the backend URL never has to be hard-coded in client code.
const API = process.env.AETHENTRA_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  distDir: process.env.NEXT_DIST_DIR || ".next",
  async rewrites() {
    return [{ source: "/backend/:path*", destination: `${API}/:path*` }];
  },
  env: { CESIUM_BASE_URL: "/cesium" },
};

export default nextConfig;
