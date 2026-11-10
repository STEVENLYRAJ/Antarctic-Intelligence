"""Day-of-year SIC climatology fitted on a given (training) period only."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..preprocessing.cube import Cube


def doy_index(dates) -> np.ndarray:
    """0-based day-of-year with 29 Feb folded onto 28 Feb, so every year has 365 slots."""
    d = pd.DatetimeIndex(dates)
    doy = d.dayofyear.values - 1
    leap_after_feb = d.is_leap_year & (d.month > 2)
    doy = doy - leap_after_feb.astype(int)
    feb29 = (d.month == 2) & (d.day == 29)
    doy[feb29] = 58
    return doy


class Climatology:
    def __init__(self, mean: np.ndarray, std: np.ndarray, period: tuple[str, str], half_width: int):
        self.mean, self.std, self.period, self.half_width = mean, std, period, half_width

    @classmethod
    def fit(cls, cube: Cube, start: str, end: str, half_width: int = 7) -> "Climatology":
        dates = pd.date_range(start, end, freq="D")
        dates = dates[(dates >= cube.dates[0]) & (dates <= cube.dates[-1])]
        ny, nx = cube.ocean.shape
        s = np.zeros((365, ny, nx), np.float64)
        ss = np.zeros((365, ny, nx), np.float64)
        n = np.zeros((365, ny, nx), np.int32)
        doys = doy_index(dates)
        for d, k in zip(dates, doys):
            a = cube.day(d)
            v = np.isfinite(a)
            s[k][v] += a[v]
            ss[k][v] += a[v] ** 2
            n[k] += v
        # circular +-half_width smoothing along day-of-year
        def smooth(x):
            ext = np.concatenate([x[-half_width:], x, x[:half_width]], axis=0)
            c = np.cumsum(ext, axis=0, dtype=np.float64)
            c = np.concatenate([np.zeros((1, ny, nx)), c], axis=0)
            w = 2 * half_width + 1
            return c[w:] - c[:-w]
        S, SS, N = smooth(s), smooth(ss), smooth(n.astype(np.float64))
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = (S / N).astype(np.float32)
            std = np.sqrt(np.maximum(SS / N - (S / N) ** 2, 0)).astype(np.float32)
        mean[:, ~cube.ocean] = np.nan
        std[:, ~cube.ocean] = np.nan
        return cls(mean, std, (start, end), half_width)

    def window_mean(self, first_date, n_days: int) -> tuple[np.ndarray, np.ndarray]:
        k = doy_index(pd.date_range(first_date, periods=n_days, freq="D"))
        return self.mean[k].mean(axis=0), self.std[k].mean(axis=0)

    def seasonal_ice_zone(self, threshold: float = 15.0) -> np.ndarray:
        return np.nanmax(self.mean, axis=0) >= threshold

    def save(self, path):
        np.savez_compressed(path, mean=self.mean.astype(np.float16), std=self.std.astype(np.float16),
                            period=np.array(self.period), half_width=self.half_width)

    @classmethod
    def load(cls, path) -> "Climatology":
        z = np.load(path)
        return cls(z["mean"].astype(np.float32), z["std"].astype(np.float32), tuple(z["period"]), int(z["half_width"]))
