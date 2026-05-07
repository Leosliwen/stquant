let candidates = [];

const $ = (id) => document.getElementById(id);

function num(id) {
  return Number($(id).value);
}

async function postJson(url, payload) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

function format(v, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "";
  return Number(v).toLocaleString("zh-CN", { maximumFractionDigits: digits });
}

function renderTable(table, rows, columns) {
  const el = $(table);
  if (!rows.length) {
    el.innerHTML = "<tbody><tr><td>暂无数据</td></tr></tbody>";
    return;
  }
  el.innerHTML = `
    <thead><tr>${columns.map((c) => `<th>${c.label}</th>`).join("")}</tr></thead>
    <tbody>
      ${rows.map((r) => `<tr>${columns.map((c) => `<td>${c.format ? c.format(r[c.key], r) : (r[c.key] ?? "")}</td>`).join("")}</tr>`).join("")}
    </tbody>`;
}

function filterPayload() {
  return {
    min_price: num("minPrice"),
    max_price: num("maxPrice"),
    min_avg_amount_20d: num("minAmount"),
    max_price_position_3y: num("maxPosition"),
    max_debt_asset_ratio: num("maxDebt"),
    min_roe: num("minRoe"),
    limit: Number($("limit").value),
    require_positive_profit: $("positiveProfit").checked,
    require_positive_operating_cash_flow: $("positiveCash").checked,
  };
}

async function loadCandidates() {
  $("candidateMeta").textContent = "查询中...";
  const data = await postJson("/api/candidates", filterPayload());
  candidates = data.rows;
  $("candidateMeta").textContent = `共 ${candidates.length} 只`;
  renderTable("candidateTable", candidates, [
    { key: "code", label: "代码" },
    { key: "name", label: "名称" },
    { key: "latest_close_raw", label: "现价", format },
    { key: "avg_amount_20d", label: "20日成交额", format: (v) => format(v / 10000, 0) + "万" },
    { key: "price_position_3y", label: "3年分位", format: (v) => format(v * 100, 1) + "%" },
    { key: "net_profit_parent", label: "归母净利", format: (v) => format(v / 100000000, 2) + "亿" },
    { key: "operating_cash_flow", label: "经营现金流", format: (v) => format(v / 100000000, 2) + "亿" },
    { key: "roe", label: "ROE", format: (v) => format(v, 2) },
    { key: "debt_asset_ratio", label: "负债率", format: (v) => format(v, 2) + "%" },
  ]);
}

function backtestPayload() {
  return {
    codes: candidates.map((r) => r.code),
    initial_cash: num("initialCash"),
    initial_position_pct: num("initialPct"),
    max_position_pct: num("maxPct"),
    grid_step: num("gridStep"),
    take_profit: num("takeProfit"),
    fee_rate: num("feeRate"),
    slippage: num("slippage"),
    max_codes: Number($("maxCodes").value),
  };
}

async function runBacktest() {
  $("summary").textContent = "回测中...";
  const data = await postJson("/api/backtest", backtestPayload());
  const s = data.summary || {};
  $("summary").innerHTML = Object.entries(s).map(([k, v]) => `<div><span>${k}</span>${format(v, 2)}</div>`).join("");
  const x = data.equity_curve.map((r) => r.date);
  const y = data.equity_curve.map((r) => r.equity);
  Plotly.newPlot("equityChart", [{ x, y, type: "scatter", mode: "lines", line: { color: "#176b5b" } }], {
    margin: { t: 20, r: 20, b: 40, l: 60 },
    yaxis: { title: "权益估算" },
  }, { displayModeBar: false });
  renderTable("stockResultTable", data.per_stock || [], [
    { key: "code", label: "代码" },
    { key: "name", label: "名称" },
    { key: "realized_profit", label: "已实现收益", format },
    { key: "remaining_shares", label: "剩余股数", format: (v) => format(v, 0) },
    { key: "end_value", label: "期末市值", format },
    { key: "last_close", label: "期末价", format },
  ]);
}

async function downloadBars() {
  const payload = {
    codes: candidates.map((r) => r.code),
    period: $("period").value,
    start_time: $("downloadStart").value,
    end_time: $("downloadEnd").value,
    dividend_type: $("dividendType").value,
  };
  $("downloadStatus").textContent = "提交中...";
  try {
    const data = await postJson("/api/download/bars", payload);
    $("downloadStatus").textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    $("downloadStatus").textContent = String(err);
  }
}

async function saveLive() {
  const payload = {
    enabled: $("liveEnabled").checked,
    dry_run: $("dryRun").checked,
    max_total_position_pct: num("liveTotalPct"),
    max_single_position_pct: num("liveSinglePct"),
    grid_step: num("gridStep"),
    take_profit: num("takeProfit"),
  };
  $("liveStatus").textContent = JSON.stringify(await postJson("/api/live/config", payload), null, 2);
}

$("filterBtn").addEventListener("click", loadCandidates);
$("backtestBtn").addEventListener("click", runBacktest);
$("backtestSelectedBtn").addEventListener("click", runBacktest);
$("downloadBtn").addEventListener("click", downloadBars);
$("saveLiveBtn").addEventListener("click", saveLive);
$("healthBtn").addEventListener("click", async () => {
  const resp = await fetch("/api/health");
  alert(JSON.stringify(await resp.json(), null, 2));
});

loadCandidates().catch((err) => {
  $("candidateMeta").textContent = String(err);
});
