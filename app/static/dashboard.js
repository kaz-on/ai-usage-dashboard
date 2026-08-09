const form = document.querySelector("#filters");
const dashboard = document.querySelector("#dashboard");
const message = document.querySelector("#message");
const submitButton = document.querySelector("#filter-submit");
const currencySelect = document.querySelector("#cost-currency");
const number = new Intl.NumberFormat("ja-JP", { notation: "compact", maximumFractionDigits: 1 });
const integer = new Intl.NumberFormat("ja-JP");
const charts = new Map();
const granularityLabels = { day: "日次", week: "週次", month: "月次" };
let currentData = null;
let selectedCurrency = "";

Chart.defaults.color = "#8f9ba7";
Chart.defaults.borderColor = "#29313a";
Chart.defaults.font.family = "system-ui, sans-serif";

function params() { return new URLSearchParams(new FormData(form)); }
function showMessage(text) { message.textContent = text; message.hidden = !text; }
function setLoading(loading) {
  dashboard.classList.toggle("is-loading", loading);
  dashboard.setAttribute("aria-busy", String(loading));
  submitButton.disabled = loading;
  submitButton.textContent = loading ? "更新中…" : "更新";
}
function dateLabel(timestamp, granularity = "day") {
  const date = new Date(timestamp * 1000);
  if (granularity === "month") return date.toLocaleDateString("ja-JP", { year: "numeric", month: "short", timeZone: "UTC" });
  const label = date.toLocaleDateString("ja-JP", { month: "numeric", day: "numeric", timeZone: "UTC" });
  return granularity === "week" ? `${label}週` : label;
}
function fullDateLabel(timestamp, granularity = "day") {
  const date = new Date(timestamp * 1000);
  if (granularity === "month") return date.toLocaleDateString("ja-JP", { year: "numeric", month: "long", timeZone: "UTC" });
  const label = date.toLocaleDateString("ja-JP", { year: "numeric", month: "long", day: "numeric", timeZone: "UTC" });
  return granularity === "week" ? `${label}からの週` : label;
}
function formatCurrency(value, currency, compact = false) {
  try {
    return new Intl.NumberFormat("ja-JP", {
      style: "currency",
      currency: currency.toUpperCase(),
      notation: compact ? "compact" : "standard",
      maximumFractionDigits: compact ? 1 : undefined,
    }).format(Number(value));
  } catch (_) {
    return `${currency.toUpperCase()} ${Number(value).toFixed(2)}`;
  }
}

async function loadDashboard() {
  showMessage("");
  setLoading(true);
  try {
    const response = await fetch(`/api/dashboard?${params()}`);
    if (!response.ok) throw new Error((await response.json()).detail || "データを取得できませんでした。");
    currentData = await response.json();
    render(currentData);
  } catch (error) {
    showMessage(error.message);
  } finally {
    setLoading(false);
  }
}

function render(data) {
  const usage = data.summary.usage;
  document.querySelector("#requests-total").textContent = integer.format(usage.requests);
  document.querySelector("#input-total").textContent = number.format(usage.input_tokens);
  document.querySelector("#output-total").textContent = number.format(usage.output_tokens);
  document.querySelector("#cache-rate").textContent = `${(usage.cache_rate * 100).toFixed(1)}%`;
  document.querySelector("#cost-total").textContent = data.summary.costs.length
    ? data.summary.costs.map(row => formatCurrency(row.amount, row.currency)).join(" / ") : "—";

  configureCurrencies(data);
  renderCostViews(data);
  lineChart("request-chart", data.usage_series, [{ key: "requests", label: "Requests", color: "#5da8ff" }], {
    ariaLabel: "期間内のリクエスト数の推移",
    granularity: data.series_granularity,
    formatter: value => integer.format(value),
  });
  inputTokenChart(data.usage_series, data.series_granularity);
  lineChart("output-token-chart", data.usage_series, [{ key: "output_tokens", label: "Output", color: "#5da8ff" }], {
    ariaLabel: "Outputトークン数の推移",
    granularity: data.series_granularity,
    formatter: value => integer.format(value),
  });
  bars("model-breakdown", data.model_breakdown, "tokens", value => number.format(value));
  table(data.recent_usage);
  options("project_id", data.filters.projects);
  options("model", data.filters.models);
  options("api_key_id", data.filters.api_keys);
  syncStatus(data);
  document.querySelector("#usage-csv").href = `/api/export/completions.csv?${params()}`;
  document.querySelector("#cost-csv").href = `/api/export/costs.csv?${params()}`;
  document.querySelector("#cost-filter-note").hidden = !data.model_cost_unavailable;
  const costCardNote = document.querySelector("#cost-card-note");
  costCardNote.textContent = data.model_cost_unavailable ? "Modelフィルター対象外" : "期間内の実績額";
  costCardNote.classList.toggle("filter-excluded", data.model_cost_unavailable);
}

function configureCurrencies(data) {
  const currencies = [...new Set([
    ...data.summary.costs.map(row => row.currency),
    ...data.project_cost_series.map(row => row.currency),
  ])].sort();
  if (!currencies.includes(selectedCurrency)) selectedCurrency = currencies[0] || "";
  currencySelect.innerHTML = currencies.map(currency => `<option value="${escapeHtml(currency)}">${escapeHtml(currency.toUpperCase())}</option>`).join("");
  currencySelect.value = selectedCurrency;
  currencySelect.parentElement.hidden = currencies.length <= 1;
}

function renderCostViews(data) {
  const rows = data.project_cost_series.filter(row => row.currency === selectedCurrency);
  const activeProjects = activeCostProjectKeys(rows);
  const projectCount = activeProjects.size;
  const detail = document.querySelector("#cost-chart-detail");
  detail.textContent = projectCount > 8
    ? `${granularityLabels[data.series_granularity]}・上位8件＋その他`
    : `${granularityLabels[data.series_granularity]}・${projectCount}プロジェクト`;
  const selectedTotal = data.summary.costs.find(row => row.currency === selectedCurrency);
  document.querySelector("#cost-chart-total").textContent = selectedTotal
    ? formatCurrency(selectedTotal.amount, selectedCurrency) : "—";
  costChart(rows, selectedCurrency, data.series_granularity);
  bars(
    "project-breakdown",
    data.project_costs
      .filter(row => row.currency === selectedCurrency && Math.abs(Number(row.amount)) > 1e-8)
      .slice(0, 12),
    "amount",
    value => formatCurrency(value, selectedCurrency),
  );
}

function costChart(rows, currency, granularity) {
  if (!rows.length) { emptyChart("cost-chart"); return; }
  const totals = new Map();
  const names = new Map();
  rows.forEach(row => {
    const key = row.project_id || "__unclassified__";
    totals.set(key, (totals.get(key) || 0) + Number(row.amount));
    names.set(key, row.project_name);
  });
  const ranked = [...totals]
    .filter(([, total]) => Math.abs(total) > 1e-8)
    .sort((a, b) => b[1] - a[1]);
  if (!ranked.length) { emptyChart("cost-chart"); return; }
  const activeKeys = new Set(ranked.map(([key]) => key));
  const activeRows = rows.filter(row => activeKeys.has(row.project_id || "__unclassified__"));
  const timestamps = [...new Set(activeRows.map(row => row.bucket_start))].sort((a, b) => a - b);
  const visible = new Set(ranked.slice(0, 8).map(([key]) => key));
  const values = new Map();
  activeRows.forEach(row => {
    const projectKey = row.project_id || "__unclassified__";
    const key = visible.has(projectKey) ? projectKey : "__other__";
    const pointKey = `${key}:${row.bucket_start}`;
    values.set(pointKey, (values.get(pointKey) || 0) + Number(row.amount));
  });
  const keys = ranked.slice(0, 8).map(([key]) => key);
  if (ranked.length > 8) keys.push("__other__");
  const colors = projectColors(keys.filter(key => key !== "__other__"));
  const datasets = keys.map(key => ({
    label: key === "__other__" ? "その他" : names.get(key),
    data: timestamps.map(timestamp => values.get(`${key}:${timestamp}`) || 0),
    backgroundColor: key === "__other__" ? "#65717d" : colors.get(key),
    borderWidth: 0,
    borderRadius: 2,
    stack: "cost",
  }));
  const labels = timestamps.map(timestamp => dateLabel(timestamp, granularity));
  const fullLabels = timestamps.map(timestamp => fullDateLabel(timestamp, granularity));
  const canvas = chartCanvas("cost-chart", `プロジェクト別コスト推移、${currency.toUpperCase()}、${granularityLabels[granularity]}`);
  const chart = new Chart(canvas, {
    type: "bar",
    data: { labels, datasets },
    options: {
      ...baseChartOptions(),
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { stacked: true, grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 9 } },
        y: { stacked: true, beginAtZero: true, ticks: { callback: value => formatCurrency(value, currency, true) } },
      },
      plugins: {
        legend: {
          position: "bottom",
          onClick: () => {},
          labels: {
            usePointStyle: true,
            boxWidth: 8,
            generateLabels(chartInstance) {
              return Chart.defaults.plugins.legend.labels.generateLabels(chartInstance).map(item => {
                const total = chartInstance.data.datasets[item.datasetIndex].data.reduce((sum, value) => sum + value, 0);
                return { ...item, text: `${item.text} — ${formatCurrency(total, currency)}` };
              });
            },
          },
        },
        tooltip: {
          callbacks: {
            title: items => fullLabels[items[0].dataIndex],
            label(context) {
              const total = context.chart.data.datasets.reduce((sum, dataset) => sum + Number(dataset.data[context.dataIndex] || 0), 0);
              const percent = total ? ` (${(context.parsed.y / total * 100).toFixed(1)}%)` : "";
              return `${context.dataset.label}: ${formatCurrency(context.parsed.y, currency)}${percent}`;
            },
            footer: items => `合計: ${formatCurrency(items.reduce((sum, item) => sum + item.parsed.y, 0), currency)}`,
          },
        },
      },
    },
  });
  registerChart("cost-chart", chart);
  addKeyboardNavigation(chart, canvas, fullLabels, index => {
    const parts = datasets.map(dataset => `${dataset.label} ${formatCurrency(dataset.data[index], currency)}`);
    const total = datasets.reduce((sum, dataset) => sum + dataset.data[index], 0);
    return `${fullLabels[index]}、合計 ${formatCurrency(total, currency)}、${parts.join("、")}`;
  });
}

function lineChart(id, rows, series, settings) {
  if (!rows.length) { emptyChart(id); return; }
  const labels = rows.map(row => dateLabel(row.bucket_start, settings.granularity));
  const fullLabels = rows.map(row => fullDateLabel(row.bucket_start, settings.granularity));
  const datasets = series.map(item => ({
    label: item.label,
    data: rows.map(row => Number(row[item.key] || 0)),
    borderColor: item.color,
    backgroundColor: item.color,
    borderWidth: 2.3,
    pointRadius: 0,
    pointHoverRadius: 4,
    tension: 0.25,
  }));
  const canvas = chartCanvas(id, settings.ariaLabel);
  const chart = new Chart(canvas, {
    type: "line",
    data: { labels, datasets },
    options: {
      ...baseChartOptions(),
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 9 } },
        y: { beginAtZero: true, ticks: { callback: value => number.format(value) } },
      },
      plugins: {
        legend: { display: series.length > 1, position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } },
        tooltip: { callbacks: { title: items => fullLabels[items[0].dataIndex], label: context => `${context.dataset.label}: ${settings.formatter(context.parsed.y)}` } },
      },
    },
  });
  registerChart(id, chart);
  addKeyboardNavigation(chart, canvas, fullLabels, index => `${fullLabels[index]}、${datasets.map(dataset => `${dataset.label} ${settings.formatter(dataset.data[index])}`).join("、")}`);
}

function inputTokenChart(rows, granularity) {
  if (!rows.length) { emptyChart("input-token-chart"); return; }
  const labels = rows.map(row => dateLabel(row.bucket_start, granularity));
  const fullLabels = rows.map(row => fullDateLabel(row.bucket_start, granularity));
  const datasets = [
    { type: "bar", label: "Uncached input", key: "uncached_tokens", backgroundColor: "#35d49a", stack: "input", borderWidth: 0 },
    { type: "bar", label: "Cached input", key: "cached_tokens", backgroundColor: "#ffc765", stack: "input", borderWidth: 0 },
  ].map(dataset => ({ ...dataset, data: rows.map(row => Number(row[dataset.key] || 0)) }));
  const canvas = chartCanvas("input-token-chart", "CachedとUncachedのInputトークン内訳");
  const chart = new Chart(canvas, {
    type: "bar",
    data: { labels, datasets },
    options: {
      ...baseChartOptions(),
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { stacked: true, grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 12 } },
        y: { stacked: true, beginAtZero: true, ticks: { callback: value => number.format(value) } },
      },
      plugins: {
        legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } },
        tooltip: { callbacks: { title: items => fullLabels[items[0].dataIndex], label: context => `${context.dataset.label}: ${integer.format(context.parsed.y)}` } },
      },
    },
  });
  registerChart("input-token-chart", chart);
  addKeyboardNavigation(chart, canvas, fullLabels, index => `${fullLabels[index]}、${datasets.map(dataset => `${dataset.label} ${integer.format(dataset.data[index])}`).join("、")}`);
}

function baseChartOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 350 },
    layout: { padding: { top: 8 } },
  };
}

function chartCanvas(id, ariaLabel) {
  const node = document.getElementById(id);
  charts.get(id)?.destroy();
  charts.delete(id);
  node.innerHTML = "";
  const canvas = document.createElement("canvas");
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", `${ariaLabel}。左右の矢印キーで期間を移動できます。`);
  canvas.tabIndex = 0;
  const fallback = document.createElement("p");
  fallback.textContent = ariaLabel;
  canvas.append(fallback);
  const announcement = document.createElement("p");
  announcement.className = "sr-only";
  announcement.setAttribute("aria-live", "polite");
  node.append(canvas, announcement);
  canvas.chartAnnouncement = announcement;
  return canvas;
}

function registerChart(id, chart) { charts.set(id, chart); }

function emptyChart(id) {
  charts.get(id)?.destroy();
  charts.delete(id);
  document.getElementById(id).innerHTML = '<div class="empty">データがありません</div>';
}

function addKeyboardNavigation(chart, canvas, labels, describe) {
  let index = 0;
  const activate = () => {
    const active = chart.data.datasets.map((_, datasetIndex) => ({ datasetIndex, index }));
    chart.setActiveElements(active);
    chart.tooltip.setActiveElements(active, { x: chart.scales.x.getPixelForValue(index), y: chart.chartArea.top });
    canvas.chartAnnouncement.textContent = describe(index);
    chart.update();
  };
  canvas.addEventListener("keydown", event => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End", "Escape"].includes(event.key)) return;
    event.preventDefault();
    if (event.key === "Escape") {
      chart.setActiveElements([]);
      chart.tooltip.setActiveElements([], { x: 0, y: 0 });
      chart.update();
      return;
    }
    if (event.key === "Home") index = 0;
    else if (event.key === "End") index = labels.length - 1;
    else index = Math.max(0, Math.min(labels.length - 1, index + (event.key === "ArrowRight" ? 1 : -1)));
    activate();
  });
}

function activeCostProjectKeys(rows) {
  const totals = new Map();
  rows.forEach(row => {
    const key = row.project_id || "__unclassified__";
    totals.set(key, (totals.get(key) || 0) + Number(row.amount));
  });
  return new Set([...totals].filter(([, total]) => Math.abs(total) > 1e-8).map(([key]) => key));
}

function projectColors(projectIds) {
  const colors = new Map();
  const usedHues = [];
  [...projectIds].sort().forEach(projectId => {
    let hue = projectHue(projectId);
    while (usedHues.some(used => hueDistance(hue, used) < 28)) hue = (hue + 137.508) % 360;
    usedHues.push(hue);
    colors.set(projectId, `hsl(${hue.toFixed(1)} 72% 62%)`);
  });
  return colors;
}

function projectHue(projectId) {
  let hash = 0;
  for (const character of projectId) hash = ((hash << 5) - hash + character.charCodeAt(0)) | 0;
  return Math.abs(hash) % 360;
}

function hueDistance(first, second) { const distance = Math.abs(first - second); return Math.min(distance, 360 - distance); }

function bars(id, rows, key, formatter) {
  const node = document.getElementById(id);
  if (!rows.length) { node.innerHTML = '<div class="empty">データがありません</div>'; return; }
  const max = Math.max(...rows.map(row => Number(row[key])), 1);
  node.innerHTML = rows.map(row => `<div class="bar-row"><span class="bar-label" title="${escapeHtml(row.label)}">${escapeHtml(row.label)}</span><div class="bar-track"><div class="bar-fill" style="width:${Number(row[key]) / max * 100}%"></div></div><span class="bar-value">${formatter(row[key])}</span></div>`).join("");
}

function table(rows) {
  document.querySelector("#usage-table").innerHTML = rows.length ? rows.map(row => `<tr><td>${dateLabel(row.bucket_start)}</td><td title="${escapeHtml(row.project_id)}">${escapeHtml(row.project_name || "—")}</td><td>${escapeHtml(row.model || "—")}</td><td title="${escapeHtml(row.api_key_id)}">${escapeHtml(row.api_key_name || "—")}</td><td>${row.batch < 0 ? "—" : row.batch ? "Yes" : "No"}</td><td>${integer.format(row.num_model_requests)}</td><td>${integer.format(row.input_tokens)}</td><td>${integer.format(row.output_tokens)}</td><td>${integer.format(row.input_cached_tokens)}</td></tr>`).join("") : '<tr><td colspan="9" class="empty">データがありません</td></tr>';
}

function options(name, values) {
  const select = form.elements[name], selected = select.value;
  const entries = values.map(value => typeof value === "string" ? { value, label: value } : value);
  select.innerHTML = '<option value="">すべて</option>' + entries.map(entry => `<option value="${escapeHtml(entry.value)}">${escapeHtml(entry.label)}</option>`).join("");
  select.value = entries.some(entry => entry.value === selected) ? selected : "";
}

function syncStatus(data) {
  const latest = data.sync_status.find(row => row.endpoint === "completions") || data.sync_status[0];
  const indicator = document.querySelector("#sync-indicator");
  indicator.textContent = data.sync_running ? "同期中" : latest?.status === "success" ? "同期済み" : latest?.status === "failed" ? "同期失敗" : "未同期";
  document.querySelector("#sync-detail").textContent = latest?.finished_at ? `最終同期: ${new Date(latest.finished_at * 1000).toLocaleString("ja-JP")}` : "APIキー未設定時は同期されません。";
}

function escapeHtml(value) { const node = document.createElement("span"); node.textContent = String(value); return node.innerHTML; }

form.addEventListener("submit", event => { event.preventDefault(); loadDashboard(); });
currencySelect.addEventListener("change", () => { selectedCurrency = currencySelect.value; if (currentData) renderCostViews(currentData); });
document.querySelector("#sync-button").addEventListener("click", async () => {
  showMessage("");
  const response = await fetch("/api/sync", { method: "POST" });
  const body = await response.json();
  if (!response.ok) showMessage(body.detail || "同期を開始できませんでした。");
  else { showMessage("同期を開始しました。"); setTimeout(loadDashboard, 1200); }
});
loadDashboard();
