from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, time, timedelta
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import analysis as an
from .config import DECISION_END, DECISION_START, DEFAULT_DECISION_TIME, TZ
from .store import DataStore

store = DataStore()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        store.load()
    except FileNotFoundError as exc:
        print("WARNING:", exc)
    yield


app = FastAPI(title="Wind Forecast Decision Portal API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


def _ready() -> None:
    if not store.ready:
        raise HTTPException(503, "Data snapshot not loaded. See README: run `python -m app.elexon`.")


def _parse_time(s: str | None) -> time:
    if not s:
        return DEFAULT_DECISION_TIME
    try:
        return time.fromisoformat(s)
    except ValueError:
        raise HTTPException(422, "decision_time must be HH:MM (UK local time)")


def _iso(ts) -> str | None:
    return None if pd.isna(ts) else ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean(v):
    return None if (isinstance(v, float) and pd.isna(v)) else v


def _delivery_days() -> list[date]:
    first, last = DECISION_START + timedelta(days=1), DECISION_END + timedelta(days=1)
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def _prepared(decision_time: time, start: date | None, end: date | None):
    """Decision-time forecasts joined with actuals, optionally limited to a delivery-date range."""
    fc = an.select_decision_forecast(store.forecasts, decision_time, TZ)
    hourly = an.is_hourly(store.forecasts)
    df = an.join(fc, an.align_actuals(store.actuals, hourly))
    df["delivery_date"] = pd.to_datetime(df["delivery_date"]).dt.date
    if start:
        df = df[df["delivery_date"] >= start]
    if end:
        df = df[df["delivery_date"] <= end]
    return df, hourly


@app.get("/api/health")
def health():
    return {"status": "ok", "data_loaded": store.ready}


@app.get("/api/config")
def config():
    _ready()
    days = _delivery_days()
    return {
        "decision_time_default": DEFAULT_DECISION_TIME.strftime("%H:%M"),
        "timezone": "Europe/London",
        "decision_dates": [str(DECISION_START), str(DECISION_END)],
        "delivery_dates": [str(days[0]), str(days[-1])],
        "forecast_resolution_min": 60 if an.is_hourly(store.forecasts) else 30,
        "forecast_rows": int(len(store.forecasts)),
        "actual_rows": int(len(store.actuals)),
        "sign_convention": "error = forecast - actual (positive = over-forecast)",
    }


@app.get("/api/decision")
def decision(delivery_date: date, decision_time: str | None = None):
    """What did the trader know when deciding on D-1, and how did it turn out?"""
    _ready()
    dt = _parse_time(decision_time)
    df, hourly = _prepared(dt, delivery_date, delivery_date)
    if df.empty:
        raise HTTPException(404, f"No forecast available before the decision time for {delivery_date}")
    cutoff = an.decision_cutoff(delivery_date, dt, TZ)
    rows = [{
        "startTime": _iso(r.startTime), "forecast_mw": _clean(r.forecast), "actual_mw": _clean(r.actual),
        "error_mw": _clean(r.error), "publishTime": _iso(r.publishTime),
    } for r in df.sort_values("startTime").itertuples()]
    return {
        "delivery_date": str(delivery_date),
        "decision_cutoff_utc": _iso(cutoff),
        "decision_cutoff_local": cutoff.tz_convert(TZ).strftime("%Y-%m-%d %H:%M %Z"),
        "forecast_published_min": _iso(df["publishTime"].min()),
        "forecast_published_max": _iso(df["publishTime"].max()),
        "resolution_min": 60 if hourly else 30,
        "metrics": an.compute_metrics(df),
        "series": rows,
    }


@app.get("/api/metrics")
def metrics(start: date | None = None, end: date | None = None, decision_time: str | None = None):
    """Accuracy of the decision-time forecast over a range of delivery days."""
    _ready()
    dt = _parse_time(decision_time)
    df, _ = _prepared(dt, start, end)
    if df.empty:
        raise HTTPException(404, "No data in the requested range")
    local_hour = df["startTime"].dt.tz_convert(TZ).dt.hour
    return {
        "decision_time": dt.strftime("%H:%M"),
        "overall": an.compute_metrics(df),
        "by_day": an.metrics_by(df, df["delivery_date"], "delivery_date"),
        "by_hour": an.metrics_by(df, local_hour, "hour"),
    }


@app.get("/api/horizon")
def horizon(start: date | None = None, end: date | None = None):
    """Error vs how far ahead the forecast was made (uses ALL published vintages)."""
    _ready()
    fc = store.forecasts.copy()
    day = fc["startTime"].dt.tz_convert(TZ).dt.date
    if start:
        fc = fc[day >= start]
        day = day[fc.index]
    if end:
        fc = fc[day <= end]
    j = an.join(fc, an.align_actuals(store.actuals, an.is_hourly(store.forecasts)))
    return {"by_horizon": an.horizon_metrics(j)}


# ---- optional: serve the built React app from the same container -------------
_static = Path(__file__).resolve().parent.parent / "static"
if _static.exists():
    app.mount("/assets", StaticFiles(directory=_static / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = _static / path
        return FileResponse(f if f.is_file() else _static / "index.html")
