from __future__ import annotations

from pydantic import BaseModel, Field


class FilterParams(BaseModel):
    min_price: float = 3.0
    max_price: float = 5.5
    min_avg_amount_20d: float = 30_000_000
    min_avg_amount_60d: float = 20_000_000
    min_turnover_20d: float = 0.5
    min_amplitude_60d: float = 1.5
    min_volatility_60d: float = 1.0
    max_price_position_3y: float = 0.45
    min_return_120d: float = -35.0
    max_return_120d: float = 35.0
    max_drawdown_1y: float = 55.0
    max_consecutive_down_days: int = Field(default=5, ge=0, le=30)
    min_listing_years: float = 3.0
    max_debt_asset_ratio: float = 75.0
    min_roe: float = 0.0
    require_positive_profit: bool = True
    require_positive_operating_cash_flow: bool = False
    max_per_industry: int = Field(default=8, ge=1, le=100)
    limit: int = Field(default=300, ge=1, le=2000)


class BacktestParams(BaseModel):
    codes: list[str] = Field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None
    initial_cash: float = 100_000
    initial_position_pct: float = 0.009
    max_position_pct: float = 0.03
    grid_step: float = 0.05
    take_profit: float = 0.05
    fee_rate: float = 0.00025
    slippage: float = 0.005
    max_codes: int = Field(default=80, ge=1, le=300)


class DownloadBarsRequest(BaseModel):
    codes: list[str]
    period: str = "1m"
    start_time: str
    end_time: str
    dividend_type: str = "none"


class LiveTradeConfig(BaseModel):
    enabled: bool = False
    dry_run: bool = True
    max_total_position_pct: float = 0.4
    max_single_position_pct: float = 0.03
    grid_step: float = 0.05
    take_profit: float = 0.05
