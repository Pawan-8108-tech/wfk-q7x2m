"""Thin client for the Elexon Insights (BMRS) stream endpoints + CLI to snapshot data.

Run:  python -m app.elexon        (writes data/actuals.csv and data/forecasts.csv)
"""
from __future__ import annotations

import time as _time
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import requests

from .config import BASE_URL, DATA_DIR, DECISION_END, DECISION_START, MAX_HORIZON_H


def _get(path: str, params: dict, retries: int = 5) -> list[dict]:
    url = f"{BASE_URL}/{path}"
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=90)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"{r.status_code} from {r.url}")
            r.raise_for_status()
            js = r.json()
            return js["data"] if isinstance(js, dict) else js
        except (requests.RequestException, ValueError) as exc:
            last = exc
            _time.sleep(2 ** attempt)
    raise RuntimeError(f"Elexon request failed after {retries} tries: {last}")


def _chunks(start: datetime, end: datetime, step_days: int):
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=step_days), end)
        yield cur, nxt
        cur = nxt


def _iso(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_actuals(d_from: date, d_to: date, step_days: int = 7) -> pd.DataFrame:
    """FUELHH, WIND only. Half-hourly national outturn in MW."""
    rows: list[dict] = []
    for a, b in _chunks(datetime(d_from.year, d_from.month, d_from.day),
                        datetime(d_to.year, d_to.month, d_to.day) + timedelta(days=1), step_days):
        rows += _get("datasets/FUELHH/stream", {
            "settlementDateFrom": a.date().isoformat(),
            "settlementDateTo": (b - timedelta(days=1)).date().isoformat(),
            "fuelType": ["WIND"],
            "format": "json",
        })
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("FUELHH returned no rows - check parameters/date range")
    df = df[df["fuelType"] == "WIND"]
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df["generation"] = pd.to_numeric(df["generation"])
    cols = [c for c in ["startTime", "settlementDate", "settlementPeriod", "generation"] if c in df]
    return df[cols].drop_duplicates("startTime").sort_values("startTime").reset_index(drop=True)


def fetch_forecasts(t_from: datetime, t_to: datetime, step_days: int = 1) -> pd.DataFrame:
    """WINDFOR, every forecast vintage (publishTime) in the window."""
    rows: list[dict] = []
    for a, b in _chunks(t_from, t_to, step_days):
        rows += _get("datasets/WINDFOR/stream", {
            "publishDateTimeFrom": _iso(a),
            "publishDateTimeTo": _iso(b),
            "format": "json",
        })
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("WINDFOR returned no rows - check parameters/date range")
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)
    df["generation"] = pd.to_numeric(df["generation"])
    horizon = (df["startTime"] - df["publishTime"]).dt.total_seconds() / 3600
    df = df[(horizon >= 0) & (horizon <= MAX_HORIZON_H)]
    return (df[["startTime", "publishTime", "generation"]]
            .drop_duplicates(["startTime", "publishTime"])
            .sort_values(["startTime", "publishTime"]).reset_index(drop=True))


def snapshot() -> None:
    """Download the January-2026 study window and store it as CSV."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    first_delivery = DECISION_START + timedelta(days=1)
    last_delivery = DECISION_END + timedelta(days=1)
    print(f"Fetching actuals {first_delivery} .. {last_delivery}")
    fetch_actuals(first_delivery, last_delivery).to_csv(DATA_DIR / "actuals.csv", index=False)
    # forecasts published from 31 Dec (so 1 Jan decisions have history) to 1 Feb 00:00
    t0 = datetime(2025, 12, 31, tzinfo=timezone.utc).replace(tzinfo=None)
    t1 = datetime(2026, 2, 1)
    print(f"Fetching forecasts published {t0} .. {t1}")
    fetch_forecasts(t0, t1).to_csv(DATA_DIR / "forecasts.csv", index=False)
    print("Done ->", DATA_DIR)


if __name__ == "__main__":
    snapshot()
