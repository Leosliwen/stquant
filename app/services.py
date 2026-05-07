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
    positive_profit_sql = "AND net_profit_parent > 0" if params.require_positive_profit else ""
    positive_cash_sql = "AND operating_cash_flow > 0" if params.require_positive_operating_cash_flow else ""
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
    ),
    latest_days AS
    (
        SELECT code, max(trade_day) AS latest_trade_day
        FROM stock_1d
        WHERE close_raw IS NOT NULL
        GROUP BY code
    ),
    daily_features AS
    (
        SELECT
            b.code AS code,
            b.name AS name,
            b.prefix AS prefix,
            b.open_date AS open_date,
            argMax(d.close_raw, d.trade_day) AS latest_close_raw,
            argMax(d.close_front, d.trade_day) AS latest_close_front,
            ld.latest_trade_day AS latest_trade_day,
            avgIf(d.amount, d.trade_day >= ld.latest_trade_day - 20) AS avg_amount_20d,
            avgIf(d.amount, d.trade_day >= ld.latest_trade_day - 60) AS avg_amount_60d,
            avgIf(d.turnover, d.trade_day >= ld.latest_trade_day - 20) AS avg_turnover_20d,
            avgIf((d.high_raw - d.low_raw) / nullIf(d.close_raw, 0) * 100, d.trade_day >= ld.latest_trade_day - 60) AS avg_amplitude_60d,
            stddevSampIf(d.change_pct, d.trade_day >= ld.latest_trade_day - 60) AS volatility_60d,
            min(d.low_front) AS low_front_3y,
            max(d.high_front) AS high_front_3y,
            minIf(d.low_front, d.trade_day >= ld.latest_trade_day - 365) AS low_front_1y,
            maxIf(d.high_front, d.trade_day >= ld.latest_trade_day - 365) AS high_front_1y,
            argMinIf(d.close_raw, abs(dateDiff('day', d.trade_day, ld.latest_trade_day - 120)), d.trade_day <= ld.latest_trade_day) AS close_120d_ago,
            (latest_close_raw - close_120d_ago) / nullIf(close_120d_ago, 0) * 100 AS return_120d,
            (high_front_1y - latest_close_front) / nullIf(high_front_1y, 0) * 100 AS drawdown_1y,
            (latest_close_front - low_front_3y) / nullIf(high_front_3y - low_front_3y, 0) AS price_position_3y,
            countIf(d.trade_day >= ld.latest_trade_day - 20 AND d.change_pct < 0) AS down_days_20d,
            countIf(d.trade_day >= ld.latest_trade_day - 20 AND d.change_pct <= -4.5) AS big_down_days_20d
        FROM stock_basic AS b
        INNER JOIN stock_1d AS d ON b.code = d.code
        INNER JOIN latest_days AS ld ON b.code = ld.code
        WHERE d.close_raw IS NOT NULL
        GROUP BY b.code, b.name, b.prefix, b.open_date, ld.latest_trade_day
    ),
    down_streak AS
    (
        SELECT
            code,
            countIf(change_pct < 0) AS consecutive_down_days
        FROM
        (
            SELECT
                code,
                trade_day,
                change_pct,
                sum(if(change_pct >= 0 OR change_pct IS NULL, 1, 0)) OVER (PARTITION BY code ORDER BY trade_day DESC) AS non_down_seen
            FROM stock_1d
            WHERE close_raw IS NOT NULL
        )
        WHERE non_down_seen = 0
        GROUP BY code
    ),
    sector_one AS
    (
        SELECT
            code,
            anyIf(sector_name, sector_type = 'industry') AS industry
        FROM stock_sector_map
        GROUP BY code
    ),
    scored AS
    (
        SELECT
        d.code AS code,
        d.name,
        d.prefix,
        d.open_date,
        d.latest_close_raw,
        d.latest_close_front,
        d.latest_trade_day,
        d.avg_amount_20d,
        d.avg_amount_60d,
        d.avg_turnover_20d,
        d.avg_amplitude_60d,
        d.volatility_60d,
        d.low_front_3y,
        d.high_front_3y,
        d.low_front_1y,
        d.high_front_1y,
        d.close_120d_ago,
        d.return_120d,
        d.drawdown_1y,
        d.price_position_3y,
        d.down_days_20d,
        d.big_down_days_20d,
        s.industry,
        ifNull(ds.consecutive_down_days, 0) AS consecutive_down_days,
            f.latest_report_date AS report_date,
            f.revenue,
            f.net_profit_parent,
            f.operating_cash_flow,
            f.roe,
            f.debt_asset_ratio,
            f.eps_basic,
            f.bps,
            dateDiff('day', d.open_date, d.latest_trade_day) / 365.0 AS listing_years,
            greatest(0, least(30, (1 - d.price_position_3y) * 30)) AS low_position_score,
            greatest(0, least(20, (d.avg_amount_20d / 100000000) * 12 + (d.avg_turnover_20d / 3) * 8)) AS liquidity_score,
            greatest(0, least(20, (d.avg_amplitude_60d / 5) * 12 + (d.volatility_60d / 4) * 8)) AS volatility_score,
            greatest(0, least(20,
                ifNull(if(f.net_profit_parent > 0, 5, 0), 0) +
                ifNull(if(f.operating_cash_flow > 0, 4, 0), 0) +
                greatest(0, least(5, ifNull(f.roe, 0) / 10 * 5)) +
                greatest(0, least(4, (80 - ifNull(f.debt_asset_ratio, 80)) / 80 * 4)) +
                ifNull(if(f.bps > d.latest_close_raw, 2, 0), 0)
            )) AS fundamental_score,
            greatest(0, least(20,
                if(consecutive_down_days > 3, (consecutive_down_days - 3) * 2, 0) +
                if(d.return_120d < -20, 5, 0) +
                if(d.drawdown_1y > 45, 5, 0) +
                if(d.latest_close_raw < 2.5, 4, 0) +
                if(d.big_down_days_20d >= 2, 4, 0)
            )) AS risk_penalty
        FROM daily_features AS d
        LEFT JOIN latest_fin AS f ON d.code = f.code
        LEFT JOIN sector_one AS s ON d.code = s.code
        LEFT JOIN down_streak AS ds ON d.code = ds.code
    )
    SELECT
        *,
        greatest(0, least(100, low_position_score + liquidity_score + volatility_score + fundamental_score - risk_penalty)) AS total_score
    FROM scored
    WHERE latest_close_raw >= {{min_price:Float64}}
      AND latest_close_raw <= {{max_price:Float64}}
      AND avg_amount_20d >= {{min_avg_amount_20d:Float64}}
      AND avg_amount_60d >= {{min_avg_amount_60d:Float64}}
      AND avg_turnover_20d >= {{min_turnover_20d:Float64}}
      AND avg_amplitude_60d >= {{min_amplitude_60d:Float64}}
      AND volatility_60d >= {{min_volatility_60d:Float64}}
      AND price_position_3y <= {{max_price_position_3y:Float64}}
      AND return_120d >= {{min_return_120d:Float64}}
      AND return_120d <= {{max_return_120d:Float64}}
      AND drawdown_1y <= {{max_drawdown_1y:Float64}}
      AND consecutive_down_days <= {{max_consecutive_down_days:UInt32}}
      AND listing_years >= {{min_listing_years:Float64}}
      AND (debt_asset_ratio IS NULL OR debt_asset_ratio <= {{max_debt_asset_ratio:Float64}})
      AND (roe IS NULL OR roe >= {{min_roe:Float64}})
      AND positionCaseInsensitive(name, 'ST') = 0
      AND position(name, '\u9000') = 0
      {positive_profit_sql}
      {positive_cash_sql}
    ORDER BY total_score DESC, risk_penalty ASC, price_position_3y ASC
    LIMIT {{limit:UInt32}}
    """
    result = client.query(
        query,
        parameters={
            "min_price": params.min_price,
            "max_price": params.max_price,
            "min_avg_amount_20d": params.min_avg_amount_20d,
            "min_avg_amount_60d": params.min_avg_amount_60d,
            "min_turnover_20d": params.min_turnover_20d,
            "min_amplitude_60d": params.min_amplitude_60d,
            "min_volatility_60d": params.min_volatility_60d,
            "max_price_position_3y": params.max_price_position_3y,
            "min_return_120d": params.min_return_120d,
            "max_return_120d": params.max_return_120d,
            "max_drawdown_1y": params.max_drawdown_1y,
            "max_consecutive_down_days": params.max_consecutive_down_days,
            "min_listing_years": params.min_listing_years,
            "max_debt_asset_ratio": params.max_debt_asset_ratio,
            "min_roe": params.min_roe,
            "limit": params.limit,
        },
    )
    rows = rows_as_dicts(result)

    picked: list[dict[str, Any]] = []
    industry_counts: dict[str, int] = {}
    for row in rows:
        industry = str(row.get("industry") or "")
        if industry:
            count = industry_counts.get(industry, 0)
            if count >= params.max_per_industry:
                continue
            industry_counts[industry] = count + 1
        picked.append(row)
    return picked


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
