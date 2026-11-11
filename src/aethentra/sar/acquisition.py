"""ML-03 acquisition: USNIC Antarctic ice charts, Sentinel-1 EW GRDM HH scene catalogue and overview-level scene download.

Sentinel-1: official ESA Level-1 GRD products served by Microsoft Planetary Computer (COG + SAFE annotation XMLs). A scene is
"downloaded" as (a) the HH image at the configured COG overview with its GCPs, (b) the calibration and noise annotation XMLs,
(c) a provenance record (STAC item id, asset URL without the SAS token, md5, overview factor, retrieval time).
No credentials are needed or stored.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import re
import time
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import ROOT
from .paths import INTERIM, RAW_AUX, RAW_CHARTS, RAW_S1, load

LOG = logging.getLogger("aethentra.ml03.acquisition")
UA = {"User-Agent": "AETHENTRA-ML03 research pipeline"}


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def md5sum(p: Path) -> str:
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _get(url, data=None, timeout=120, retries=4) -> bytes:
    for a in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if a == retries:
                raise
            LOG.warning("GET %s failed (%s); retry %d", url.split("?")[0], str(e)[:120], a)
            time.sleep(5 * a)


# ----------------------------------------------------------------------------------------------- USNIC charts
def list_charts(start: str, end: str) -> pd.DataFrame:
    cfg = load("satellite_sources")["usnic_charts"]
    rows = []
    for y in range(int(start[:4]), int(end[:4]) + 1):
        body = urllib.parse.urlencode({"searchText": cfg["search_text"], "searchProduct": cfg["search_product"],
                                       "startDate": f"01/01/{y}", "endDate": f"12/31/{y}"}).encode()
        html = _get(cfg["search_url"], data=body).decode("utf-8", "replace")
        for prd in re.findall(r"prd=(\d{10,})", html):                       # prefix + MMDDYYYY
            d = pd.Timestamp(f"{prd[-4:]}-{prd[-8:-6]}-{prd[-6:-4]}")
            if pd.Timestamp(start) <= d <= pd.Timestamp(end):
                rows.append({"chart_date": d, "prd": prd})
    return pd.DataFrame(rows).drop_duplicates("chart_date").sort_values("chart_date").reset_index(drop=True)


def download_chart(chart_date: pd.Timestamp, prd: str) -> dict:
    cfg = load("satellite_sources")["usnic_charts"]
    d = RAW_CHARTS / f"{chart_date:%Y%m%d}"
    prov_p = d / "provenance.json"
    if prov_p.exists():
        return json.loads(prov_p.read_text())
    d.mkdir(parents=True, exist_ok=True)
    z = d / f"antarc{chart_date:%y%m%d}.zip"
    z.write_bytes(_get(cfg["download_url"].format(prd=prd)))
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
        shp = [n for n in names if n.lower().endswith(".shp")]
        if not shp:
            raise ValueError(f"no shapefile in chart {z.name}")
        zf.extractall(d)
    info = {"chart_date": str(chart_date.date()), "prd": prd, "zip": z.name, "md5": md5sum(z), "shapefile": shp[0],
            "source": cfg["name"], "url": cfg["download_url"].format(prd=prd), "retrieved_utc": _now()}
    prov_p.write_text(json.dumps(info, indent=1))
    return info


def acquire_charts(start: str, end: str, workers: int = 4) -> pd.DataFrame:
    lst = list_charts(start, end)
    with ThreadPoolExecutor(workers) as ex:
        infos = list(ex.map(lambda r: download_chart(r.chart_date, r.prd), lst.itertuples()))
    cat = pd.DataFrame(infos)
    INTERIM.mkdir(parents=True, exist_ok=True)
    cat.to_csv(INTERIM / "chart_catalogue.csv", index=False)
    return cat


def chart_path(chart_date) -> Path:
    d = RAW_CHARTS / f"{pd.Timestamp(chart_date):%Y%m%d}"
    return d / json.loads((d / "provenance.json").read_text())["shapefile"]


# ----------------------------------------------------------------------------------------------- Sentinel-1 catalogue
def _client():
    import planetary_computer as pc
    import pystac_client
    return pystac_client.Client.open(load("satellite_sources")["sentinel1"]["stac_api"], modifier=pc.sign_inplace)


def sector_of(lon: float) -> str:
    for name, (a, b) in load("evaluation")["sectors"].items():
        if (a <= lon < b) if a < b else (lon >= a or lon < b):
            return name
    return "unknown"


def split_of(chart_date) -> str | None:
    for name, (a, b) in load("labels")["splits"].items():
        if pd.Timestamp(a) <= pd.Timestamp(chart_date) <= pd.Timestamp(b):
            return name
    return None


def footprint_points(geometry: dict) -> np.ndarray:
    """All exterior vertices (lon, lat) of a Polygon / MultiPolygon footprint (antimeridian-split parts included)."""
    polys = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    pts = [np.asarray(p[0], float) for p in polys if p and len(p[0])]
    return np.concatenate(pts)


def search_scenes(chart_date, client=None, days: tuple | None = None, max_items: int | None = 80) -> list:
    """EW GRDM HH scenes acquired days[0]..days[1] days before chart_date (default: the chart match window), centroid south of
    search_lat_max. days=(0, 0) returns the acquisitions of that single day. max_items keeps the acquisitions closest to
    chart_date (newest first), which also minimises the chart-scene time mismatch; None returns all."""
    s1, lab = load("satellite_sources")["sentinel1"], load("labels")
    a, b = days or lab["chart_match_days"]
    t1 = pd.Timestamp(chart_date) - pd.Timedelta(days=a) + pd.Timedelta(hours=23, minutes=59)
    t0 = pd.Timestamp(chart_date) - pd.Timedelta(days=b)
    client = client or _client()
    res = client.search(collections=[s1["collection"]], bbox=[-180, -90, 180, s1["search_lat_max"]],
                        datetime=f"{t0:%Y-%m-%dT%H:%M:%SZ}/{t1:%Y-%m-%dT%H:%M:%SZ}", limit=100, max_items=max_items,
                        sortby=[{"field": "properties.datetime", "direction": "desc"}],
                        query={"sar:instrument_mode": {"eq": s1["instrument_mode"]}, "s1:resolution": {"eq": s1["product_resolution"]}})
    out = []
    for it in res.items():
        p = it.properties
        if s1["polarization"] not in p.get("sar:polarizations", []) or s1["polarization"].lower() not in it.assets:
            continue
        g = footprint_points(it.geometry)
        lat = float(g[:, 1].mean())
        lon = float(np.degrees(np.arctan2(np.sin(np.radians(g[:, 0])).mean(), np.cos(np.radians(g[:, 0])).mean())))
        if lat > s1["search_lat_max"]:
            continue
        out.append({"scene_id": it.id, "acquired": p["datetime"], "chart_date": str(pd.Timestamp(chart_date).date()),
                    "polarizations": ",".join(p["sar:polarizations"]), "mode": p["sar:instrument_mode"], "orbit_state": p.get("sat:orbit_state"),
                    "relative_orbit": p.get("sat:relative_orbit"), "platform": it.id[:3], "centroid_lat": lat, "centroid_lon": lon,
                    "sector": sector_of(lon), "footprint": json.dumps(it.geometry)})
    return out


def build_catalogue(charts: pd.DataFrame, workers: int = 4) -> pd.DataFrame:
    cfg = load("labels")
    rng = np.random.default_rng(load("training")["seed"])
    client = _client()

    cache = INTERIM / "search_cache"
    cache.mkdir(parents=True, exist_ok=True)

    def one(d):                                    # per-date cache -> the catalogue build is resumable
        f = cache / f"{d:%Y%m%d}.json"
        if f.exists():
            return json.loads(f.read_text())
        for a in range(3):
            try:
                r = search_scenes(d, client)
                f.write_text(json.dumps(r))
                return r
            except Exception as e:  # noqa: BLE001
                LOG.warning("search %s failed (%d): %s", d.date(), a, str(e)[:150])
                time.sleep(10 * (a + 1))
        return []
    with ThreadPoolExecutor(workers) as ex:
        found = list(ex.map(one, [pd.Timestamp(d) for d in charts["chart_date"]]))
    rows = []
    for d, sc in zip(charts["chart_date"], found):
        if not sc:
            continue
        df = pd.DataFrame(sc).drop_duplicates("scene_id")
        # stratify by longitude sector: round-robin over sectors, random order within a sector
        df = df.iloc[rng.permutation(len(df))]
        groups = [g for _, g in df.groupby("sector")]
        rng.shuffle(groups)
        pick, k = [], 0
        while len(pick) < cfg["scenes_per_chart"] and any(len(g) > k for g in groups):
            pick += [g.iloc[k] for g in groups if len(g) > k][: cfg["scenes_per_chart"] - len(pick)]
            k += 1
        rows += [dict(r) for r in pick]
    cat = pd.DataFrame(rows)
    cat["split"] = cat["chart_date"].map(split_of)
    cat["download_status"] = "pending"
    cat["processing_status"] = "pending"
    INTERIM.mkdir(parents=True, exist_ok=True)
    cat.to_csv(INTERIM / "scene_catalogue.csv", index=False)
    return cat


# ----------------------------------------------------------------------------------------------- Sentinel-1 download
def download_scene(scene_id: str, client=None) -> dict:
    import rasterio
    from rasterio.control import GroundControlPoint
    d = RAW_S1 / scene_id
    prov_p = d / "provenance.json"
    if prov_p.exists():
        return json.loads(prov_p.read_text())
    s1 = load("satellite_sources")["sentinel1"]
    f = s1["overview_factor"]
    pol = s1["polarization"].lower()
    client = client or _client()
    it = client.get_collection(s1["collection"]).get_item(scene_id)
    d.mkdir(parents=True, exist_ok=True)
    href = it.assets[pol].href
    with rasterio.open(href) as r:
        H, W = r.height, r.width
        h, w = H // f, W // f
        a = r.read(1, out_shape=(h, w))
        gcps, gcrs = r.gcps
    sg = [GroundControlPoint(row=g.row * h / H, col=g.col * w / W, x=g.x, y=g.y, z=g.z) for g in gcps]
    tif = d / f"{pol}_ov{f}.tif"
    tmp = tif.with_suffix(".part")
    with rasterio.open(tmp, "w", driver="GTiff", width=w, height=h, count=1, dtype=a.dtype, compress="deflate",
                       gcps=sg, crs=gcrs) as o:
        o.write(a, 1)
        o.update_tags(full_width=W, full_height=H, overview_factor=f, source_asset=pol)
    tmp.replace(tif)
    files = {tif.name: md5sum(tif)}
    for key in (f"schema-calibration-{pol}", f"schema-noise-{pol}"):
        x = d / f"{key}.xml"
        x.write_bytes(_get(it.assets[key].href))
        files[x.name] = md5sum(x)
    p = it.properties
    info = {"scene_id": scene_id, "acquired": p["datetime"], "start": p.get("start_datetime"), "end": p.get("end_datetime"),
            "platform": p.get("platform"), "mode": p["sar:instrument_mode"], "polarizations": p["sar:polarizations"],
            "orbit_state": p.get("sat:orbit_state"), "relative_orbit": p.get("sat:relative_orbit"),
            "pixel_spacing_m": p.get("sar:pixel_spacing_range"), "looks": [p.get("sar:looks_range"), p.get("sar:looks_azimuth")],
            "full_size": [H, W], "overview_factor": f, "stored_size": [h, w], "files": files, "geometry": it.geometry,
            "source": f"{s1['stac_api']} collection {s1['collection']}", "asset_url": href.split("?")[0],
            "licence": "Copernicus Sentinel data (free, full and open)", "retrieved_utc": _now()}
    prov_p.write_text(json.dumps(info, indent=1))
    return info


def download_scenes(ids: list[str], workers: int = 6) -> pd.DataFrame:
    client = _client()
    out = []

    def one(sid):
        for a in range(3):
            try:
                return {"scene_id": sid, "status": "downloaded", **{k: v for k, v in download_scene(sid, client).items() if k == "stored_size"}}
            except Exception as e:  # noqa: BLE001
                err = str(e)[:200]
                time.sleep(5 * (a + 1))
        return {"scene_id": sid, "status": "failed", "error": err}
    with ThreadPoolExecutor(workers) as ex:
        for i, r in enumerate(ex.map(one, ids)):
            out.append(r)
            if i % 50 == 0:
                LOG.info("scenes %d/%d", i, len(ids))
    return pd.DataFrame(out)


# ----------------------------------------------------------------------------------------------- auxiliary (land mask)
def acquire_land() -> dict:
    cfg = load("sar_preprocessing")["land_mask"]
    RAW_AUX.mkdir(parents=True, exist_ok=True)
    out = {}
    for key in ("land_url", "shelves_url"):
        url = cfg[key]
        z = RAW_AUX / url.rsplit("/", 1)[1]
        if not z.exists():
            z.write_bytes(_get(url))
        with zipfile.ZipFile(z) as zf:
            zf.extractall(RAW_AUX / z.stem)
        out[z.name] = {"url": url, "md5": md5sum(z)}
    (RAW_AUX / "provenance.json").write_text(json.dumps({**out, "retrieved_utc": _now(), "licence": "Natural Earth, public domain"}, indent=1))
    return out


def relpath(p: Path) -> str:
    return Path(p).resolve().relative_to(ROOT).as_posix()
