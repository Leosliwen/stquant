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
    min_avg_amount_60d: num("minAmount60"),
    min_turnover_20d: num("minTurnover20"),
    min_amplitude_60d: num("minAmplitude60"),
    min_volatility_60d: num("minVolatility60"),
    max_price_position_3y: num("maxPosition"),
    min_return_120d: num("minReturn120"),
    max_return_120d: num("maxReturn120"),
    max_drawdown_1y: num("maxDrawdown1y"),
    max_consecutive_down_days: Number($("maxConsecutiveDown").value),
    min_listing_years: Number($("minListingYears").value),
    max_debt_asset_ratio: num("maxDebt"),
    min_roe: num("minRoe"),
    max_per_industry: Number($("maxPerIndustry").value),
    limit: Number($("limit").value),
    require_positive_profit: $("positiveProfit").checked,
    require_positive_operating_cash_flow: $("positiveCash").checked,
  };
}

async function loadCandidates() {
  $("candidateMeta").textContent = "查询中...";
  $("candidateSummary").innerHTML = "";
  const data = await postJson("/api/candidates", filterPayload());
  candidates = data.rows;
  $("candidateMeta").textContent = `共 ${candidates.length} 只`;
  if (candidates.length) {
    const top = candidates[0];
    $("candidateSummary").innerHTML = `
      <div><span>首位股票</span>${top.code} ${top.name}</div>
      <div><span>首位分数</span>${format(top.total_score, 1)}</div>
      <div><span>首位现价</span>${format(top.latest_close_raw, 2)}</div>
      <div><span>候选数量</span>${candidates.length}</div>
    `;
  }
  renderTable("candidateTable", candidates, [
    { key: "code", label: "代码" },
    { key: "name", label: "名称" },
    { key: "latest_close_raw", label: "现价", format },
    { key: "avg_amount_20d", label: "20日成交额", format: (v) => format(v / 10000, 0) + "万" },
    { key: "avg_amount_60d", label: "60日成交额", format: (v) => format(v / 10000, 0) + "万" },
    { key: "avg_turnover_20d", label: "20日换手", format: (v) => format(v, 2) + "%" },
    { key: "avg_amplitude_60d", label: "60日振幅", format: (v) => format(v, 2) + "%" },
    { key: "volatility_60d", label: "60日波动", format: (v) => format(v, 2) + "%" },
    { key: "price_position_3y", label: "3年分位", format: (v) => format(v * 100, 1) + "%" },
    { key: "return_120d", label: "120日涨跌", format: (v) => format(v, 1) + "%" },
    { key: "drawdown_1y", label: "1年回撤", format: (v) => format(v, 1) + "%" },
    { key: "consecutive_down_days", label: "连续下跌", format: (v) => format(v, 0) + "天" },
    { key: "net_profit_parent", label: "归母净利", format: (v) => format(v / 100000000, 2) + "亿" },
    { key: "operating_cash_flow", label: "经营现金流", format: (v) => format(v / 100000000, 2) + "亿" },
    { key: "roe", label: "ROE", format: (v) => format(v, 2) },
    { key: "debt_asset_ratio", label: "负债率", format: (v) => format(v, 2) + "%" },
    { key: "total_score", label: "总分", format: (v) => format(v, 1) },
  ]);
  $("candidateTable").parentElement.parentElement.scrollIntoView({ behavior: "smooth", block: "start" });
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

function renderDataHealth(data) {
  const agent = data.qmt_agent || {};
  const cards = [
    {
      label: "ClickHouse 数据库",
      ok: Boolean(data.clickhouse),
      detail: data.clickhouse ? "可访问" : "不可访问",
    },
    {
      label: "Windows qmt_agent",
      ok: Boolean(agent.ok),
      detail: agent.ok ? "可访问" : (agent.error || "不可访问"),
    },
    {
      label: "miniQMT 行情接口",
      ok: Boolean(agent.qmt),
      detail: agent.qmt ? "可访问" : (agent.error || "不可访问"),
    },
  ];
  $("dataHealthStatus").innerHTML = cards.map((card) => `
    <div class="statusCard ${card.ok ? "ok" : "bad"}">
      <span>${card.label}</span>
      <strong>${card.ok ? "正常" : "异常"}</strong>
      <small>${card.detail}</small>
    </div>
  `).join("");
}

async function testDataHealth() {
  $("dataHealthStatus").innerHTML = '<div class="statusCard"><span>连通性测试</span><strong>测试中...</strong></div>';
  try {
    const resp = await fetch("/api/health");
    const data = await resp.json();
    renderDataHealth(data);
    $("downloadStatus").textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    $("dataHealthStatus").innerHTML = `
      <div class="statusCard bad">
        <span>连通性测试</span>
        <strong>异常</strong>
        <small>${String(err)}</small>
      </div>`;
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

function activateTab(tabId) {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tabId);
  });
  document.querySelectorAll(".tabPage").forEach((page) => {
    const isActive = page.id === tabId;
    page.classList.toggle("active", isActive);
    page.hidden = !isActive;
  });
}

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => activateTab(btn.dataset.tab));
});

$("filterBtn").addEventListener("click", loadCandidates);
$("backtestBtn").addEventListener("click", runBacktest);
$("backtestSelectedBtn").addEventListener("click", runBacktest);
$("dataHealthBtn").addEventListener("click", testDataHealth);
$("downloadBtn").addEventListener("click", downloadBars);
$("saveLiveBtn").addEventListener("click", saveLive);
$("healthBtn").addEventListener("click", async () => {
  const resp = await fetch("/api/health");
  const data = await resp.json();
  renderDataHealth(data);
  alert(JSON.stringify(data, null, 2));
});

loadCandidates().catch((err) => {
  $("candidateMeta").textContent = String(err);
});
