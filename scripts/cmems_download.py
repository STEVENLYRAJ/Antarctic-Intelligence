"""Copernicus Marine (CMEMS) downloads C1-C7 for AETHENTRA (approved 2026-11-20).

Credentials: read by the copernicusmarine toolbox from the user's own credentials file
(%USERPROFILE%/.copernicusmarine). Nothing is hardcoded, printed or logged here.

Resumable: each chunk is written to <name>.part.nc, opened and checked, then renamed.
Existing finished files are skipped. Run again to resume.

Usage: python scripts/cmems_download.py [--only C1 C4 ...] [--workers 4]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "cmems"
LOG = ROOT / "experiments" / "logs" / "cmems_download.log"
ML03_DATES = ROOT / "configs" / "ml03" / "cmems_c4_test_dates.txt"

log = logging.getLogger("cmems")


def _years(a: int, b: int, step: int = 1):
    for y in range(a, b + 1, step):
        yield y, min(y + step - 1, b)


def jobs() -> list[dict]:
    J: list[dict] = []

    def add(code, ds, variables, lat, start, end, name, depth=None):
        J.append(dict(code=code, dataset_id=ds, variables=variables, lat=lat, start=start, end=end,
                      depth=depth, out=OUT / code / f"{name}.nc"))

    # C1 OSI-SAF SIC climate data record (OSI-450, 1978-10..2020) + ICDR (OSI-430, 2021..2025-09)
    v1 = ["ice_conc", "total_standard_uncertainty", "status_flag"]
    for a, _ in _years(1978, 2020):
        add("C1", "OSISAF-GLO-SEAICE_CONC_TIMESERIES-SH-LA-OBS", v1, (-90, -50),
            f"{a}-01-01", f"{a}-12-31T23:59:59", f"osisaf_sic_cdr_{a}")
    for a, _ in _years(2021, 2025):
        add("C1", "OSISAF-GLO-SEAICE_CONC_CONT_TIMESERIES-SH-LA-OBS", v1, (-90, -50),
            f"{a}-01-01", f"{a}-12-31T23:59:59", f"osisaf_sic_icdr_{a}")

    # C2 GLORYS12 monthly reanalysis: ice + surface ocean (top level only), 80-50S
    for a, b in _years(1993, 2026, 2):
        add("C2", "cmems_mod_glo_phy_my_0.083deg_P1M-m", ["siconc", "sithick", "thetao", "so", "mlotst"],
            (-80, -50), f"{a}-01-01", f"{b}-12-31T23:59:59", f"glorys12_monthly_{a}_{b}", depth=(0, 1))

    # C3 multi-reanalysis ensemble mean/std (structural uncertainty), surface
    v3 = [f"{v}_{s}" for v in ("siconc", "sithick", "thetao", "mlotst") for s in ("mean", "std")]
    for a, b in _years(1993, 2025, 11):
        add("C3", "cmems_mod_glo_phy-mnstd_my_0.25deg_P1M-m", v3, (-80, -50),
            f"{a}-01-01", f"{b}-12-31T23:59:59", f"glo_ens_mnstd_{a}_{b}", depth=(0, 1))

    # C4 DMI-ASIP 1 km SIC, ML-03 test-scene dates only (comparison, not independent truth)
    for d in ML03_DATES.read_text().split():
        iso = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        add("C4", "cmems_obs-si_ant_phy_nrt_l3-1km_P1D", ["ice_concentration", "confidence"], (-86, -50),
            iso, f"{iso}T23:59:59", f"dmi_asip_1km_{d}")

    # C5 IFREMER AMSR 3-day ice drift
    for a, _ in _years(2003, 2026):
        add("C5", "cmems_obs-si_ant_physic_my_drift-amsr_P3D", ["eastward_sea_ice_velocity", "northward_sea_ice_velocity"],
            (-90, -50), f"{a}-01-01", f"{a}-12-31T23:59:59", f"ifremer_drift_amsr_p3d_{a}")

    # C6 SMOS+CryoSat-2 observed ice thickness (short record)
    v6 = ["sea_ice_thickness", "sea_ice_thickness_uncertainty", "sea_ice_concentration", "quality_flag", "status_flag"]
    add("C6", "esa_obs-si_ant_phy-sit_nrt_l4-multi_P1D-m", v6, (-90, -50), "2025-01-01", "2025-12-31T23:59:59", "smos_cs2_sit_2025")
    add("C6", "esa_obs-si_ant_phy-sit_nrt_l4-multi_P1D-m", v6, (-90, -50), "2026-01-01", "2026-12-31T23:59:59", "smos_cs2_sit_2026")

    # C7 MULTIOBS observation-based T/S (surface) + MLD
    for a, b in _years(1993, 2025, 11):
        add("C7", "cmems_obs-mob_glo_phy_my_0.125deg_P1M-m", ["to", "so", "mlotst"], (-83, -50),
            f"{a}-01-01", f"{b}-12-31T23:59:59", f"multiobs_ts_{a}_{b}", depth=(0, 1))
    return J


def _check(path: Path) -> dict:
    import xarray as xr
    with xr.open_dataset(path) as ds:
        nt = int(ds.sizes.get("time", 1))
        if nt < 1:
            raise ValueError("empty time axis")
        return {"vars": sorted(ds.data_vars), "time": nt,
                "t0": str(ds["time"].values[0])[:10] if "time" in ds else None,
                "t1": str(ds["time"].values[-1])[:10] if "time" in ds else None}


def run_one(j: dict, retries: int = 4) -> tuple[str, str]:
    import copernicusmarine as cm
    out: Path = j["out"]
    if out.exists():
        return "skip", out.name
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_name(out.stem + ".part.nc")
    kw = dict(dataset_id=j["dataset_id"], variables=j["variables"],
              minimum_longitude=-180, maximum_longitude=180,
              minimum_latitude=j["lat"][0], maximum_latitude=j["lat"][1],
              start_datetime=j["start"], end_datetime=j["end"],
              output_directory=str(part.parent), output_filename=part.name,
              overwrite=True, disable_progress_bar=True, netcdf_compression_level=4)
    if j["depth"]:
        kw.update(minimum_depth=j["depth"][0], maximum_depth=j["depth"][1])
    err = ""
    for k in range(retries):
        try:
            t = time.time()
            cm.subset(**kw)
            info = _check(part)
            part.replace(out)
            mb = out.stat().st_size / 1e6
            log.info("DONE %s %s (%.0f MB, %d steps %s..%s, %.0f s)", j["code"], out.name, mb,
                     info["time"], info["t0"], info["t1"], time.time() - t)
            return "done", out.name
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {str(e)[:300]}"
            if "no data" in err.lower() or "out of" in err.lower() and "range" in err.lower():
                log.warning("NO DATA %s %s: %s", j["code"], out.name, err)
                return "nodata", out.name
            log.warning("retry %d %s %s: %s", k + 1, j["code"], out.name, err)
            part.unlink(missing_ok=True)
            time.sleep(30 * (k + 1))
    log.error("FAILED %s %s: %s", j["code"], out.name, err)
    return "failed", out.name


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s",
                        handlers=[logging.FileHandler(LOG), logging.StreamHandler(sys.stdout)])
    for noisy in ("copernicusmarine", "copernicusmarine_blank_logger", "urllib3", "botocore", "s3transfer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    J = [j for j in jobs() if not a.only or j["code"] in a.only]
    # small, high-value first: C4, C6, C3, C7, C2, C5, C1
    order = {c: i for i, c in enumerate(["C4", "C6", "C3", "C7", "C2", "C5", "C1"])}
    J.sort(key=lambda j: order[j["code"]])
    log.info("start: %d chunks (%s), %d workers", len(J), ",".join(sorted({j['code'] for j in J})), a.workers)
    res = {"done": 0, "skip": 0, "failed": 0, "nodata": 0}
    with ThreadPoolExecutor(a.workers) as ex:
        futs = [ex.submit(run_one, j) for j in J]
        for i, f in enumerate(as_completed(futs), 1):
            r, _ = f.result()
            res[r] += 1
            if i % 10 == 0 or i == len(J):
                log.info("progress %d/%d %s", i, len(J), json.dumps(res))
    log.info("finished CMEMS C1-C7: %s", json.dumps(res))
    return 1 if res["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
