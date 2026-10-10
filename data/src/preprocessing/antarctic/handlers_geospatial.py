"""Handlers for vector / raster geospatial data: GLIMS shapefiles, PGC KMZ tile index, TIFF image."""
from __future__ import annotations

import re
import warnings
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import shapely
from shapely.validation import explain_validity

from .common import add_output, finish, issue, new_record, num_summary, step
from .config import (EPSG_ANTARCTIC_PS, EPSG_EASE2_SOUTH, GLIMS_ANTARCTIC_O1REG, PROCESSED_DIR)

GLIMS_GPKG = PROCESSED_DIR / "glims" / "glims_antarctic_rgi19.gpkg"


def _coord_range_flags(geoms: gpd.GeoSeries) -> pd.DataFrame:
    b = geoms.bounds
    return pd.DataFrame({
        "lon_out_of_range": (b.minx < -180) | (b.maxx > 180),
        "lat_out_of_range": (b.miny < -90) | (b.maxy > 90),
    })


def _validity(geoms: gpd.GeoSeries) -> pd.DataFrame:
    arr = geoms.values
    empty = shapely.is_empty(arr)
    null = pd.isna(geoms).values
    valid = shapely.is_valid(arr)
    reasons = [("" if (v or n) else explain_validity(g)) for g, v, n in zip(arr, valid, null)]
    return pd.DataFrame({"geom_null": null, "geom_empty": empty, "geom_valid": valid & ~null,
                         "invalid_reason": reasons}, index=geoms.index)


def _reason_category(r: str) -> str:
    return re.sub(r"\[.*", "", r).strip() if r else ""


def _missing(df: pd.DataFrame) -> dict:
    out = {}
    for c in df.columns:
        if c == "geometry":
            continue
        s = df[c]
        n = s.isna() | (s.astype(str).str.strip().isin(["", "None", "nan"]) if s.dtype == object else False)
        out[c] = int(n.sum())
    return out


# --------------------------------------------------------------------------- GLIMS polygons
def process_glims_polygons(shp: Path) -> tuple[dict, set[str]]:
    rec = new_record("glims_polygons", "GLIMS glacier outlines (polygons)", [shp.with_suffix(s) for s in (".shp", ".shx", ".dbf", ".prj")],
                     "vector_polygons", "GLIMS / NSIDC")
    ids: set[str] = set()
    try:
        info = pyogrio.read_info(shp)
        rec["metrics"]["global_feature_count"] = int(info["features"])
        rec["metrics"]["crs"] = info["crs"]
        rec["metrics"]["geometry_type"] = info["geometry_type"]
        rec["metrics"]["fields"] = dict(zip(info["fields"], map(str, info["dtypes"])))
        rec["metrics"]["global_bounds"] = [float(v) for v in info["total_bounds"]] if info.get("total_bounds") is not None else None
        step(rec, f"Shapefile: {info['features']:,} {info['geometry_type']} features, CRS {info['crs']}, {len(info['fields'])} attribute fields")

        cols = ["glac_id", "anlys_id", "line_type", "rec_status", "gtng_o1reg", "geog_area", "glac_stat"]
        g = pyogrio.read_dataframe(shp, read_geometry=False, columns=cols)
        step(rec, f"Global attribute pass (no geometry, {len(cols)} columns) over all {len(g):,} features")
        rec["metrics"]["global_line_type_counts"] = g.line_type.value_counts().to_dict()
        rec["metrics"]["global_rgi_o1_region_counts"] = {str(int(k)) if pd.notna(k) else "missing": int(v)
                                                         for k, v in g.gtng_o1reg.value_counts(dropna=False).items()}
        rec["metrics"]["global_missing_selected_columns"] = _missing(g)
        rec["metrics"]["global_duplicate_glac_anlys_linetype"] = int(g.duplicated(["glac_id", "anlys_id", "line_type"]).sum())
        n_ant = int((g.gtng_o1reg == GLIMS_ANTARCTIC_O1REG).sum())
        del g

        gdf = pyogrio.read_dataframe(shp, where=f"gtng_o1reg = {GLIMS_ANTARCTIC_O1REG}")
        step(rec, f"Antarctic subset read with attribute filter gtng_o1reg = {GLIMS_ANTARCTIC_O1REG} (RGI 'Antarctic and Subantarctic'): {len(gdf):,} features")
        assert len(gdf) == n_ant, "attribute-filter count mismatch"
        rec["metrics"]["records_before"] = rec["metrics"]["global_feature_count"]
        rec["metrics"]["antarctic_features"] = int(len(gdf))
        rec["metrics"]["antarctic_line_type_counts"] = gdf.line_type.value_counts().to_dict()
        rec["metrics"]["antarctic_geog_area_counts"] = gdf.geog_area.value_counts().to_dict()
        rec["metrics"]["antarctic_rec_status_counts"] = gdf.rec_status.value_counts().to_dict()

        v = _validity(gdf.geometry)
        rng = _coord_range_flags(gdf.geometry)
        gdf = gdf.join(v).join(rng)
        gdf["invalid_category"] = gdf.invalid_reason.map(_reason_category)
        n_invalid = int((~gdf.geom_valid).sum())
        rec["metrics"]["geometry_null"] = int(v.geom_null.sum())
        rec["metrics"]["geometry_empty"] = int(v.geom_empty.sum())
        rec["metrics"]["geometry_invalid"] = n_invalid
        rec["metrics"]["geometry_invalid_categories"] = gdf.loc[~gdf.geom_valid, "invalid_category"].value_counts().to_dict()
        rec["metrics"]["coordinates_out_of_range"] = int((rng.lon_out_of_range | rng.lat_out_of_range).sum())
        b = gdf.total_bounds
        rec["metrics"]["antarctic_bounds_lonlat"] = [float(x) for x in b]
        rec["metrics"]["features_north_of_60S"] = int((gdf.geometry.bounds.maxy > -60).sum())
        step(rec, f"Geometry validation: {n_invalid} invalid, {rec['metrics']['geometry_empty']} empty, "
                  f"{rec['metrics']['coordinates_out_of_range']} with out-of-range coordinates")
        if n_invalid:
            issue(rec, "warning", "invalid_geometry", f"Invalid polygons: {rec['metrics']['geometry_invalid_categories']} "
                  "(original geometry retained; repaired copy written to a separate layer)", n_invalid)
        if rec["metrics"]["features_north_of_60S"]:
            issue(rec, "info", "scope_note", "RGI region 19 includes sub-Antarctic islands north of 60 S (e.g. Kerguelen, "
                  "South Georgia); retained and flagged via column north_of_60S", rec["metrics"]["features_north_of_60S"])
        gdf["north_of_60S"] = gdf.geometry.bounds.maxy > -60

        # Areas: equal-area projection (EASE-Grid 2.0 South) to cross-check the reported km^2 fields.
        ea = gdf.geometry.to_crs(EPSG_EASE2_SOUTH)
        gdf["area_km2_computed_ease2"] = np.where(gdf.geom_valid, ea.area / 1e6, np.nan)
        rel_diff = (gdf.area_km2_computed_ease2 - gdf.db_area) / gdf.db_area
        gdf["flag_area_mismatch_gt5pct"] = rel_diff.abs() > 0.05
        rec["metrics"]["db_area_km2_summary"] = num_summary(gdf.db_area)
        rec["metrics"]["area_field_km2_summary"] = num_summary(gdf.area)
        rec["metrics"]["computed_area_vs_db_area_median_rel_diff"] = float(np.nanmedian(rel_diff))
        rec["metrics"]["area_mismatch_gt5pct"] = int(gdf.flag_area_mismatch_gt5pct.sum())
        rec["metrics"]["nonpositive_db_area"] = int((gdf.db_area <= 0).sum())
        step(rec, f"Computed polygon areas in EPSG:{EPSG_EASE2_SOUTH}; median relative difference vs db_area = "
                  f"{rec['metrics']['computed_area_vs_db_area_median_rel_diff']:.5f} (confirms db_area is km^2)")
        if rec["metrics"]["area_mismatch_gt5pct"]:
            issue(rec, "info", "suspicious_value", "Computed area differs from db_area by >5% (flagged, retained)", rec["metrics"]["area_mismatch_gt5pct"])

        # Duplicates
        dup_key = gdf.duplicated(["glac_id", "anlys_id", "line_type"], keep=False)
        wkb = gdf.geometry.to_wkb()
        dup_geom = wkb.duplicated(keep=False)
        gdf["flag_duplicate_key"] = dup_key
        gdf["flag_duplicate_geometry"] = dup_geom
        rec["metrics"]["duplicate_key_rows"] = int(dup_key.sum())
        rec["metrics"]["duplicate_geometry_rows"] = int(dup_geom.sum())
        gb = gdf[gdf.line_type == "glac_bound"]
        per_glacier = gb.groupby("glac_id").anlys_id.nunique()
        rec["metrics"]["glaciers_unique"] = int(gb.glac_id.nunique())
        rec["metrics"]["glaciers_with_multiple_analyses"] = int((per_glacier > 1).sum())
        if dup_geom.any():
            issue(rec, "warning", "duplicate_geometry", "Byte-identical geometries (retained, flagged)", int(dup_geom.sum()))

        # Overlaps between glacier outlines (glac_bound, valid only), in equal-area metres.
        gbv = gb[gb.geom_valid]
        geoms = ea.loc[gbv.index].values
        tree = shapely.STRtree(geoms)
        left, right = tree.query(geoms, predicate="intersects")
        m = left < right
        left, right = left[m], right[m]
        inter = shapely.area(shapely.intersection(geoms[left], geoms[right]))
        same = gbv.glac_id.values[left] == gbv.glac_id.values[right]
        pos = inter > 0
        big = inter > 1e4  # > 0.01 km^2
        rec["metrics"]["overlap_pairs_intersecting"] = int(len(left))
        rec["metrics"]["overlap_pairs_area_gt0_different_glacier"] = int((pos & ~same).sum())
        rec["metrics"]["overlap_pairs_area_gt_0p01km2_different_glacier"] = int((big & ~same).sum())
        rec["metrics"]["overlap_pairs_same_glacier_multitemporal"] = int((pos & same).sum())
        rec["metrics"]["overlap_area_km2_different_glacier_total"] = float(inter[pos & ~same].sum() / 1e6)
        step(rec, f"Overlap analysis on {len(gbv):,} valid glac_bound outlines: {len(left):,} intersecting pairs, "
                  f"{int((big & ~same).sum()):,} pairs of DIFFERENT glaciers overlapping by >0.01 km^2")
        if (big & ~same).any():
            issue(rec, "warning", "overlapping_features", "Different-glacier outline pairs overlapping >0.01 km^2 (flagged)", int((big & ~same).sum()))
        ov = pd.Series(0, index=gbv.index)
        for idx in np.concatenate([gbv.index.values[left[big & ~same]], gbv.index.values[right[big & ~same]]]):
            ov[idx] += 1
        gdf["overlap_partner_count"] = ov.reindex(gdf.index).fillna(0).astype(int)

        miss = _missing(gdf.drop(columns=[c for c in gdf.columns if c.startswith(("geom_", "flag_", "lon_out", "lat_out"))]))
        rec["metrics"]["antarctic_missing_by_attribute"] = miss
        n_attr_cells = len(gdf) * len(info["fields"])
        rec["metrics"]["missing_count"] = int(sum(miss[f] for f in info["fields"] if f in miss))
        rec["metrics"]["missing_percent"] = round(100 * rec["metrics"]["missing_count"] / n_attr_cells, 3)

        GLIMS_GPKG.parent.mkdir(parents=True, exist_ok=True)
        if GLIMS_GPKG.exists():
            GLIMS_GPKG.unlink()   # pipeline-owned output; rebuilt deterministically each run
        gdf.to_file(GLIMS_GPKG, layer="polygons", driver="GPKG", engine="pyogrio")
        bad = gdf[~gdf.geom_valid & ~gdf.geom_null].copy()
        if len(bad):
            bad["geometry"] = shapely.make_valid(bad.geometry.values)
            bad["repair_method"] = "shapely.make_valid (GEOS MakeValid, structure method)"
            bad[["glac_id", "anlys_id", "line_type", "invalid_reason", "repair_method", "geometry"]] \
                .to_file(GLIMS_GPKG, layer="polygons_invalid_repaired", driver="GPKG", engine="pyogrio")
            step(rec, f"Wrote {len(bad)} repaired copies of invalid polygons to layer polygons_invalid_repaired (originals untouched)")
        chk = pyogrio.read_info(GLIMS_GPKG, layer="polygons")
        rec["metrics"]["records_after"] = int(chk["features"])
        rec["metrics"]["excluded_records"] = rec["metrics"]["records_before"] - rec["metrics"]["records_after"]
        rec["metrics"]["exclusion_reason"] = f"Outside GLIMS/RGI first-order region {GLIMS_ANTARCTIC_O1REG} (non-Antarctic glaciers); source shapefile retained"
        rec["validation"] = {"output_reopened": True, "feature_count_matches": chk["features"] == len(gdf),
                             "crs_preserved": "4326" in str(chk["crs"]), "all_source_fields_preserved": set(info["fields"]) <= set(chk["fields"])}
        add_output(rec, GLIMS_GPKG, "gpkg", "Layer 'polygons': RGI-19 outlines, original geometry + validity/duplicate/overlap/area flags; "
                   "layer 'polygons_invalid_repaired': repaired copies")
        ids = set(gdf.glac_id.dropna())
        return finish(rec, "processed" if all(rec["validation"].values()) else "partially_processed"), ids
    except Exception as e:
        rec["errors"].append(f"{type(e).__name__}: {e}")
        return finish(rec, "failed"), ids


def process_glims_points(shp: Path, antarctic_ids: set[str]) -> dict:
    rec = new_record("glims_points", "GLIMS glacier representative points", [shp.with_suffix(s) for s in (".shp", ".shx", ".dbf", ".prj")],
                     "vector_points", "GLIMS / NSIDC")
    try:
        gdf = pyogrio.read_dataframe(shp)
        rec["metrics"]["records_before"] = int(len(gdf))
        rec["metrics"]["crs"] = str(gdf.crs)
        x, y = gdf.geometry.x, gdf.geometry.y
        z = shapely.get_z(gdf.geometry.values)
        rec["metrics"]["lon_gt_180"] = int((x > 180).sum())
        rec["metrics"]["lon_lt_minus180"] = int((x < -180).sum())
        rec["metrics"]["lat_out_of_range"] = int(((y < -90) | (y > 90)).sum())
        rec["metrics"]["z_summary"] = num_summary(z)
        rec["metrics"]["null_or_empty_geometry"] = int((gdf.geometry.isna() | gdf.geometry.is_empty).sum())
        rec["metrics"]["duplicate_glacier_id"] = int(gdf.glacier_id.duplicated().sum())
        rec["metrics"]["missing_glacier_id"] = int(gdf.glacier_id.isna().sum())
        rec["metrics"]["missing_count"] = rec["metrics"]["missing_glacier_id"]
        rec["metrics"]["missing_percent"] = round(100 * rec["metrics"]["missing_glacier_id"] / len(gdf), 3)
        step(rec, f"{len(gdf):,} points; {rec['metrics']['lon_gt_180']} with longitude > 180 (0-360 convention), "
                  f"{rec['metrics']['duplicate_glacier_id']:,} duplicate glacier_id")
        if rec["metrics"]["lon_gt_180"]:
            issue(rec, "warning", "invalid_coordinate", "Longitudes > 180 deg in a WGS84 (-180..180) layer; retained, flagged "
                  "(column lon_wrapped gives lon-360 for use)", rec["metrics"]["lon_gt_180"])
        if rec["metrics"]["duplicate_glacier_id"]:
            issue(rec, "info", "duplicate_identifier", "glacier_id repeated (multiple points per glacier)", rec["metrics"]["duplicate_glacier_id"])
        gdf["flag_lon_gt_180"] = x > 180
        gdf["lon_wrapped"] = np.where(x > 180, x - 360, x)
        gdf["in_rgi19_polygon_set"] = gdf.glacier_id.isin(antarctic_ids)
        gdf["south_of_60S"] = y <= -60
        ant = gdf[gdf.in_rgi19_polygon_set | gdf.south_of_60S].copy()
        rec["metrics"]["antarctic_points"] = int(len(ant))
        rec["metrics"]["antarctic_points_south_of_60S_not_in_rgi19_polygons"] = int((ant.south_of_60S & ~ant.in_rgi19_polygon_set).sum())
        rgi_pts = set(gdf.loc[gdf.in_rgi19_polygon_set, "glacier_id"])
        rec["metrics"]["rgi19_glaciers_without_point"] = int(len(antarctic_ids - rgi_pts))
        ant.to_file(GLIMS_GPKG, layer="points", driver="GPKG", engine="pyogrio")
        chk = pyogrio.read_info(GLIMS_GPKG, layer="points")
        rec["metrics"]["records_after"] = int(chk["features"])
        rec["metrics"]["excluded_records"] = int(len(gdf) - len(ant))
        rec["metrics"]["exclusion_reason"] = "Not linked to an RGI-19 glacier and north of 60 S (outside Antarctic scope)"
        rec["validation"] = {"output_reopened": True, "feature_count_matches": chk["features"] == len(ant)}
        add_output(rec, GLIMS_GPKG, "gpkg", "Layer 'points': Antarctic glacier points with coordinate flags")
        return finish(rec, "processed")
    except Exception as e:
        rec["errors"].append(f"{type(e).__name__}: {e}")
        return finish(rec, "failed")


def process_glims_images(shp: Path) -> dict:
    rec = new_record("glims_images", "GLIMS source-image footprints (points)", [shp.with_suffix(s) for s in (".shp", ".shx", ".dbf", ".prj")],
                     "vector_points", "GLIMS / NSIDC")
    try:
        gdf = pyogrio.read_dataframe(shp)
        x, y = gdf.geometry.x, gdf.geometry.y
        rec["metrics"]["records_before"] = int(len(gdf))
        rec["metrics"]["fields"] = list(gdf.columns.drop("geometry"))
        rec["metrics"]["lat_out_of_range"] = int(((y < -90) | (y > 90)).sum())
        rec["metrics"]["lon_out_of_range"] = int(((x < -180) | (x > 180)).sum())
        rec["metrics"]["est_loc_counts"] = gdf.est_loc.value_counts().to_dict()
        t = pd.to_datetime(gdf.acq_time, errors="coerce", utc=True)
        rec["metrics"]["acq_time_unparseable"] = int(t.isna().sum() - gdf.acq_time.isna().sum())
        rec["metrics"]["acq_time_range"] = [str(t.min()), str(t.max())]
        rec["metrics"]["instrument_counts"] = gdf.inst_sname.value_counts().head(15).to_dict()
        rec["metrics"]["duplicate_orig_id"] = int(gdf.orig_id.duplicated().sum())
        miss = _missing(gdf)
        rec["metrics"]["missing_by_column"] = miss
        rec["metrics"]["missing_count"] = int(sum(miss.values()))
        rec["metrics"]["missing_percent"] = round(100 * sum(miss.values()) / (len(gdf) * len(miss)), 3)
        step(rec, f"{len(gdf):,} image points; {rec['metrics']['lat_out_of_range']} with latitude outside [-90, 90]")
        if rec["metrics"]["lat_out_of_range"]:
            issue(rec, "error", "invalid_coordinate", "Image locations with latitude outside [-90, 90] (retained, flagged)", rec["metrics"]["lat_out_of_range"])
        issue(rec, "info", "missing_link", "Layer has no glac_id field in this export, so images cannot be joined to glaciers", None)
        gdf["flag_coord_invalid"] = (y < -90) | (y > 90) | (x < -180) | (x > 180)
        gdf["acq_time_utc"] = t.astype(str)
        gdf["south_of_60S"] = (y <= -60) & ~gdf.flag_coord_invalid
        gdf.to_file(GLIMS_GPKG, layer="images_all_flagged", driver="GPKG", engine="pyogrio")
        chk = pyogrio.read_info(GLIMS_GPKG, layer="images_all_flagged")
        rec["metrics"]["antarctic_images_south_of_60S"] = int(gdf.south_of_60S.sum())
        rec["metrics"]["records_after"] = int(chk["features"])
        rec["metrics"]["excluded_records"] = 0
        rec["validation"] = {"output_reopened": True, "feature_count_matches": chk["features"] == len(gdf)}
        add_output(rec, GLIMS_GPKG, "gpkg", "Layer 'images_all_flagged': all image points with coordinate-validity and south_of_60S flags")
        return finish(rec, "processed")
    except Exception as e:
        rec["errors"].append(f"{type(e).__name__}: {e}")
        return finish(rec, "failed")


def process_glims_lines(shp: Path) -> dict:
    rec = new_record("glims_lines", "GLIMS glacier lines (snow lines / centre lines)", [shp.with_suffix(s) for s in (".shp", ".shx", ".dbf", ".prj")],
                     "vector_lines", "GLIMS / NSIDC")
    try:
        info = pyogrio.read_info(shp)
        rec["metrics"].update({"records_before": int(info["features"]), "records_after": int(info["features"]),
                               "geometry_type": info["geometry_type"], "crs": info["crs"], "fields": list(info["fields"])})
        step(rec, f"Opened lines layer: {info['features']} features")
        if info["features"] == 0:
            issue(rec, "info", "empty_layer", "Layer is empty: the GLIMS query returned no snow/centre lines (per README this is expected when no line data match)", 0)
        rec["validation"] = {"opened": True, "schema_readable": True}
        return finish(rec, "validated")
    except Exception as e:
        rec["errors"].append(f"{type(e).__name__}: {e}")
        return finish(rec, "failed")


# --------------------------------------------------------------------------- PGC / NCALM KMZ tile index
KML_NS = {"k": "http://www.opengis.net/kml/2.2"}
_ATTR_RE = re.compile(r"<B>([^<]+)</B>\s*=\s*(.*?)(?:<BR>|$)", re.S)


def parse_kmz_tiles(kmz: Path) -> gpd.GeoDataFrame:
    with zipfile.ZipFile(kmz) as z:
        kml_name = next(n for n in z.namelist() if n.lower().endswith(".kml"))
        root = ET.fromstring(z.read(kml_name))
    rows = []
    for pm in root.iter("{http://www.opengis.net/kml/2.2}Placemark"):
        desc = pm.findtext("k:description", default="", namespaces=KML_NS)
        attrs = {k.strip(): re.sub(r"<[^>]+>", "", v).strip() for k, v in _ATTR_RE.findall(desc)}
        coords_txt = pm.findtext(".//k:outerBoundaryIs/k:LinearRing/k:coordinates", default="", namespaces=KML_NS)
        pts = [tuple(map(float, c.split(","))) for c in coords_txt.split()]
        geom = shapely.Polygon([(p[0], p[1]) for p in pts]) if len(pts) >= 4 else None
        attrs["n_vertices"] = len(pts)
        attrs["z_all_zero"] = all(len(p) < 3 or p[2] == 0 for p in pts)
        attrs["geometry"] = geom
        rows.append(attrs)
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    for c in ["Pt_Count", "Pt_Spacing", "Z_Min", "Z_Max"]:
        if c in gdf:
            gdf[c] = pd.to_numeric(gdf[c], errors="coerce")
    return gdf


def process_pgc_kmz(kmz: Path, related: list[Path]) -> dict:
    rec = new_record("pgc_ncalm_dv_lidar_tiles", "NCALM McMurdo Dry Valleys LiDAR (2014) LAS tile index", [kmz, *related],
                     "vector_polygons", "Polar Geospatial Center (PGC) / NCALM")
    try:
        gdf = parse_kmz_tiles(kmz)
        rec["metrics"]["records_before"] = int(len(gdf))
        rec["metrics"]["fields"] = [c for c in gdf.columns if c != "geometry"]
        step(rec, f"Parsed KMZ (zipped KML 2.2): {len(gdf):,} tile placemarks; attributes extracted from HTML descriptions: {rec['metrics']['fields']}")
        gdf = gdf.rename(columns={"FileName": "las_file", "Pt_Count": "point_count", "Pt_Spacing": "point_spacing_m",
                                  "Z_Min": "z_min_m", "Z_Max": "z_max_m", "http_url": "las_url"})
        step(rec, "Renamed FileName->las_file, Pt_Count->point_count, Pt_Spacing->point_spacing_m, Z_Min->z_min_m, Z_Max->z_max_m, http_url->las_url "
                  "(units assumed metres: PGC elevation products; not stated in the KML)")
        v = _validity(gdf.geometry)
        gdf = gdf.join(v)
        rec["metrics"]["geometry_invalid"] = int((~v.geom_valid).sum())
        rec["metrics"]["geometry_null"] = int(v.geom_null.sum())
        rec["metrics"]["duplicate_las_file"] = int(gdf.las_file.duplicated().sum())
        rec["metrics"]["duplicate_geometry"] = int(gdf.geometry.to_wkb().duplicated().sum())
        rec["metrics"]["z_min_gt_z_max"] = int((gdf.z_min_m > gdf.z_max_m).sum())
        rec["metrics"]["nonpositive_point_count"] = int((gdf.point_count <= 0).sum())
        rec["metrics"]["point_count_summary"] = num_summary(gdf.point_count)
        rec["metrics"]["point_spacing_summary_m"] = num_summary(gdf.point_spacing_m)
        rec["metrics"]["elevation_range_m"] = [float(gdf.z_min_m.min()), float(gdf.z_max_m.max())]
        rec["metrics"]["sites"] = gdf.site_name.value_counts().to_dict()
        rec["metrics"]["total_points"] = int(gdf.point_count.sum())
        rec["metrics"]["bounds_lonlat"] = [float(x) for x in gdf.total_bounds]
        miss = _missing(gdf.drop(columns=["geom_null", "geom_empty", "geom_valid", "invalid_reason"]))
        rec["metrics"]["missing_by_column"] = {k: v for k, v in miss.items() if v}
        rec["metrics"]["missing_count"] = int(sum(miss.values()))
        rec["metrics"]["missing_percent"] = round(100 * sum(miss.values()) / (len(gdf) * len(miss)), 3)
        ps = gdf.to_crs(EPSG_ANTARCTIC_PS)
        gdf["tile_area_m2_ps3031"] = ps.area
        geoms = ps.geometry.values
        tree = shapely.STRtree(geoms)
        l, r = tree.query(geoms, predicate="intersects")
        m = l < r
        inter = shapely.area(shapely.intersection(geoms[l[m]], geoms[r[m]]))
        same_site = gdf.site_name.values[l[m]] == gdf.site_name.values[r[m]]
        rec["metrics"]["tile_pairs_overlapping_area_gt1m2"] = int((inter > 1).sum())
        rec["metrics"]["tile_pairs_overlapping_cross_site"] = int(((inter > 1) & ~same_site).sum())
        step(rec, f"Overlap check in EPSG:{EPSG_ANTARCTIC_PS}: {int((inter > 1).sum())} tile pairs overlap by >1 m^2 "
                  f"({int(((inter > 1) & ~same_site).sum())} across different sites)")
        for k, sev, kind, msg in [("geometry_invalid", "warning", "invalid_geometry", "Invalid tile polygons"),
                                  ("duplicate_las_file", "warning", "duplicate_identifier", "Duplicate LAS file names"),
                                  ("z_min_gt_z_max", "error", "invalid_value", "Z_Min > Z_Max"),
                                  ("tile_pairs_overlapping_cross_site", "info", "overlapping_features", "Tiles from different sites overlap")]:
            if rec["metrics"][k]:
                issue(rec, sev, kind, msg, rec["metrics"][k])
        out = PROCESSED_DIR / "pgc" / "ncalm_dv_lidar_tile_index.gpkg"
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            out.unlink()
        gdf.to_file(out, layer="tiles", driver="GPKG", engine="pyogrio")
        site = gdf.groupby("site_name").agg(tiles=("las_file", "count"), points=("point_count", "sum"),
                                            z_min_m=("z_min_m", "min"), z_max_m=("z_max_m", "max"),
                                            median_spacing_m=("point_spacing_m", "median"), area_km2=("tile_area_m2_ps3031", lambda a: a.sum() / 1e6))
        site.to_csv(out.parent / "ncalm_dv_lidar_site_summary.csv")
        chk = gpd.read_file(out, layer="tiles", engine="pyogrio")
        rec["metrics"]["records_after"] = int(len(chk))
        rec["metrics"]["excluded_records"] = 0
        rec["validation"] = {"output_reopened": True, "feature_count_matches": len(chk) == len(gdf),
                             "crs_epsg4326": chk.crs.to_epsg() == 4326, "all_tiles_south_of_60S": bool(chk.total_bounds[3] < -60)}
        add_output(rec, out, "gpkg", "Tile polygons (EPSG:4326) with LAS metadata, validity flags and polar-stereographic area")
        add_output(rec, out.parent / "ncalm_dv_lidar_site_summary.csv", "csv", "Per-site tile/point/elevation summary")
        rec["notes"].append("Only the tile INDEX is local; the LAS point clouds referenced by las_url were not downloaded.")
        return finish(rec, "processed" if all(rec["validation"].values()) else "partially_processed")
    except Exception as e:
        rec["errors"].append(f"{type(e).__name__}: {e}")
        return finish(rec, "failed")


# --------------------------------------------------------------------------- TIFF image
def process_tiff_image(tif: Path) -> dict:
    import rasterio
    from rasterio.errors import NotGeoreferencedWarning
    rec = new_record("ags_glacier_photograph", "Glacier photograph image AGS_A_2002_04 (provenance unverified)", [tif],
                     "raster_image", "unverified")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", NotGeoreferencedWarning)
            with rasterio.open(tif) as r:
                prof = r.profile
                tags = r.tags()
                exif = r.tags(ns="EXIF")
                stats = []
                for b in range(1, r.count + 1):
                    mins, maxs, s, ss, n = 255, 0, 0.0, 0.0, 0
                    for _, win in r.block_windows(b):
                        a = r.read(b, window=win).astype("float64")
                        mins, maxs = min(mins, a.min()), max(maxs, a.max())
                        s += a.sum(); ss += (a ** 2).sum(); n += a.size
                    mean = s / n
                    stats.append({"band": b, "min": mins, "max": maxs, "mean": mean, "std": float(np.sqrt(ss / n - mean ** 2))})
                georef = r.crs is not None or not r.transform.is_identity or bool(r.gcps[0])
        rec["metrics"] = {"width": prof["width"], "height": prof["height"], "bands": prof["count"], "dtype": prof["dtype"],
                          "nodata": prof["nodata"], "crs": str(prof["crs"]), "georeferenced": georef,
                          "software": tags.get("TIFFTAG_SOFTWARE"), "tiff_datetime": tags.get("TIFFTAG_DATETIME"),
                          "exif_datetime_original": exif.get("EXIF_DateTimeOriginal"), "band_stats": stats,
                          "records_before": f"{prof['count']}x{prof['height']}x{prof['width']}",
                          "records_after": "not transformed"}
        step(rec, f"Opened {prof['width']}x{prof['height']} {prof['count']}-band {prof['dtype']} TIFF; CRS={prof['crs']}; georeferenced={georef}")
        rec["domain_relevance"] = "unverified"
        if not georef:
            issue(rec, "warning", "no_spatial_reference", "No CRS, geotransform or GCPs: this is an RGB photograph (Adobe Photoshop), "
                  "not a GeoTIFF; it cannot be used as spatial data", None)
        issue(rec, "info", "provenance_unknown", "No embedded description of the subject, location or source; the 'AGS' prefix "
              "could not be matched to a verified source", None)
        rec["validation"] = {"opened": True, "all_blocks_readable": True}
        return finish(rec, "validated")
    except Exception as e:
        rec["errors"].append(f"{type(e).__name__}: {e}")
        return finish(rec, "failed")
