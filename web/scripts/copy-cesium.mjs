// Copies CesiumJS static assets (workers, widgets, textures) into public/cesium so the globe can load them.
import { cpSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, "node_modules", "cesium", "Build", "Cesium");
const dst = join(root, "public", "cesium");
if (!existsSync(src)) { console.error("cesium not installed"); process.exit(1); }
mkdirSync(dst, { recursive: true });
for (const d of ["Assets", "Workers", "ThirdParty", "Widgets"]) cpSync(join(src, d), join(dst, d), { recursive: true });
cpSync(join(src, "Cesium.js"), join(dst, "Cesium.js"));
console.log("cesium assets copied to public/cesium");
