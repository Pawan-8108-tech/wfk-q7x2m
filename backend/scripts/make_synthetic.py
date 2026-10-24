"""SYNTHETIC demo data (NOT real Elexon data) - lets you develop/test with no internet.

    python -m scripts.make_synthetic            # writes to ./data
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.config import DATA_DIR


def build(seed: int = 7):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01", "2026-02-02", freq="30min", tz="UTC", inclusive="left")
    t = np.arange(len(idx))
    base = 9000 + 4500 * np.sin(t / 130) + 2500 * np.sin(t / 37)
    actual = np.clip(base + rng.normal(0, 600, len(idx)), 300, 20000)
    act = pd.DataFrame({"startTime": idx, "generation": actual.round(0)})

    hours = pd.date_range("2025-12-31", "2026-02-01", freq="h", tz="UTC")
    truth = pd.Series(actual, idx)
    rows = []
    for p in hours:
        for h in range(1, 97):
            s = p + pd.Timedelta(hours=h)
            if s not in truth.index:
                continue
            t_h = truth[s] if s in truth.index else np.nan
            rows.append((s, p, max(t_h + rng.normal(0, 250 + 35 * h), 0)))
    fc = pd.DataFrame(rows, columns=["startTime", "publishTime", "generation"])
    fc["generation"] = fc["generation"].round(0)
    return act, fc


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    a, f = build()
    a.to_csv(DATA_DIR / "actuals.csv", index=False)
    f.to_csv(DATA_DIR / "forecasts.csv", index=False)
    print("Wrote SYNTHETIC data to", DATA_DIR)
