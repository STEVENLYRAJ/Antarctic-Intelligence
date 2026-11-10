"""Shared spatial deep-learning candidate (ML-01 and ML-02): a compact U-Net trained on gridded predictor stacks.

Inputs are (C, H, W) float tensors already normalised with training-split statistics (NaN -> 0 plus a validity channel);
targets are (H, W) with NaN where undefined. The loss is an area-weighted masked MSE or L1, so cells outside the domain never
contribute. Early stopping uses a separate validation stack only - test data are never seen during training.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as Fn

LOG = logging.getLogger("aethentra.unet")


class _Block(nn.Module):
    def __init__(self, cin, cout, dropout=0.0):
        super().__init__()
        self.net = nn.Sequential(nn.Conv2d(cin, cout, 3, padding=1, bias=False), nn.GroupNorm(8, cout), nn.GELU(),
                                 nn.Dropout2d(dropout) if dropout else nn.Identity(),
                                 nn.Conv2d(cout, cout, 3, padding=1, bias=False), nn.GroupNorm(8, cout), nn.GELU())

    def forward(self, x):
        return self.net(x)


class UNet(nn.Module):
    def __init__(self, cin: int, base: int = 32, depth: int = 4, dropout: float = 0.1, cout: int = 1):
        super().__init__()
        ch = [base * 2 ** i for i in range(depth + 1)]
        self.mult = 2 ** depth
        self.down = nn.ModuleList([_Block(cin, ch[0])] + [_Block(ch[i], ch[i + 1], dropout if i >= depth - 2 else 0) for i in range(depth)])
        self.up = nn.ModuleList([nn.ConvTranspose2d(ch[i + 1], ch[i], 2, stride=2) for i in reversed(range(depth))])
        self.dec = nn.ModuleList([_Block(2 * ch[i], ch[i]) for i in reversed(range(depth))])
        self.head = nn.Conv2d(ch[0], cout, 1)

    def forward(self, x):
        h, w = x.shape[-2:]
        ph, pw = (-h) % self.mult, (-w) % self.mult
        x = Fn.pad(x, (0, pw, 0, ph))
        skips = []
        for i, blk in enumerate(self.down):
            x = blk(x if i == 0 else Fn.max_pool2d(x, 2))
            skips.append(x)
        skips.pop()
        for up, dec in zip(self.up, self.dec):
            x = dec(torch.cat([up(x), skips.pop()], 1))
        return self.head(x)[..., :h, :w]


def masked_loss(pred, y, w, kind: str = "mse"):
    """pred/y (B,1,H,W) or (B,H,W); w = area weight (0 where undefined); kind = mse | l1."""
    e = pred.reshape(y.shape) - torch.nan_to_num(y)
    return ((e ** 2 if kind == "mse" else e.abs()) * w).sum() / w.sum().clamp_min(1e-6)


class StackDataset(torch.utils.data.Dataset):
    """Memory-mapped (n, C, H, W) predictors + (n, H, W) targets; static channels appended per sample."""

    def __init__(self, X, Y, static, mean, std, area, valid_channel: int):
        self.X, self.Y, self.static = X, Y, static
        self.mean, self.std = mean[:, None, None], std[:, None, None]
        self.area, self.vc = area, valid_channel

    def __len__(self):
        return len(self.X)

    def __getitem__(self, i):
        x = np.asarray(self.X[i], np.float32)
        valid = np.isfinite(x[self.vc])
        x = np.nan_to_num((x - self.mean) / self.std)
        x = np.concatenate([x, self.static, valid[None].astype(np.float32)], 0)
        y = np.asarray(self.Y[i], np.float32)
        w = np.where(np.isfinite(y) & valid, self.area, 0.0).astype(np.float32)
        return torch.from_numpy(x), torch.from_numpy(y), torch.from_numpy(w)


def _loader(ds, bs, shuffle, seed):
    g = torch.Generator().manual_seed(seed)
    return torch.utils.data.DataLoader(ds, batch_size=bs, shuffle=shuffle, generator=g, num_workers=0, pin_memory=True)


def evaluate(model, loader, device, loss: str = "mse") -> float:
    """Area-weighted RMSE (loss=mse) or MAE (loss=l1) over all defined cells of the split."""
    model.eval()
    se = ws = 0.0
    with torch.no_grad(), torch.autocast(device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
        for x, y, w in loader:
            x, y, w = x.to(device), y.to(device), w.to(device)
            p = model(x).float().reshape(y.shape)
            se += float(masked_loss(p, y, w, loss) * w.sum()); ws += float(w.sum())
    m = se / max(ws, 1e-9)
    return float(np.sqrt(m) if loss == "mse" else m)


def fit(model, train_ds, val_ds=None, epochs=40, lr=1e-3, weight_decay=1e-4, batch_size=8, patience=8, seed=42,
        fixed_epochs: int | None = None, log_path: Path | None = None, loss: str = "mse") -> dict:
    """Train with AdamW + one-cycle schedule. With val_ds: early stopping on validation RMSE (mse) / MAE (l1), best weights restored.
    With fixed_epochs: train exactly that many epochs (final refit, no validation data)."""
    torch.manual_seed(seed); np.random.seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    n_ep = fixed_epochs or epochs
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=n_ep * int(np.ceil(len(train_ds) / batch_size)), pct_start=0.1)
    tl = _loader(train_ds, batch_size, True, seed)
    vl = _loader(val_ds, batch_size, False, seed) if val_ds is not None else None
    hist, best, best_state, best_ep, bad, t0 = [], np.inf, None, 0, 0, time.time()
    for ep in range(1, n_ep + 1):
        model.train()
        tot = ws = 0.0
        for x, y, w in tl:
            x, y, w = x.to(device, non_blocking=True), y.to(device, non_blocking=True), w.to(device, non_blocking=True)
            with torch.autocast(device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
                p = model(x)
            lv = masked_loss(p.float(), y, w, loss)
            opt.zero_grad(set_to_none=True)
            lv.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step()
            tot += float(lv) * float(w.sum()); ws += float(w.sum())
        tm = tot / ws
        rec = {"epoch": ep, f"train_{'rmse' if loss == 'mse' else 'mae'}": float(np.sqrt(tm) if loss == "mse" else tm), "seconds": round(time.time() - t0, 1)}
        if vl is not None:
            rec["val_metric"] = evaluate(model, vl, device, loss)
            if rec["val_metric"] < best - 1e-4:
                best, best_ep, bad = rec["val_metric"], ep, 0
                best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            else:
                bad += 1
        hist.append(rec)
        LOG.info("epoch %s", rec)
        if log_path:
            log_path.write_text(json.dumps(hist, indent=1))
        if vl is not None and bad >= patience:
            break
    if best_state is not None:
        model.load_state_dict(best_state)
    return {"history": hist, "best_epoch": best_ep or n_ep, "loss": loss,
            "best_val_metric": None if vl is None else best, "val_metric": None if vl is None else ("rmse" if loss == "mse" else "mae"),
            "epochs_run": len(hist), "seconds": round(time.time() - t0, 1), "device": str(device),
            "n_parameters": int(sum(p.numel() for p in model.parameters()))}


def predict(model, x: np.ndarray) -> np.ndarray:
    """x: (C, H, W) already normalised -> (H, W) float32."""
    device = next(model.parameters()).device
    model.eval()
    with torch.no_grad(), torch.autocast(device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
        return model(torch.from_numpy(x[None]).to(device)).float().cpu().numpy()[0, 0]
