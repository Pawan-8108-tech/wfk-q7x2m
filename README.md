# Wind forecast check for day-ahead buying

A small web app for a day-ahead power desk. For every delivery day in the pilot window it shows
(1) the latest national wind forecast that was available at decision time and
(2) how accurate that forecast turned out to be, in MW and %.

Data: Elexon BMRS only. `FUELHH` (actual wind, fuelType = WIND) and `WINDFOR` (wind forecasts, every `publishTime`).

**Live app:** https://wfk-q7x2m.vercel.app/
**Video walkthrough:** _paste your unlisted YouTube link here_

> **AI tools:** this project was built with the help of an AI assistant (Claude, by Anthropic) for code generation and design.
> I ran, tested and reviewed the code myself.

## Key assumptions

- **Scope:** purchase decisions made 1-31 Jan 2026, so delivery days are 2 Jan to 1 Feb 2026.
- **Decision time:** 09:00 UK time on D-1 (the day before delivery). Change it with the `DECISION_TIME` env var
  (`backend/app/config.py`) or the `decision_time` query parameter. This is an assumption, not taken from the brief.
- **Forecast used:** for each target hour, the latest forecast with `publishTime <= decision time`. Later forecasts are never used.
- **Resolution:** WINDFOR is hourly, FUELHH is half-hourly. Actuals are averaged over the two half-hours of each hour (complete hours only).
- **Error sign:** error = forecast - actual. Positive means wind was over-forecast (risk of buying too little thermal).

## Files and directories

```
backend/
  app/config.py      settings: decision time, window, time zone
  app/elexon.py      Elexon API client; `python -m app.elexon` saves the Jan 2026 snapshot to data/
  app/analysis.py    forecast selection (no look-ahead) and error metrics (pure functions)
  app/store.py       loads the CSV snapshot into memory
  app/main.py        FastAPI endpoints (and serves the built React app when ./static exists)
  data/              actuals.csv, forecasts.csv (snapshot of the Elexon data)
  scripts/           make_synthetic.py: fake demo data for offline development only
  tests/             unit tests for the core logic
frontend/            React (Vite + Recharts) source
public/              built React app, served by Vercel
api/index.py         Vercel entrypoint for the API
Dockerfile           builds React, then runs the API + app on port 8000
docker-compose.yml   `docker compose up`
vercel.json          routes /api/* to the Python function
```

### API

| Endpoint | Purpose |
|---|---|
| `GET /api/config` | window, decision time, data size |
| `GET /api/decision?delivery_date=2026-01-15` | forecast known at decision time vs actual, hour by hour |
| `GET /api/metrics?start=&end=` | MAE, RMSE, bias, wMAPE, P90 over/under-forecast; by day and by hour |
| `GET /api/horizon` | error by how far ahead the forecast was made (all published forecasts) |

## How to start

### With Docker

```
docker compose up --build
```
Open http://localhost:8000

### Without Docker (Windows)

```
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m app.elexon        # only if data/ is empty: downloads the Jan 2026 data
python -m pytest
uvicorn app.main:app --reload
```
Open http://localhost:8000 (API docs at /docs). The built React app is served from `backend/static`.

### Frontend development

```
cd frontend
npm install
npm run dev                 # http://localhost:5173, proxies /api to :8000
npm run build               # output in frontend/dist
```
After a build, copy `frontend/dist` into `public/` (Vercel) and `backend/static` (local server).

## Deploying to Vercel

1. Push this repo to GitHub (make sure `backend/data/*.csv` are committed).
2. In Vercel: Add New > Project > import the repo. Keep the root directory as the repo root. Deploy.
3. Open the deployment URL and check `/api/health` returns `"data_loaded": true`.

## Results in this window (09:00 D-1 decision)

Average forecast 13,031 MW against 11,284 MW actual. Bias +1,748 MW, MAE 2,039 MW, RMSE 2,505 MW, wMAPE 18.1%.
Wind was over-forecast in 84.9% of hours. The 90th-percentile over-forecast was 4,098 MW.
These figures describe one month; the cause of the bias is not established by this analysis.
