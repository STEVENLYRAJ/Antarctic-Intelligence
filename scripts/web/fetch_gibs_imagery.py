"""Cache NASA GIBS Antarctic polar-stereographic (EPSG:3031) imagery snapshots for the web frontend.

Public-domain NASA imagery, no token required. Cached locally so the presentation does not depend on the network.
Output: web/public/data/imagery/<id>.jpg + index.json (title, date, layer, bbox, attribution).
"""
from __future__ import annotations

import json
import math
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "web" / "public" / "data" / "imagery"
WMS = "https://gibs.earthdata.nasa.gov/wms/epsg3031/best/wms.cgi"
DATE = "2025-12-15"
TC = "MODIS_Terra_CorrectedReflectance_TrueColor"
BM = "BlueMarble_ShadedRelief_Bathymetry"


def ps(lat: float, lon: float) -> tuple[float, float]:
    """EPSG:3031 forward (WGS84, true scale at 71 S, central meridian 0)."""
    a, e, phic = 6378137.0, 0.0818191908426, math.radians(71.0)
    phi, lam = math.radians(-lat), math.radians(lon)
    t = math.tan(math.pi / 4 - phi / 2) / ((1 - e * math.sin(phi)) / (1 + e * math.sin(phi))) ** (e / 2)
    tc = math.tan(math.pi / 4 - phic / 2) / ((1 - e * math.sin(phic)) / (1 + e * math.sin(phic))) ** (e / 2)
    mc = math.cos(phic) / math.sqrt(1 - e * e * math.sin(phic) ** 2)
    rho = a * mc * t / tc
    return rho * math.sin(lam), rho * math.cos(lam)


SHOTS = [
    # id, title, layer, centre (lat, lon) or None for full, half-width km, w, h
    ("continent", "Antarctica and the Southern Ocean", TC, None, 3200, 1600, 1600),
    ("continent_bluemarble", "Antarctica, Blue Marble shaded relief and bathymetry", BM, None, 4000, 1200, 1200),
    ("peninsula", "Antarctic Peninsula", TC, (-67.5, -63.0), 650, 1200, 800),
    ("ross", "Ross Sea and Ross Ice Shelf", TC, (-76.5, -178.0), 900, 1200, 800),
    ("weddell", "Weddell Sea", TC, (-72.5, -42.0), 1000, 1200, 800),
    ("east", "East Antarctica", TC, (-73.5, 105.0), 1500, 1200, 800),
    ("west", "West Antarctica and the Amundsen Sea", TC, (-77.0, -110.0), 900, 1200, 800),
    ("pole", "South Pole and the polar plateau", TC, (-90.0, 0.0), 700, 1200, 800),
    ("southern_ocean", "Southern Ocean", BM, None, 4100, 1200, 800),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    idx = []
    for sid, title, layer, c, hw_km, w, h in SHOTS:
        x0, y0 = ps(*c) if c else (0.0, 0.0)
        hx = hw_km * 1000.0; hy = hx * h / w
        bbox = (x0 - hx, y0 - hy, x0 + hx, y0 + hy)
        q = (f"SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS={layer}&STYLES=&CRS=EPSG:3031"
             f"&BBOX={','.join(f'{v:.0f}' for v in bbox)}&WIDTH={w}&HEIGHT={h}&FORMAT=image/jpeg")
        if layer == TC:
            q += f"&TIME={DATE}"
        p = OUT / f"{sid}.jpg"
        with urllib.request.urlopen(f"{WMS}?{q}", timeout=60) as r:
            data = r.read()
            assert r.headers.get("Content-Type", "").startswith("image/"), r.headers.get("Content-Type")
        p.write_bytes(data)
        idx.append({"id": sid, "title": title, "url": f"/data/imagery/{sid}.jpg", "layer": layer,
                    "date": DATE if layer == TC else "composite (static)", "crs": "EPSG:3031", "bbox_m": [round(v) for v in bbox],
                    "width": w, "height": h,
                    "attribution": ("NASA EOSDIS GIBS / Worldview — MODIS Terra Corrected Reflectance (true colour)" if layer == TC
                                    else "NASA Earth Observatory Blue Marble shaded relief & bathymetry, via NASA GIBS"),
                    "license": "NASA imagery, public domain (no copyright)"})
        print(sid, len(data) // 1024, "KB")
    (OUT / "index.json").write_text(json.dumps(idx, indent=1))


if __name__ == "__main__":
    main()
