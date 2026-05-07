#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Windows miniQMT agent for STQuant.

Run from Windows with the QMT Python environment:
  D:\gjzqqmt\qmt_env\python.exe qmt_agent.py

The WSL web app calls this service to access miniQMT indirectly.
"""

from __future__ import annotations

import json
import math
import os
import sys
import threading
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Iterable, List, Sequence


XTQUANT_PATH = os.getenv("XTQUANT_PATH", r"D:\gjzqqmt\qmt_env\Lib\site-packages")
if XTQUANT_PATH not in sys.path:
    sys.path.insert(0, XTQUANT_PATH)

from clickhouse_driver import Client  # noqa: E402
from xtquant import xtdata  # noqa: E402


HOST = os.getenv("QMT_AGENT_HOST", "0.0.0.0")
PORT = int(os.getenv("QMT_AGENT_PORT", "8710"))
CH_HOST = os.getenv("QMT_AGENT_CLICKHOUSE_HOST", "127.0.0.1")
CH_PORT = int(os.getenv("QMT_AGENT_CLICKHOUSE_PORT", "9000"))
CH_DATABASE = os.getenv("QMT_AGENT_CLICKHOUSE_DATABASE", "xtquant")
CH_USER = os.getenv("QMT_AGENT_CLICKHOUSE_USER", "default")
CH_PASSWORD = os.getenv("QMT_AGENT_CLICKHOUSE_PASSWORD", "")
BATCH_SIZE = int(os.getenv("QMT_AGENT_BATCH_SIZE", "50"))

TASKS: Dict[str, Dict[str, Any]] = {}


def ch_client() -> Client:
    return Client(host=CH_HOST, port=CH_PORT, user=CH_USER, password=CH_PASSWORD, database=CH_DATABASE)


def safe_float(value: Any):
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def parse_time(value: Any, period: str) -> datetime:
    text = str(value).strip()
    if period == "1d":
        for fmt in ("%Y%m%d", "%Y-%m-%d"):
            try:
                return datetime.strptime(text[:10], fmt)
            except ValueError:
                pass
    for fmt in ("%Y%m%d%H%M%S", "%Y-%m-%d %H:%M:%S", "%Y%m%d%H%M"):
        try:
            return datetime.strptime(text[: len(fmt)], fmt)
        except ValueError:
            pass
    if len(text) == 8:
        return datetime.strptime(text, "%Y%m%d")
    raise ValueError(f"unsupported time value: {value}")


def chunks(items: Sequence[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(items), size):
        yield list(items[i : i + size])


def ensure_bar_table(client: Client, period: str) -> str:
    table = f"stock_bar_{period}"
    client.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {CH_DATABASE}.{table}
        (
            code String,
            period LowCardinality(String),
            trade_time DateTime('Asia/Shanghai'),
            trade_day Date,
            open Nullable(Float64),
            high Nullable(Float64),
            low Nullable(Float64),
            close Nullable(Float64),
            volume Nullable(Float64),
            amount Nullable(Float64),
            dividend_type LowCardinality(String),
            update_time DateTime DEFAULT now()
        )
        ENGINE = ReplacingMergeTree(update_time)
        PARTITION BY toYYYYMM(trade_day)
        ORDER BY (code, period, trade_time)
        """
    )
    return table


def update_task(task_id: str, **fields: Any) -> None:
    TASKS[task_id].update(fields)
    TASKS[task_id]["updated_at"] = datetime.now().isoformat(timespec="seconds")


def download_bars_task(task_id: str, payload: Dict[str, Any]) -> None:
    codes = [str(c).upper() for c in payload.get("codes", []) if str(c).strip()]
    period = str(payload.get("period", "1m"))
    start_time = str(payload.get("start_time", ""))
    end_time = str(payload.get("end_time", ""))
    dividend_type = str(payload.get("dividend_type", "none"))
    fields = ["open", "high", "low", "close", "volume", "amount"]

    try:
        client = ch_client()
        table = ensure_bar_table(client, period)
        inserted = 0
        update_task(task_id, status="running", total=len(codes), inserted=0, table=table)

        for batch_no, batch_codes in enumerate(chunks(codes, BATCH_SIZE), 1):
            update_task(task_id, batch=batch_no, message=f"downloading {len(batch_codes)} codes")
            try:
                xtdata.download_history_data2(batch_codes, period, start_time, end_time)
            except Exception:
                for code in batch_codes:
                    try:
                        xtdata.download_history_data(code, period, start_time, end_time)
                    except Exception:
                        pass

            data = xtdata.get_market_data(
                field_list=fields,
                stock_list=batch_codes,
                period=period,
                start_time=start_time,
                end_time=end_time,
                dividend_type=dividend_type,
            )
            close_df = data.get("close")
            if close_df is None:
                continue
            rows = []
            for code in batch_codes:
                if code not in close_df.index:
                    continue
                for time_key in sorted(close_df.columns):
                    trade_time = parse_time(time_key, period)
                    values = {}
                    for field in fields:
                        df = data.get(field)
                        values[field] = None
                        if df is not None and code in df.index and time_key in df.columns:
                            values[field] = safe_float(df.loc[code, time_key])
                    rows.append(
                        (
                            code,
                            period,
                            trade_time,
                            trade_time.date(),
                            values["open"],
                            values["high"],
                            values["low"],
                            values["close"],
                            values["volume"],
                            values["amount"],
                            dividend_type,
                        )
                    )
            if rows:
                client.execute(
                    f"""
                    INSERT INTO {CH_DATABASE}.{table}
                    (code, period, trade_time, trade_day, open, high, low, close, volume, amount, dividend_type)
                    VALUES
                    """,
                    rows,
                )
                inserted += len(rows)
                update_task(task_id, inserted=inserted)

        update_task(task_id, status="done", message="completed", inserted=inserted)
    except Exception as exc:
        update_task(task_id, status="error", error=repr(exc))


class Handler(BaseHTTPRequestHandler):
    server_version = "STQuantQmtAgent/0.1"

    def _json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self._json(200, {"ok": True})

    def do_GET(self) -> None:
        if self.path == "/health":
            ok = True
            error = None
            try:
                xtdata.get_full_tick(["000001.SZ"])
            except Exception as exc:
                ok = False
                error = repr(exc)
            self._json(200, {"ok": ok, "qmt": ok, "error": error, "time": datetime.now().isoformat(timespec="seconds")})
            return

        if self.path.startswith("/task/"):
            task_id = self.path.rsplit("/", 1)[-1]
            self._json(200, TASKS.get(task_id, {"status": "missing", "task_id": task_id}))
            return

        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")

        if self.path == "/download_bars":
            task_id = uuid.uuid4().hex[:12]
            TASKS[task_id] = {
                "task_id": task_id,
                "status": "queued",
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "payload": payload,
            }
            thread = threading.Thread(target=download_bars_task, args=(task_id, payload), daemon=True)
            thread.start()
            self._json(202, TASKS[task_id])
            return

        self._json(404, {"error": "not found"})

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {self.address_string()} {fmt % args}")


def main() -> int:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"qmt_agent listening on http://{HOST}:{PORT}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
