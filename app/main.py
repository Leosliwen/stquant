from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .schemas import BacktestParams, DownloadBarsRequest, FilterParams, LiveTradeConfig
from .services import filter_candidates, get_agent_task, health, request_download, run_grid_backtest, save_live_config


app = FastAPI(title="STQuant", version="0.1.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    with open("app/templates/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/health")
def api_health():
    return health()


@app.post("/api/candidates")
def api_candidates(params: FilterParams):
    return {"rows": filter_candidates(params)}


@app.post("/api/backtest")
def api_backtest(params: BacktestParams):
    return run_grid_backtest(params)


@app.post("/api/download/bars")
def api_download_bars(payload: DownloadBarsRequest):
    return request_download(payload)


@app.get("/api/download/task/{task_id}")
def api_download_task(task_id: str):
    return get_agent_task(task_id)


@app.post("/api/live/config")
def api_live_config(config: LiveTradeConfig):
    return save_live_config(config)
