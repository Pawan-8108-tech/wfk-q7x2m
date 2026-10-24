"""Loads the CSV snapshot once and serves it from memory."""
from __future__ import annotations

import pandas as pd

from .config import DATA_DIR


class DataStore:
    def __init__(self) -> None:
        self.actuals: pd.DataFrame | None = None
        self.forecasts: pd.DataFrame | None = None

    def load(self) -> None:
        a, f = DATA_DIR / "actuals.csv", DATA_DIR / "forecasts.csv"
        if not (a.exists() and f.exists()):
            raise FileNotFoundError(
                f"Missing {a.name}/{f.name} in {DATA_DIR}. Run `python -m app.elexon` "
                "(real data) or `python -m scripts.make_synthetic` (demo data).")
        self.actuals = pd.read_csv(a, parse_dates=["startTime"])
        self.forecasts = pd.read_csv(f, parse_dates=["startTime", "publishTime"])
        for df, cols in ((self.actuals, ["startTime"]), (self.forecasts, ["startTime", "publishTime"])):
            for c in cols:
                df[c] = pd.to_datetime(df[c], utc=True)

    @property
    def ready(self) -> bool:
        return self.actuals is not None and self.forecasts is not None
