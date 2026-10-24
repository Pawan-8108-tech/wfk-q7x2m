"""Pure functions (no I/O) for forecast selection and error metrics.

Sign convention: error = forecast - actual.
  error > 0  -> wind was OVER-forecast  -> trader bought too little thermal (shortfall risk)
  error < 0  -> wind was UNDER-forecast -> trader bought too much (surplus / sell back)
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HORIZON_BINS = [0, 6, 12, 24, 36, 48, 72, 96.0001]
HORIZON_LABELS = ["0-6h", "6-12h", "12-24h", "24-36h", "36-48h", "48-72h", "72-96h"]


def decision_cutoff(delivery_date: date, decision_time: time, tz: ZoneInfo) -> pd.Timestamp:
    """UTC instant at which the day-ahead decision for `delivery_date` is taken (D-1, local time)."""
    local = datetime.combine(delivery_date - timedelta(days=1), decision_time, tzinfo=tz)
    return pd.Timestamp(local).tz_convert("UTC")


def add_cutoff(fc: pd.DataFrame, decision_time: time, tz: ZoneInfo) -> pd.DataFrame:
    out = fc.copy()
    out["delivery_date"] = out["startTime"].dt.tz_convert(tz).dt.date
    cutoffs = {d: decision_cutoff(d, decision_time, tz) for d in out["delivery_date"].unique()}
    out["cutoff"] = pd.to_datetime(out["delivery_date"].map(cutoffs), utc=True)
    return out


def select_decision_forecast(fc: pd.DataFrame, decision_time: time, tz: ZoneInfo) -> pd.DataFrame:
    """For every target half-hour/hour keep the latest forecast published AT OR BEFORE the cutoff.

    Forecasts published after the cutoff are never used (that would be look-ahead leakage).
    """
    d = add_cutoff(fc, decision_time, tz)
    d = d[d["publishTime"] <= d["cutoff"]]
    d = d.sort_values(["startTime", "publishTime"]).drop_duplicates("startTime", keep="last")
    return d.reset_index(drop=True)


def is_hourly(fc: pd.DataFrame) -> bool:
    return not (fc["startTime"].dt.minute != 0).any()


def align_actuals(actual: pd.DataFrame, hourly: bool) -> pd.DataFrame:
    """Actuals are half-hourly. If forecasts are hourly, average the two half-hours of each hour."""
    a = actual[["startTime", "generation"]].rename(columns={"generation": "actual"})
    if not hourly:
        return a
    s = a.set_index("startTime")["actual"].resample("60min")
    out = pd.DataFrame({"actual": s.mean(), "n": s.count()})
    out = out[out["n"] == 2].drop(columns="n").reset_index()   # only complete hours
    return out


def join(fc: pd.DataFrame, actual_aligned: pd.DataFrame) -> pd.DataFrame:
    df = fc.rename(columns={"generation": "forecast"}).merge(actual_aligned, on="startTime", how="left")
    df["error"] = df["forecast"] - df["actual"]
    df["abs_error"] = df["error"].abs()
    df["horizon_h"] = (df["startTime"] - df["publishTime"]).dt.total_seconds() / 3600
    return df


def compute_metrics(df: pd.DataFrame, mape_min_mw: float = 100.0) -> dict:
    d = df.dropna(subset=["forecast", "actual"])
    if d.empty:
        return {"n": 0}
    e, ae = d["error"], d["abs_error"]
    big = d[d["actual"] >= mape_min_mw]
    r = lambda x, k=1: None if pd.isna(x) else round(float(x), k)  # noqa: E731
    return {
        "n": int(len(d)),
        "mae_mw": r(ae.mean()),
        "rmse_mw": r(np.sqrt((e ** 2).mean())),
        "bias_mw": r(e.mean()),                       # + = over-forecast on average
        "wmape_pct": r(100 * ae.sum() / d["actual"].sum(), 2),
        "mape_pct": r(100 * (big["abs_error"] / big["actual"]).mean(), 2) if len(big) else None,
        "median_abs_error_mw": r(ae.median()),
        "p90_abs_error_mw": r(ae.quantile(0.90)),
        "p95_abs_error_mw": r(ae.quantile(0.95)),
        # Planning buffers: how bad can it get in 9 of 10 hours?
        "overforecast_p90_mw": r(max(e.quantile(0.90), 0)),    # shortfall risk -> buy extra
        "underforecast_p90_mw": r(max((-e).quantile(0.90), 0)),  # surplus risk
        "share_overforecast_pct": r(100 * (e > 0).mean(), 1),
        "avg_actual_mw": r(d["actual"].mean()),
        "avg_forecast_mw": r(d["forecast"].mean()),
    }


def metrics_by(df: pd.DataFrame, key: pd.Series, name: str) -> list[dict]:
    out = []
    for k, g in df.groupby(key, observed=True):
        m = compute_metrics(g)
        if m["n"]:
            out.append({name: str(k) if not isinstance(k, (int, np.integer)) else int(k), **m})
    return out


def horizon_metrics(all_vintages_joined: pd.DataFrame) -> list[dict]:
    d = all_vintages_joined.copy()
    d["bucket"] = pd.cut(d["horizon_h"], HORIZON_BINS, labels=HORIZON_LABELS, right=False)
    return metrics_by(d, d["bucket"], "horizon")
