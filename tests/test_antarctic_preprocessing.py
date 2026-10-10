"""Tests for the Antarctic preprocessing pipeline.

Unit tests use small synthetic fixtures created in tmp_path (never reported as results).
Integration tests check the real pipeline outputs and are skipped if the pipeline has not been run.

    python -m pytest tests/test_antarctic_preprocessing.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from data.src.preprocessing.antarctic import config, era5_api, handlers_netcdf, handlers_tabular, inventory

ROOT = config.ROOT


# --------------------------------------------------------------------------- unit tests
def test_parse_glims_id_south_and_wrap():
    lon, lat = handlers_tabular.parse_glims_id("G295123E64321S")
    assert lat == pytest.approx(-64.321)
    assert lon == pytest.approx(295.123 - 360)
    assert np.isnan(handlers_tabular.parse_glims_id("bad")[0])


def test_sniff_format_magic_bytes(tmp_path):
    (tmp_path / "a.nc").write_bytes(b"\x89HDF\r\n\x1a\n" + b"\0" * 10)
    (tmp_path / "b.tif").write_bytes(b"II*\x00" + b"\0" * 10)
    (tmp_path / "c.kmz").write_bytes(b"PK\x03\x04" + b"\0" * 10)
    (tmp_path / "d.json").write_text('[{"a": 1}]')
    (tmp_path / "e.json").write_text('[{"a": 1}')
    assert inventory.sniff_format(tmp_path / "a.nc") == "NetCDF-4/HDF5"
    assert inventory.sniff_format(tmp_path / "b.tif") == "TIFF"
    assert inventory.sniff_format(tmp_path / "c.kmz").startswith("KMZ")
    assert inventory.sniff_format(tmp_path / "d.json") == "JSON"
    assert inventory.sniff_format(tmp_path / "e.json") == "JSON (invalid)"


def test_monthly_continuity_detects_gaps_and_duplicates():
    t = pd.DatetimeIndex(["2000-01-15", "2000-02-15", "2000-02-15", "2000-05-15"])
    c = handlers_netcdf.monthly_continuity(t)
    assert c["duplicate_months"] == ["2000-02"]
    assert c["missing_months"] == ["2000-03", "2000-04"]


def test_nsidc_climatology_parser(tmp_path):
    p = tmp_path / "S_clim.csv"
    p.write_text("std Years = 1981-2010\nDOY,   Average Extent,   Std Deviation,      10th,      25th,      50th,      75th,      90th\n"
                 "001,  5.0, 0.3, 4.6, 4.8, 5.0, 5.2, 5.4\n002,  4.9, 0.3, 4.5, 4.7, 4.9, 5.1, 5.3\n")
    df, meta = handlers_tabular.read_nsidc_climatology(p)
    assert meta == "std Years = 1981-2010"
    assert list(df.columns)[:2] == ["doy", "mean_extent_mkm2"]
    assert df.mean_extent_mkm2.tolist() == [5.0, 4.9]


def test_edsc_normalize_preserves_nested():
    rec = {"provider": "P", "shortName": "S", "version": "1", "title": "T", "processingLevel": {"id": "2"},
           "platforms": [{"shortName": "SAT", "type": "x", "instruments": [{"shortName": "I", "operationalModes": ["Antarctic"]}]}],
           "timeStart": "2000-01-01T00:00:00.000Z", "timeEnd": None}
    n = handlers_tabular.normalize_edsc_record(rec)
    assert n["instruments"] == "I" and n["operational_modes"] == "Antarctic"
    assert json.loads(n["platforms_json"]) == rec["platforms"]
    assert n["time_end_original"] is None


def test_api_scripts_parsed_without_execution():
    for script, ds in [("API.py", "reanalysis-era5-single-levels"), ("PRESSUREAPI.py", "reanalysis-era5-pressure-levels")]:
        p = era5_api.parse_api_script(config.API_DIR / script)
        assert p["dataset"] == ds
        assert p["request"]["data_format"] == "netcdf"
        assert "retrieve" in p["calls"]


def test_request_estimate_counts_calendar():
    req = {"variable": ["2m_temperature"], "year": ["2001"], "month": ["02"], "day": [f"{d:02d}" for d in range(1, 32)], "time": ["00:00"]}
    import datetime as dt
    e = era5_api.estimate_request(req, today=dt.date(2026, 1, 1))
    assert e["valid_dates"] == 28 and e["invalid_calendar_dates_ignored"] == 3 and e["fields"] == 28


def _synthetic_era5(path, pressure: bool, dup_time=False):
    t = pd.date_range("2020-01-01", periods=4, freq="6h")
    if dup_time:
        t = t.insert(2, t[1])
    lat = np.arange(-50, -90.25, -0.25)
    lon = np.arange(0, 2, 0.25)
    if pressure:
        lev = np.array([1000, 850, 500], dtype=float)
        data = 230 + np.random.default_rng(0).random((len(t), 3, lat.size, lon.size))
        ds = xr.Dataset({"t": (("valid_time", "pressure_level", "latitude", "longitude"), data, {"units": "K"})},
                        coords={"valid_time": t, "pressure_level": lev, "latitude": lat, "longitude": lon},
                        attrs={"GRIB_centre": "ecmf", "institution": "European Centre for Medium-Range Weather Forecasts"})
    else:
        data = 250 + np.random.default_rng(1).random((len(t), lat.size, lon.size))
        data[0, 0, 0] = np.nan
        ds = xr.Dataset({"t2m": (("valid_time", "latitude", "longitude"), data, {"units": "K"}),
                         "msl": (("valid_time", "latitude", "longitude"), 98000 + 0 * data, {"units": "Pa"})},
                        coords={"valid_time": t, "latitude": lat, "longitude": lon},
                        attrs={"institution": "European Centre for Medium-Range Weather Forecasts"})
    ds.to_netcdf(path)
    return path


def test_era5_detection_and_coordinate_validation(tmp_path):
    s = _synthetic_era5(tmp_path / "s.nc", pressure=False, dup_time=True)
    p = _synthetic_era5(tmp_path / "p.nc", pressure=True)
    assert era5_api._looks_like_era5(s) == "single_levels"
    assert era5_api._looks_like_era5(p) == "pressure_levels"
    with xr.open_dataset(s) as ds:
        c = era5_api.validate_era5_coords(ds, "single_levels")
        assert c["time_duplicates"] == 1 and c["lat_order"] == "descending"
        st = era5_api._var_stats(ds["t2m"], "valid_time")
        assert st["missing"] == 1 and st["units_match"] is True and st["below_plausible"] == 0
    with xr.open_dataset(p) as ds:
        c = era5_api.validate_era5_coords(ds, "pressure_levels")
        assert c["levels_hPa"] == [1000.0, 850.0, 500.0] and c["levels_nonstandard"] == [] and c["level_order"] == "descending"


def test_era5_file_processing_writes_antarctic_subset(tmp_path, monkeypatch):
    monkeypatch.setattr(era5_api, "PROCESSED_DIR", tmp_path / "processed")
    import data.src.preprocessing.antarctic.common as common
    monkeypatch.setattr(common, "QUALITY_DIR", tmp_path / "quality")
    p = _synthetic_era5(tmp_path / "p.nc", pressure=True)
    rec = era5_api.process_era5_file(p, "pressure_levels")
    assert rec["status"] == "processed", rec["errors"]
    out = [o["path"] for o in rec["outputs"] if o["kind"] == "netcdf"][0]
    with xr.open_dataset(out) as ds:
        assert float(ds.latitude.max()) <= -60 and "t" in ds and ds.sizes["pressure_level"] == 3


# --------------------------------------------------------------------------- integration tests on real outputs
needs_run = pytest.mark.skipif(not config.INVENTORY_CSV.exists(), reason="pipeline has not been run")


@needs_run
def test_inventory_covers_all_raw_files():
    inv = pd.read_csv(config.INVENTORY_CSV)
    on_disk = {p.relative_to(ROOT).as_posix() for p in config.RAW_DIR.rglob("*") if p.is_file()}
    assert set(inv.relative_path) == on_disk
    assert inv.processing_status.notna().all()


@needs_run
def test_raw_files_unchanged_sizes():
    inv = pd.read_csv(config.INVENTORY_PRERUN_CSV)
    for r in inv.itertuples():
        assert (ROOT / r.relative_path).stat().st_size == r.size_bytes


@needs_run
def test_quality_reports_match_outputs():
    for q in config.QUALITY_DIR.glob("*.json"):
        rec = json.loads(q.read_text(encoding="utf-8"))
        for o in rec["outputs"]:
            assert (ROOT / o["path"]).exists(), o["path"]
        if rec["status"] == "processed":
            assert all(v for v in rec["validation"].values() if isinstance(v, bool)), rec["dataset_id"]


@needs_run
def test_omi_output_reopens_with_expected_schema():
    p = config.PROCESSED_DIR / "sea_ice_extent" / "cmems_omi_si_extent_monthly.csv"
    df = pd.read_csv(p)
    q = json.loads((config.QUALITY_DIR / "cmems_omi_si_extent.json").read_text(encoding="utf-8"))
    assert len(df) == q["metrics"]["records_after"] == 552
    assert {"time", "siextent_km2", "anomaly_km2", "flag_missing"} <= set(df.columns)
    assert df.flag_missing.sum() == q["metrics"]["missing_count"]
    assert pd.to_datetime(df.time).is_monotonic_increasing


@needs_run
def test_glims_geopackage_layers():
    import pyogrio
    gpkg = config.PROCESSED_DIR / "glims" / "glims_antarctic_rgi19.gpkg"
    layers = {l[0] for l in pyogrio.list_layers(gpkg)}
    assert {"polygons", "points", "images_all_flagged"} <= layers
    info = pyogrio.read_info(gpkg, layer="polygons")
    q = json.loads((config.QUALITY_DIR / "glims_polygons.json").read_text(encoding="utf-8"))
    assert info["features"] == q["metrics"]["antarctic_features"]
    assert "4326" in str(info["crs"])


@needs_run
def test_registry_does_not_overclaim():
    reg = json.loads(config.SOURCE_REGISTRY_JSON.read_text(encoding="utf-8"))["sources"]
    by = {s["dataset_id"]: s for s in reg}
    assert by["cmems_sea_ice_drift"]["download_status"] == "not_downloaded"
    assert by["cmems_sea_ice_drift"]["preprocessing_status"] != "processed"
    assert by["scar_amd"]["download_status"] == "not_downloaded"
    for api in ("era5_single_levels", "era5_pressure_levels"):
        if api in by and not by[api]["output_paths"]:
            assert by[api]["preprocessing_status"] == "not_available"


@needs_run
def test_word_report_opens():
    if not config.WORD_REPORT.exists():
        pytest.skip("report not yet generated")
    from docx import Document
    d = Document(config.WORD_REPORT)
    heads = [p.text for p in d.paragraphs if p.style.name.startswith("Heading")]
    assert any("Preprocessing of API-Generated Scientific Datasets" in h for h in heads)
    assert len(d.inline_shapes) >= 5
