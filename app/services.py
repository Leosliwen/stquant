from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd
import requests

from .config import settings
from .db import get_client, rows_as_dicts
from .schemas import BacktestParams, DownloadBarsRequest, FilterParams, LiveTradeConfig


def health() -> dict[str, Any]:
    client = get_client()
    ch_ok = bool(client.command("SELECT 1"))
    agent = {"ok": False, "error": None}
    try:
        resp = requests.get(f"{settings.qmt_agent_url}/health", timeout=3)
        agent = resp.json()
        agent["ok"] = resp.ok
    except Exception as exc:
        agent = {"ok": False, "error": str(exc)}
    return {"clickhouse": ch_ok, "qmt_agent": agent}


def filter_candidates(params: FilterParams) -> list[dict[str, Any]]:
    client = get_client()
    positive_profit_sql = "AND f.net_profit_parent > 0" if params.require_positive_profit else ""
    positive_cash_sql = "AND f.operating_cash_flow > 0" if params.require_positive_operating_cash_flow else ""
    query = f"""
    WITH latest_fin AS
    (
        SELECT
            code,
            max(report_date) AS latest_report_date,
            argMax(revenue, report_date) AS revenue,
            argMax(net_profit_parent, report_date) AS net_profit_parent,
            argMax(operating_cash_flow, report_date) AS operating_cash_flow,
            argMax(roe, report_date) AS roe,
            argMax(debt_asset_ratio, report_date) AS debt_asset_ratio,
            argMax(eps_basic, report_date) AS eps_basic,
            argMax(bps, report_date) AS bps
        FROM stock_financial_summary
        GROUP BY code
    )
    SELECT
        c.code,
        c.name,
        c.prefix,
        c.latest_close_raw,
        c.latest_close_front,
        c.latest_trade_day,
        c.avg_amount_20d,
        c.low_front_3y,
        c.high_front_3y,
        c.price_position_3y,
        f.latest_report_date AS report_date,
        f.revenue,
        f.net_profit_parent,
        f.operating_cash_flow,
        f.roe,
        f.debt_asset_ratio,
        f.eps_basic,
        f.bps
    FROM v_grid_low_price_candidates AS c
    LEFT JOIN latest_fin AS f ON c.code = f.code
    WHERE c.latest_close_raw >= {{min_price:Float64}}
      AND c.latest_close_raw <= {{max_price:Float64}}
      AND c.avg_amount_20d >= {{min_avg_amount_20d:Float64}}
      AND c.price_position_3y <= {{max_price_position_3y:Float64}}
      AND (f.debt_asset_ratio IS NULL OR f.debt_asset_ratio <= {{max_debt_asset_ratio:Float64}})
      AND (f.roe IS NULL OR f.roe >= {{min_roe:Float64}})
      AND positionCaseInsensitive(c.name, 'ST') = 0
      AND position(c.name, '\u9000') = 0
      {positive_profit_sql}
      {positive_cash_sql}
    ORDER BY c.price_position_3y ASC, c.avg_amount_20d DESC
    LIMIT {{limit:UInt32}}
    """
    result = client.query(
        query,
        parameters={
            "min_price": params.min_price,
            "max_price": params.max_price,
            "min_avg_amount_20d": params.min_avg_amount_20d,
            "max_price_position_3y": params.max_price_position_3y,
            "max_debt_asset_ratio": params.max_debt_asset_ratio,
            "min_roe": params.min_roe,
            "limit": params.limit,
        },
    )
    return rows_as_dicts(result)


def load_daily_bars(codes: list[str], start_date: str | None, end_date: str | None) -> pd.DataFrame:
    client = get_client()
    if not codes:
        codes = [row["code"] for row in filter_candidates(FilterParams(limit=80))]
    codes = codes[:300]
    where_dates = []
    params: dict[str, Any] = {"codes": codes}
    if start_date:
        where_dates.append("trade_day >= {start_date:Date}")
        params["start_date"] = start_date
    if end_date:
        where_dates.append("trade_day <= {end_date:Date}")
        params["end_date"] = end_date
    date_sql = " AND " + " AND ".join(where_dates) if where_dates else ""
    result = client.query(
        f"""
        SELECT code, name, trade_day, close_raw, high_raw, low_raw, amount
        FROM stock_1d
        WHERE code IN {{codes:Array(String)}} {date_sql}
          AND close_raw IS NOT NULL
        ORDER BY code, trade_day
        """,
        parameters=params,
    )
    return pd.DataFrame(rows_as_dicts(result))


def run_grid_backtest(params: BacktestParams) -> dict[str, Any]:
    codes = params.codes[: params.max_codes]
    df = load_daily_bars(codes, params.start_date, params.end_date)
    if df.empty:
        return {"summary": {}, "trades": [], "equity_curve": [], "per_stock": []}

    trades: list[dict[str, Any]] = []
    per_stock: list[dict[str, Any]] = []
    total_realized = 0.0
    total_cost = 0.0
    total_end_value = 0.0
    equity_by_day: dict[date, float] = {}

    for code, g in df.groupby("code", sort=False):
        g = g.sort_values("trade_day")
        name = str(g.iloc[0]["name"])
        first_price = float(g.iloc[0]["close_raw"])
        if first_price <= 0:
            continue
        cash_budget = params.initial_cash * params.max_position_pct
        base_budget = params.initial_cash * params.initial_position_pct
        shares = int(base_budget / first_price / 100) * 100
        if shares <= 0:
            shares = 100
        avg_cost = first_price + params.slippage
        used_cash = shares * avg_cost
        realized = 0.0
        grid_lots: list[tuple[float, int]] = []
        next_buy = avg_cost - params.grid_step

        for _, row in g.iterrows():
            day = row["trade_day"]
            low = float(row["low_raw"] or row["close_raw"])
            high = float(row["high_raw"] or row["close_raw"])
            close = float(row["close_raw"])

            while low <= next_buy and used_cash + next_buy * 100 <= cash_budget:
                buy_price = next_buy + params.slippage
                lot = 100
                cost = buy_price * lot * (1 + params.fee_rate)
                used_cash += cost
                shares += lot
                grid_lots.append((buy_price, lot))
                trades.append({"date": str(day), "code": code, "name": name, "side": "BUY", "price": round(buy_price, 4), "shares": lot})
                next_buy -= params.grid_step

            while grid_lots and high >= grid_lots[-1][0] + params.take_profit:
                buy_price, lot = grid_lots.pop()
                sell_price = buy_price + params.take_profit - params.slippage
                proceeds = sell_price * lot * (1 - params.fee_rate)
                profit = proceeds - buy_price * lot
                realized += profit
                total_realized += profit
                used_cash = max(0, used_cash - buy_price * lot)
                shares -= lot
                trades.append({"date": str(day), "code": code, "name": name, "side": "SELL", "price": round(sell_price, 4), "shares": lot, "profit": round(profit, 2)})
                next_buy = min(next_buy + params.grid_step, close - params.grid_step)

            equity_by_day[day] = equity_by_day.get(day, 0.0) + realized + shares * close

        last_close = float(g.iloc[-1]["close_raw"])
        end_value = shares * last_close
        total_end_value += end_value
        total_cost += used_cash
        per_stock.append(
            {
                "code": code,
                "name": name,
                "realized_profit": round(realized, 2),
                "remaining_shares": shares,
                "end_value": round(end_value, 2),
                "last_close": round(last_close, 3),
            }
        )

    equity_curve = [{"date": str(day), "equity": round(value, 2)} for day, value in sorted(equity_by_day.items())]
    summary = {
        "codes": len(per_stock),
        "trades": len(trades),
        "realized_profit": round(total_realized, 2),
        "end_value": round(total_end_value, 2),
        "capital_used_est": round(total_cost, 2),
    }
    return {"summary": summary, "trades": trades[-500:], "equity_curve": equity_curve, "per_stock": per_stock}


def request_download(payload: DownloadBarsRequest) -> dict[str, Any]:
    resp = requests.post(f"{settings.qmt_agent_url}/download_bars", json=payload.model_dump(), timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_agent_task(task_id: str) -> dict[str, Any]:
    resp = requests.get(f"{settings.qmt_agent_url}/task/{task_id}", timeout=5)
    resp.raise_for_status()
    return resp.json()


def save_live_config(config: LiveTradeConfig) -> dict[str, Any]:
    # The first version is deliberately dry-run only from the WSL app side.
    return {"status": "saved", "config": config.model_dump(), "note": "live trading bridge is not armed yet"}
