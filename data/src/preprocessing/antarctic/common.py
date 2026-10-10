"""Shared helpers: hashing, JSON I/O, logging, quality-record bookkeeping."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import math
import platform
import sys
from pathlib import Path

import numpy as np

from .config import HASH_CACHE_JSON, LOGS_DIR, QUALITY_DIR, ROOT

LOG = logging.getLogger("antarctic")


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def rel(path) -> str:
    """Repository-relative POSIX path (falls back to the absolute path)."""
    p = Path(path).resolve()
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def setup_logging(run_id: str) -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"pipeline_{run_id}.log"
    LOG.setLevel(logging.INFO)
    LOG.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for h in (logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler(sys.stdout)):
        h.setFormatter(fmt)
        LOG.addHandler(h)
    return log_path


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (dt.datetime, dt.date)):
        return o.isoformat()
    if isinstance(o, Path):
        return rel(o)
    return str(o)


def _clean(o):
    """Replace NaN/inf floats with None so JSON output is strictly valid."""
    if isinstance(o, float) and not math.isfinite(o):
        return None
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def write_json(obj, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(_clean(json.loads(json.dumps(obj, default=_json_default))), indent=2, ensure_ascii=False)
    path.write_text(text, encoding="utf-8")
    return path


def read_json(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def sha256_file(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def cached_sha256(path: Path, cache: dict, force: bool = False) -> str:
    """SHA-256 with a (size, mtime) keyed cache so reruns do not rehash 9 GB of GLIMS data."""
    st = path.stat()
    key = rel(path)
    entry = cache.get(key)
    if not force and entry and entry["size"] == st.st_size and entry["mtime_ns"] == st.st_mtime_ns:
        return entry["sha256"]
    digest = sha256_file(path)
    cache[key] = {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "sha256": digest}
    return digest


def load_hash_cache() -> dict:
    return read_json(HASH_CACHE_JSON, {}) or {}


def save_hash_cache(cache: dict) -> None:
    write_json(cache, HASH_CACHE_JSON)


def software_versions() -> dict:
    mods = ["numpy", "pandas", "xarray", "netCDF4", "pyogrio", "geopandas", "shapely", "pyproj",
            "rasterio", "matplotlib", "docx", "pyarrow", "requests"]
    out = {"python": sys.version.split()[0], "platform": platform.platform()}
    for m in mods:
        try:
            mod = __import__(m)
            out[m] = getattr(mod, "__version__", "installed")
        except Exception as e:  # pragma: no cover - depends on environment
            out[m] = f"unavailable ({type(e).__name__})"
    try:
        import pyogrio
        out["gdal"] = pyogrio.__gdal_version_string__
    except Exception:
        pass
    return out


def new_record(dataset_id: str, dataset_name: str, files, category: str, provider: str = "") -> dict:
    """Machine-readable quality record shared by every handler."""
    return {
        "dataset_id": dataset_id,
        "dataset_name": dataset_name,
        "category": category,
        "provider": provider,
        "source_files": [rel(f) for f in files],
        "status": "discovered",
        "domain_relevance": "antarctic",
        "started_utc": utcnow(),
        "finished_utc": None,
        "steps": [],
        "metrics": {},
        "issues": [],
        "outputs": [],
        "validation": {},
        "errors": [],
        "notes": [],
    }


def step(rec: dict, msg: str) -> None:
    rec["steps"].append(msg)
    LOG.info("[%s] %s", rec["dataset_id"], msg)


def issue(rec: dict, severity: str, kind: str, detail: str, count=None) -> None:
    rec["issues"].append({"severity": severity, "type": kind, "detail": detail, "count": count})


def add_output(rec: dict, path: Path, kind: str, description: str) -> None:
    p = Path(path)
    rec["outputs"].append({
        "path": rel(p), "kind": kind, "description": description,
        "size_bytes": p.stat().st_size if p.exists() else None,
    })


def finish(rec: dict, status: str) -> dict:
    rec["status"] = status
    rec["finished_utc"] = utcnow()
    write_json(rec, QUALITY_DIR / f"{rec['dataset_id']}.json")
    return rec


def num_summary(a) -> dict:
    """min/max/mean/std/percentiles of a numeric array ignoring NaN."""
    a = np.asarray(a, dtype="float64")
    a = a[np.isfinite(a)]
    if a.size == 0:
        return {"count": 0}
    q = np.percentile(a, [1, 25, 50, 75, 99])
    return {"count": int(a.size), "min": float(a.min()), "p01": float(q[0]), "p25": float(q[1]),
            "median": float(q[2]), "p75": float(q[3]), "p99": float(q[4]), "max": float(a.max()),
            "mean": float(a.mean()), "std": float(a.std())}
