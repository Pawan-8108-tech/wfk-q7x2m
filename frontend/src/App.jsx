import { useEffect, useState } from "react";
import {
  ResponsiveContainer, ComposedChart, Line, Area, BarChart, Bar, LineChart, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine,
} from "recharts";

const C = { actual: "var(--actual)", forecast: "var(--forecast)", over: "var(--over)", under: "var(--under)" };
const mw = (v) => (v == null ? "-" : Math.round(v).toLocaleString("en-GB") + " MW");
const gw = (v) => (v == null ? "-" : (v / 1000).toFixed(1) + " GW");
const axisGW = (v) => (v / 1000).toFixed(0);
const dayLabel = (d) => new Date(d + "T12:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", weekday: "short" });
const tick = { fontSize: 12, fill: "var(--muted)" };
const get = (url) => fetch(url).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${url} -> ${r.status}`))));

function Grid() {
  return <CartesianGrid stroke="var(--line)" strokeDasharray="3 3" vertical={false} />;
}

export default function App() {
  const [cfg, setCfg] = useState(null);
  const [month, setMonth] = useState(null);
  const [horizon, setHorizon] = useState(null);
  const [date, setDate] = useState(null);
  const [day, setDay] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([get("/api/config"), get("/api/metrics"), get("/api/horizon")])
      .then(([c, m, h]) => { setCfg(c); setMonth(m); setHorizon(h.by_horizon); setDate(c.delivery_dates[0] <= "2026-01-15" ? "2026-01-15" : c.delivery_dates[0]); })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!date) return;
    get(`/api/decision?delivery_date=${date}`).then(setDay).catch((e) => setError(e.message));
  }, [date]);

  if (error) return <div className="wrap"><div className="err"><b>Could not load data.</b><p>{error}. Check that the backend is running and that data/actuals.csv and data/forecasts.csv exist (run <code>python -m app.elexon</code>).</p></div></div>;
  if (!cfg || !month || !horizon) return <div className="wrap"><p>Loading…</p></div>;

  const o = month.overall;
  const days = month.by_day.map((d) => d.delivery_date);

  return (
    <div className="wrap">
      <header>
        <h1>How far off was the wind forecast at 09:00 the day before?</h1>
        <p className="lede">
          For every delivery day in the pilot window ({dayLabel(cfg.delivery_dates[0])} to {dayLabel(cfg.delivery_dates[1])} 2026), we take the latest national wind forecast
          published by the {cfg.decision_time_default} UK decision time on D-1 and compare it with what wind actually delivered. Source: Elexon WINDFOR and FUELHH.
        </p>
      </header>

      <div className="kpis" role="list">
        <div className="kpi" role="listitem"><b>{gw(o.bias_mw)}</b><span>average over-forecast (bias)</span></div>
        <div className="kpi" role="listitem"><b>{o.share_overforecast_pct}%</b><span>of hours forecast too high</span></div>
        <div className="kpi" role="listitem"><b>{mw(o.mae_mw)}</b><span>mean absolute error</span></div>
        <div className="kpi" role="listitem"><b>{mw(o.rmse_mw)}</b><span>RMSE</span></div>
        <div className="kpi" role="listitem"><b>{o.wmape_pct}%</b><span>weighted error (wMAPE)</span></div>
        <div className="kpi" role="listitem"><b>{gw(o.overforecast_p90_mw)}</b><span>over-forecast in the worst 1 of 10 hours</span></div>
      </div>

      <div className="plan">
        <p>
          In this window the 09:00 forecast averaged <b>{mw(o.avg_forecast_mw)}</b> against <b>{mw(o.avg_actual_mw)}</b> actually generated.
          Wind was over-forecast in {o.share_overforecast_pct}% of hours, so power left to buy from thermal plants was understated more often than overstated.
        </p>
        <p>
          In 9 of 10 hours the shortfall was no more than <b>{mw(o.overforecast_p90_mw)}</b>. Holding that much extra cover would have absorbed most misses; a smaller correction of about {mw(o.bias_mw)} would remove the average bias.
        </p>
        <p>Based on one month of data. This portal measures the error; it does not establish why the forecast leans high.</p>
      </div>

      <section>
        <h2>One delivery day</h2>
        <p className="sub">What the desk could see when deciding, and how the day turned out. Red shading marks hours where wind was over-forecast, blue where it was under-forecast.</p>
        <div className="panel">
          <div className="bar">
            <label>Delivery day
              <select value={date || ""} onChange={(e) => setDate(e.target.value)}>
                {days.map((d) => <option key={d} value={d}>{dayLabel(d)}</option>)}
              </select>
            </label>
            {day && (
              <div className="facts">
                <span>Decision taken <b>{day.decision_cutoff_local}</b></span>
                <span>Forecast used was published <b>{day.forecast_published_min.replace("T", " ").replace(":00Z", " UTC")}</b></span>
                <span>Day MAE <b>{mw(day.metrics.mae_mw)}</b></span>
                <span>Day bias <b>{mw(day.metrics.bias_mw)}</b></span>
              </div>
            )}
          </div>
          {day && <DayChart series={day.series} />}
          <div className="legend">
            <span><i style={{ background: C.actual }} />Actual</span>
            <span><i style={{ background: C.forecast }} />Forecast at decision time</span>
            <span><i style={{ background: C.over }} />Over-forecast</span>
            <span><i style={{ background: C.under }} />Under-forecast</span>
          </div>
        </div>
      </section>

      <section>
        <h2>Every day in the window</h2>
        <p className="sub">Average error per delivery day (forecast minus actual). Above zero means over-forecast. Select a bar to open that day above.</p>
        <div className="panel">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={month.by_day} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <Grid />
              <XAxis dataKey="delivery_date" tick={tick} tickFormatter={(d) => d.slice(8)} interval={1} />
              <YAxis tick={tick} tickFormatter={axisGW} unit=" GW" width={56} />
              <ReferenceLine y={0} stroke="var(--muted)" />
              <Tooltip formatter={(v) => mw(v)} labelFormatter={dayLabel} contentStyle={{ background: "var(--panel)", border: "1px solid var(--line)" }} />
              <Bar dataKey="bias_mw" name="Bias" onClick={(d) => setDate(d.delivery_date)} cursor="pointer">
                {month.by_day.map((d) => (
                  <Cell key={d.delivery_date} fill={d.bias_mw >= 0 ? C.over : C.under} stroke={d.delivery_date === date ? "var(--ink)" : "none"} strokeWidth={2} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section>
        <h2>When the error is largest</h2>
        <div className="two">
          <div>
            <p className="sub">By how far ahead the forecast was made. Uses every published forecast, not only the decision-time one.</p>
            <div className="panel">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={horizon} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <Grid />
                  <XAxis dataKey="horizon" tick={tick} />
                  <YAxis tick={tick} tickFormatter={axisGW} unit=" GW" width={56} />
                  <Tooltip formatter={(v) => mw(v)} contentStyle={{ background: "var(--panel)", border: "1px solid var(--line)" }} />
                  <Bar dataKey="mae_mw" name="Mean absolute error" fill={C.actual} />
                  <Bar dataKey="bias_mw" name="Bias" fill={C.over} />
                </BarChart>
              </ResponsiveContainer>
              <div className="legend"><span><i style={{ background: C.actual }} />Mean absolute error</span><span><i style={{ background: C.over }} />Bias</span></div>
            </div>
          </div>
          <div>
            <p className="sub">By hour of day (UK time), at the decision-time forecast.</p>
            <div className="panel">
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={month.by_hour} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <Grid />
                  <XAxis dataKey="hour" tick={tick} />
                  <YAxis tick={tick} tickFormatter={axisGW} unit=" GW" width={56} />
                  <Tooltip formatter={(v) => mw(v)} labelFormatter={(h) => `${String(h).padStart(2, "0")}:00`} contentStyle={{ background: "var(--panel)", border: "1px solid var(--line)" }} />
                  <Line dataKey="mae_mw" name="Mean absolute error" stroke={C.actual} dot={false} strokeWidth={2} />
                  <Line dataKey="bias_mw" name="Bias" stroke={C.over} dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
              <div className="legend"><span><i style={{ background: C.actual }} />Mean absolute error</span><span><i style={{ background: C.over }} />Bias</span></div>
            </div>
          </div>
        </div>
        <p className="note">Error = forecast − actual. Forecasts are hourly; half-hourly actuals are averaged to the hour. The decision time is an assumption, set in the backend config.</p>
      </section>
    </div>
  );
}

function DayChart({ series }) {
  const data = series.map((r) => ({
    t: r.startTime.slice(11, 16),
    forecast: r.forecast_mw,
    actual: r.actual_mw,
    over: r.actual_mw != null && r.forecast_mw > r.actual_mw ? [r.actual_mw, r.forecast_mw] : null,
    under: r.actual_mw != null && r.forecast_mw < r.actual_mw ? [r.forecast_mw, r.actual_mw] : null,
  }));
  return (
    <ResponsiveContainer width="100%" height={340}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <Grid />
        <XAxis dataKey="t" tick={tick} interval={2} />
        <YAxis tick={tick} tickFormatter={axisGW} unit=" GW" width={56} domain={[0, "auto"]} />
        <Tooltip
          formatter={(v, n) => (Array.isArray(v) ? null : [mw(v), n])}
          contentStyle={{ background: "var(--panel)", border: "1px solid var(--line)" }}
          itemSorter={() => 0}
        />
        <Area dataKey="over" name="Over-forecast" stroke="none" fill={C.over} fillOpacity={0.22} isAnimationActive={false} legendType="none" tooltipType="none" />
        <Area dataKey="under" name="Under-forecast" stroke="none" fill={C.under} fillOpacity={0.22} isAnimationActive={false} legendType="none" tooltipType="none" />
        <Line dataKey="actual" name="Actual" stroke={C.actual} strokeWidth={2.5} dot={false} />
        <Line dataKey="forecast" name="Forecast" stroke={C.forecast} strokeWidth={2.5} dot={false} strokeDasharray="6 3" />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
