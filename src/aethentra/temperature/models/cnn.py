"""ML-02 spatial deep-learning candidate: U-Net on gridded predictor stacks (addendum experiment).

The per-cell features of ``FeatureContext.features(t)`` are scattered onto the 25 km polar-stereographic grid (cropped to
the ≤60°S bounding box) so the CNN sees exactly the same leakage-safe inputs as the tree models; it adds spatial context
through convolutions. Static fields use fixed physical scalings; dynamic channels use mean/std from the TRAINING split.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ..features.build import STATIC_FEATURES

STATIC_SCALE = {"lat": (-75.0, 10.0), "lon_sin": (0.0, 1.0), "lon_cos": (0.0, 1.0), "elevation_m": (0.0, 1000.0),
                "dist_coast_km": (0.0, 500.0), "land": (0.0, 1.0), "coastal": (0.0, 1.0)}
EXCLUDE = set(STATIC_FEATURES) | {"month"}          # month/region are categorical; doy_sin/doy_cos carry the season


def dynamic_channels(names: list[str]) -> list[str]:
    return [n for n in names if n not in EXCLUDE]


class GridMap:
    """Cell vector <-> cropped 2-D grid."""

    def __init__(self, grid: dict):
        r, c = grid["rows"], grid["cols"]
        self.r0, self.c0 = int(r.min()), int(c.min())
        self.shape = (int(r.max()) - self.r0 + 1, int(c.max()) - self.c0 + 1)
        self.rr, self.cc = r - self.r0, c - self.c0

    def to_grid(self, v: np.ndarray, fill=np.nan, dtype=np.float32) -> np.ndarray:
        g = np.full(self.shape, fill, dtype)
        g[self.rr, self.cc] = v
        return g

    def to_cells(self, g: np.ndarray) -> np.ndarray:
        return g[self.rr, self.cc]


def static_stack(ctx, gm: GridMap) -> np.ndarray:
    return np.stack([gm.to_grid((ctx.static[k] - a) / s, fill=0.0) for k, (a, s) in STATIC_SCALE.items()]).astype(np.float32)


def dynamic_stack(F: dict, channels: list[str], gm: GridMap) -> np.ndarray:
    return np.stack([gm.to_grid(F[k]) for k in channels])


class CNNModel:
    """Checkpointed U-Net with the evaluation interface of ``AnomalyModel`` (``predict_cells``)."""

    def __init__(self, net, meta: dict, static: np.ndarray, gm: GridMap):
        self.net, self.meta, self.static, self.gm = net, meta, static, gm
        self.channels = meta["dynamic_channels"]
        self.mean = np.asarray(meta["norm_mean"], np.float32)[:, None, None]
        self.std = np.asarray(meta["norm_std"], np.float32)[:, None, None]
        self.vc = self.channels.index("anom_w1")
        self.name = meta["name"]

    @property
    def features(self) -> list[str]:
        return self.channels

    @classmethod
    def load(cls, directory: Path, name: str, ctx) -> "CNNModel":
        import torch

        from ...models.unet import UNet
        meta = json.loads((Path(directory) / f"{name}.meta.json").read_text())
        net = UNet(meta["in_channels"], **meta["architecture"])
        net.load_state_dict(torch.load(Path(directory) / f"{name}.pt", map_location="cpu", weights_only=True))
        net.to("cuda" if torch.cuda.is_available() else "cpu")
        gm = GridMap(ctx.cube.grid)
        return cls(net, meta, static_stack(ctx, gm), gm)

    def input_from_stack(self, x: np.ndarray) -> np.ndarray:
        x = x.astype(np.float32)
        valid = np.isfinite(x[self.vc])
        x = np.nan_to_num((x - self.mean) / self.std)
        return np.concatenate([x, self.static, valid[None].astype(np.float32)], 0)

    def predict_cells(self, F: dict) -> np.ndarray:
        from ...models.unet import predict
        x = dynamic_stack(F, self.channels, self.gm)
        p = self.gm.to_cells(predict(self.net, self.input_from_stack(x)))
        return np.where(np.isfinite(F["anom_w1"]), p, np.nan).astype(np.float32)
