"""Per-cell daily climatology (day-of-year mean, circularly smoothed) fitted on a fixed reference period."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from ..paths import load

LOG = logging.getLogger("aethentra.ml02.climatology")


def doy_index(dates) -> np.ndarray:
    """0..364; 29 Feb shares the slot of 28 Feb so every year maps onto 365 slots."""
    d = pd.DatetimeIndex(dates)
    doy = d.dayofyear.to_numpy() - 1
    leap = d.is_leap_year
    after = leap & ((d.month > 2) | ((d.month == 2) & (d.day == 29)))   # 29 Feb -> 28 Feb slot; later days shift by one
    return np.where(after, doy - 1, doy).astype(np.int16)


def smooth_circular(a: np.ndarray, half: int) -> np.ndarray:
    """Moving average over axis 0 (365 slots) with wrap-around (31 Dec is adjacent to 1 Jan)."""
    if half <= 0:
        return a
    k = 2 * half + 1
    pad = np.concatenate([a[-half:], a, a[:half]], axis=0)
    c = np.cumsum(np.concatenate([np.zeros((1,) + a.shape[1:]), pad], axis=0), axis=0)
    return (c[k:] - c[:-k]) / k


class Climatology:
    """``mean[var]`` is (365, N) float32 in physical units."""

    def __init__(self, mean: dict, period: tuple[int, int], half: int):
        self.mean, self.period, self.half = mean, tuple(period), half

    @classmethod
    def fit(cls, cube, variables=None, period=None, half=None) -> "Climatology":
        cfg = load("climatology")
        period = tuple(period or cfg["reference_period"])
        half = cfg["smoothing_half_width_days"] if half is None else half
        variables = [v for v in (variables or cfg["variables"]) if v in cube.variables]
        sel = (cube.dates.year >= period[0]) & (cube.dates.year <= period[1])
        if not sel.any():
            raise ValueError(f"cube has no days in the reference period {period}")
        idx = np.flatnonzero(sel)
        doy = cube.doy[idx]
        mean = {}
        for v in variables:
            s = np.zeros((365, cube.n)); n = np.zeros((365, cube.n))
            for c0 in range(0, idx.size, 366):
                block = cube.window(v, cube.dates[idx[min(c0 + 365, idx.size - 1)]], min(366, idx.size - c0))
                d = doy[c0:c0 + block.shape[0]]
                ok = np.isfinite(block)
                np.add.at(s, d, np.where(ok, block, 0.0))
                np.add.at(n, d, ok)
            with np.errstate(invalid="ignore", divide="ignore"):
                m = s / n
            # smooth only where every slot is defined (reanalysis: always); otherwise keep NaN
            mean[v] = smooth_circular(m, half).astype(np.float32)
            LOG.info("climatology %s: %d days, min count per slot %d", v, idx.size, int(n.min()))
        return cls(mean, period, half)

    def daily(self, var: str, dates) -> np.ndarray:
        return self.mean[var][doy_index(dates)]

    def window_mean(self, var: str, start, n: int) -> np.ndarray:
        """Mean climatology over n consecutive days starting at ``start`` -> (N,)."""
        return self.daily(var, pd.date_range(start, periods=n, freq="D")).mean(axis=0)

    def save(self, path: Path):
        np.savez_compressed(path, period=np.array(self.period), half=np.array(self.half), **{f"mean_{k}": v for k, v in self.mean.items()})
        path.with_suffix(".json").write_text(json.dumps({"period": list(self.period), "smoothing_half_width_days": self.half,
                                                          "variables": list(self.mean)}, indent=1))

    @classmethod
    def load(cls, path: Path) -> "Climatology":
        z = np.load(path)
        return cls({k[5:]: z[k] for k in z.files if k.startswith("mean_")}, tuple(z["period"]), int(z["half"]))
