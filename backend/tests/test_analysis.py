from datetime import time

import pandas as pd

from app import analysis as an
from app.config import TZ


def ts(s):
    return pd.Timestamp(s, tz="UTC")


def fc_frame():
    # target 2026-01-15 12:00 has three vintages; cutoff for D=15 Jan at 09:00 is 14 Jan 09:00
    return pd.DataFrame({
        "startTime":   [ts("2026-01-15 12:00")] * 3,
        "publishTime": [ts("2026-01-14 06:00"), ts("2026-01-14 09:00"), ts("2026-01-14 10:00")],
        "generation":  [100.0, 200.0, 999.0],
    })


def test_cutoff_is_d_minus_1_local():
    assert an.decision_cutoff(pd.Timestamp("2026-01-15").date(), time(9, 0), TZ) == ts("2026-01-14 09:00")


def test_picks_latest_at_or_before_cutoff_no_leakage():
    sel = an.select_decision_forecast(fc_frame(), time(9, 0), TZ)
    assert len(sel) == 1
    assert sel.iloc[0]["generation"] == 200.0          # 09:00 included, 10:00 excluded


def test_no_forecast_before_cutoff_gives_empty():
    sel = an.select_decision_forecast(fc_frame(), time(5, 0), TZ)
    assert sel.empty


def test_align_actuals_hourly_averages_two_halfhours_and_drops_incomplete():
    a = pd.DataFrame({"startTime": [ts("2026-01-15 12:00"), ts("2026-01-15 12:30"), ts("2026-01-15 13:00")],
                      "generation": [100.0, 200.0, 50.0]})
    out = an.align_actuals(a, hourly=True)
    assert out["actual"].tolist() == [150.0]


def test_metrics_and_sign_convention():
    df = pd.DataFrame({"forecast": [110.0, 90.0, 130.0], "actual": [100.0, 100.0, 100.0]})
    df["error"] = df["forecast"] - df["actual"]
    df["abs_error"] = df["error"].abs()
    m = an.compute_metrics(df)
    assert m["bias_mw"] == 10.0            # over-forecast on average
    assert m["mae_mw"] == 16.7
    assert m["share_overforecast_pct"] == 66.7
