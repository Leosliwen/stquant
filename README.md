# STQuant

STQuant is a local stock-grid strategy workstation.

The WSL app provides:

- low-price stock filtering from ClickHouse
- configurable grid backtests
- tables and charts in a browser UI
- data-download requests forwarded to a Windows miniQMT agent
- a dry-run live-trading configuration placeholder

The Windows agent provides:

- `GET /health`
- `POST /download_bars`
- `GET /task/{task_id}`

## Run WSL Web App

```bash
cd /home/leo/stquant
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./scripts/run_dev.sh
```

Open:

```text
http://localhost:8501
```

Useful environment variables:

```bash
export STQUANT_CLICKHOUSE_HOST=127.0.0.1
export STQUANT_CLICKHOUSE_PORT=8123
export STQUANT_QMT_AGENT_URL=http://127.0.0.1:8710
```

If the Windows agent is not reachable from WSL through `127.0.0.1`, set
`STQUANT_QMT_AGENT_URL` to the Windows host IP, often shown in WSL by:

```bash
grep nameserver /etc/resolv.conf
```

## Run Windows miniQMT Agent

From Windows PowerShell:

```powershell
cd D:\gjzqqmt\python_scripts\qmt_agent
D:\gjzqqmt\qmt_env\python.exe .\qmt_agent.py
```

For daily use, double-click:

```text
D:\gjzqqmt\python_scripts\qmt_agent\toggle_qmt_agent.bat
```

If port `8710` is free it starts the agent. If port `8710` is already
listening it stops the process on that port.

If ClickHouse is in WSL but exposed on Windows localhost, the default
`127.0.0.1:9000` works. Otherwise set:

```powershell
$env:QMT_AGENT_CLICKHOUSE_HOST="127.0.0.1"
$env:QMT_AGENT_CLICKHOUSE_PORT="9000"
```

## Notes

The first backtest engine is intentionally conservative and simple. It uses
daily raw prices for grid trigger approximation. Minute-bar backtesting can be
added after downloading `stock_bar_1m` through the Windows agent.
