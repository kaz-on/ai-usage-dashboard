// @ts-check

/**
 * @template {Element} T
 * @param {string} selector
 * @param {new (...args: any[]) => T} constructor
 * @returns {T}
 */
function requiredElement(selector, constructor) {
  const element = document.querySelector(selector);
  if (!(element instanceof constructor)) throw new Error(`Required element not found: ${selector}`);
  return element;
}

const form = requiredElement("#filters", HTMLFormElement);
const dashboard = requiredElement("#dashboard", HTMLElement);
const message = requiredElement("#message", HTMLParagraphElement);
const submitButton = requiredElement("#filter-submit", HTMLButtonElement);
const currencySelect = requiredElement("#cost-currency", HTMLSelectElement);
const number = new Intl.NumberFormat("ja-JP", { notation: "compact", maximumFractionDigits: 1 });
const integer = new Intl.NumberFormat("ja-JP");
/** @type {Map<string, BarChart>} */
const charts = new Map();
/** @type {Record<Granularity, string>} */
const granularityLabels = { day: "日次", week: "週次", month: "月次" };
/** @type {DashboardData | null} */
let currentData = null;
let selectedCurrency = "";

Chart.defaults.color = "#8f9ba7";
Chart.defaults.borderColor = "#29313a";
Chart.defaults.font.family = "system-ui, sans-serif";

function params() {
  const searchParams = new URLSearchParams();
  new FormData(form).forEach((value, key) => searchParams.append(key, String(value)));
  return searchParams;
}
/** @param {string} text */
function showMessage(text) { message.textContent = text; message.hidden = !text; }
/** @param {boolean} loading */
function setLoading(loading) {
  dashboard.classList.toggle("is-loading", loading);
  dashboard.setAttribute("aria-busy", String(loading));
  submitButton.disabled = loading;
  submitButton.textContent = loading ? "更新中…" : "更新";
}
/** @param {number} timestamp @param {Granularity} [granularity] */
function dateLabel(timestamp, granularity = "day") {
  const date = new Date(timestamp * 1000);
  if (granularity === "month") return date.toLocaleDateString("ja-JP", { year: "numeric", month: "short", timeZone: "UTC" });
  const label = date.toLocaleDateString("ja-JP", { month: "numeric", day: "numeric", timeZone: "UTC" });
  return granularity === "week" ? `${label}週` : label;
}
/** @param {number} timestamp @param {Granularity} [granularity] */
function fullDateLabel(timestamp, granularity = "day") {
  const date = new Date(timestamp * 1000);
  if (granularity === "month") return date.toLocaleDateString("ja-JP", { year: "numeric", month: "long", timeZone: "UTC" });
  const label = date.toLocaleDateString("ja-JP", { year: "numeric", month: "long", day: "numeric", timeZone: "UTC" });
  return granularity === "week" ? `${label}からの週` : label;
}
/** @param {number | string} value @param {string} currency @param {boolean} [compact] */
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
    if (!response.ok) {
      const body = /** @type {ApiErrorResponse} */ (await response.json());
      throw new Error(body.detail || "データを取得できませんでした。");
    }
    currentData = /** @type {DashboardData} */ (await response.json());
    render(currentData);
  } catch (error) {
    showMessage(error instanceof Error ? error.message : "予期しないエラーが発生しました。");
  } finally {
    setLoading(false);
  }
}

/** @param {DashboardData} data */
function render(data) {
  const usage = data.summary.usage;
  requiredElement("#requests-total", HTMLElement).textContent = integer.format(usage.requests);
  requiredElement("#input-total", HTMLElement).textContent = number.format(usage.input_tokens);
  requiredElement("#output-total", HTMLElement).textContent = number.format(usage.output_tokens);
  requiredElement("#cache-rate", HTMLElement).textContent = `${(usage.cache_rate * 100).toFixed(1)}%`;
  requiredElement("#cost-total", HTMLElement).textContent = data.summary.costs.length
    ? data.summary.costs.map(row => formatCurrency(row.amount, row.currency)).join(" / ") : "—";

  configureCurrencies(data);
  renderCostViews(data);
  projectRequestChart(data.project_request_series, data.series_granularity);
  inputTokenChart(data.usage_series, data.series_granularity);
  barChart("output-token-chart", data.usage_series, { key: "output_tokens", label: "Output", color: "#5da8ff" }, {
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
  requiredElement("#usage-csv", HTMLAnchorElement).href = `/api/export/completions.csv?${params()}`;
  requiredElement("#cost-csv", HTMLAnchorElement).href = `/api/export/costs.csv?${params()}`;
  requiredElement("#cost-filter-note", HTMLElement).hidden = !data.model_cost_unavailable;
  const costCardNote = requiredElement("#cost-card-note", HTMLElement);
  costCardNote.textContent = data.model_cost_unavailable ? "Modelフィルター対象外" : "期間内の実績額";
  costCardNote.classList.toggle("filter-excluded", data.model_cost_unavailable);
}

/** @param {DashboardData} data */
function configureCurrencies(data) {
  const currencies = [...new Set([
    ...data.summary.costs.map(row => row.currency),
    ...data.project_cost_series.map(row => row.currency),
  ])].sort();
  if (!currencies.includes(selectedCurrency)) selectedCurrency = currencies[0] || "";
  currencySelect.innerHTML = currencies.map(currency => `<option value="${escapeHtml(currency)}">${escapeHtml(currency.toUpperCase())}</option>`).join("");
  currencySelect.value = selectedCurrency;
  if (currencySelect.parentElement) currencySelect.parentElement.hidden = currencies.length <= 1;
}

/** @param {DashboardData} data */
function renderCostViews(data) {
  const rows = data.project_cost_series.filter(row => row.currency === selectedCurrency);
  const projectCount = new Set(rows.map(row => row.project_id || "__unclassified__")).size;
  const detail = requiredElement("#cost-chart-detail", HTMLElement);
  detail.textContent = projectCount > 8
    ? `${granularityLabels[data.series_granularity]}・上位8件＋その他`
    : `${granularityLabels[data.series_granularity]}・${projectCount}プロジェクト`;
  const selectedTotal = data.summary.costs.find(row => row.currency === selectedCurrency);
  requiredElement("#cost-chart-total", HTMLElement).textContent = selectedTotal
    ? formatCurrency(selectedTotal.amount, selectedCurrency) : "—";
  costChart(rows, selectedCurrency, data.series_granularity);
  costShareBars(
    data.project_costs.filter(row => row.currency === selectedCurrency).slice(0, 12),
    selectedCurrency,
    selectedTotal?.amount || 0,
  );
}

/**
 * @param {HTMLCanvasElement} canvas
 * @param {import("chart.js").ChartConfiguration<"bar", number[], string>} configuration
 * @returns {BarChart}
 */
function createBarChart(canvas, configuration) {
  return new Chart(canvas, configuration);
}

/** @param {ProjectCostRow[]} rows @param {string} currency @param {Granularity} granularity */
function costChart(rows, currency, granularity) {
  if (!rows.length) { emptyChart("cost-chart"); return; }
  const { timestamps, keys, names, values, colors } = groupProjectRows(rows, "amount");
  /** @type {BarDataset[]} */
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
  const chart = createBarChart(canvas, {
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
                if (item.datasetIndex === undefined) return item;
                const total = chartInstance.data.datasets[item.datasetIndex].data.reduce((sum, value) => Number(sum) + Number(value), 0);
                return { ...item, text: `${item.text} — ${formatCurrency(Number(total), currency)}` };
              });
            },
          },
        },
        tooltip: {
          callbacks: {
            title: items => fullLabels[items[0].dataIndex],
            label(context) {
              const total = context.chart.data.datasets.reduce((sum, dataset) => sum + Number(dataset.data[context.dataIndex] || 0), 0);
              const value = Number(context.parsed.y);
              const percent = total ? ` (${(value / total * 100).toFixed(1)}%)` : "";
              return `${context.dataset.label}: ${formatCurrency(value, currency)}${percent}`;
            },
            footer: items => `合計: ${formatCurrency(items.reduce((sum, item) => sum + Number(item.parsed.y), 0), currency)}`,
          },
        },
      },
    },
  });
  registerChart("cost-chart", chart);
  addKeyboardNavigation(chart, canvas, fullLabels, index => {
    const parts = datasets.map(dataset => `${dataset.label} ${formatCurrency(Number(dataset.data[index]), currency)}`);
    const total = datasets.reduce((sum, dataset) => sum + Number(dataset.data[index]), 0);
    return `${fullLabels[index]}、合計 ${formatCurrency(total, currency)}、${parts.join("、")}`;
  });
}

/** @param {ProjectRequestRow[]} rows @param {Granularity} granularity */
function projectRequestChart(rows, granularity) {
  if (!rows.length) { emptyChart("request-chart"); return; }
  const { timestamps, keys, names, values, colors, ranked } = groupProjectRows(rows, "requests");
  const detail = requiredElement("#request-chart-detail", HTMLElement);
  detail.textContent = ranked.length > 8
    ? `${granularityLabels[granularity]}・上位8件＋その他`
    : `${granularityLabels[granularity]}・${ranked.length}プロジェクト`;
  /** @type {BarDataset[]} */
  const datasets = keys.map(key => ({
    label: key === "__other__" ? "その他" : names.get(key),
    data: timestamps.map(timestamp => values.get(`${key}:${timestamp}`) || 0),
    backgroundColor: key === "__other__" ? "#65717d" : colors.get(key),
    borderWidth: 0,
    borderRadius: 2,
    stack: "requests",
  }));
  const labels = timestamps.map(timestamp => dateLabel(timestamp, granularity));
  const fullLabels = timestamps.map(timestamp => fullDateLabel(timestamp, granularity));
  const canvas = chartCanvas("request-chart", `プロジェクト別リクエスト推移、${granularityLabels[granularity]}`);
  const chart = createBarChart(canvas, {
    type: "bar",
    data: { labels, datasets },
    options: {
      ...baseChartOptions(),
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { stacked: true, grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 9 } },
        y: { stacked: true, beginAtZero: true, ticks: { callback: value => number.format(Number(value)) } },
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
                if (item.datasetIndex === undefined) return item;
                const total = chartInstance.data.datasets[item.datasetIndex].data.reduce((sum, value) => Number(sum) + Number(value), 0);
                return { ...item, text: `${item.text} — ${integer.format(Number(total))}` };
              });
            },
          },
        },
        tooltip: {
          callbacks: {
            title: items => fullLabels[items[0].dataIndex],
            label(context) {
              const total = context.chart.data.datasets.reduce((sum, dataset) => sum + Number(dataset.data[context.dataIndex] || 0), 0);
              const value = Number(context.parsed.y);
              const percent = total ? ` (${(value / total * 100).toFixed(1)}%)` : "";
              return `${context.dataset.label}: ${integer.format(value)}${percent}`;
            },
            footer: items => `合計: ${integer.format(items.reduce((sum, item) => sum + Number(item.parsed.y), 0))}`,
          },
        },
      },
    },
  });
  registerChart("request-chart", chart);
  addKeyboardNavigation(chart, canvas, fullLabels, index => {
    const parts = datasets.map(dataset => `${dataset.label} ${integer.format(Number(dataset.data[index]))}`);
    const total = datasets.reduce((sum, dataset) => sum + Number(dataset.data[index]), 0);
    return `${fullLabels[index]}、合計 ${integer.format(total)}、${parts.join("、")}`;
  });
}

/**
 * @param {string} id
 * @param {UsageSeriesRow[]} rows
 * @param {BarSeries} series
 * @param {BarChartSettings} settings
 */
function barChart(id, rows, series, settings) {
  if (!rows.length) { emptyChart(id); return; }
  const labels = rows.map(row => dateLabel(row.bucket_start, settings.granularity));
  const fullLabels = rows.map(row => fullDateLabel(row.bucket_start, settings.granularity));
  const dataset = {
    label: series.label,
    data: rows.map(row => Number(row[series.key] || 0)),
    backgroundColor: series.color,
    borderWidth: 0,
    borderRadius: 2,
  };
  const canvas = chartCanvas(id, settings.ariaLabel);
  const chart = createBarChart(canvas, {
    type: "bar",
    data: { labels, datasets: [dataset] },
    options: {
      ...baseChartOptions(),
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 9 } },
        y: { beginAtZero: true, ticks: { callback: value => number.format(Number(value)) } },
      },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { title: items => fullLabels[items[0].dataIndex], label: context => `${context.dataset.label}: ${settings.formatter(Number(context.parsed.y))}` } },
      },
    },
  });
  registerChart(id, chart);
  addKeyboardNavigation(chart, canvas, fullLabels, index => `${fullLabels[index]}、${dataset.label} ${settings.formatter(dataset.data[index])}`);
}

/** @param {UsageSeriesRow[]} rows @param {Granularity} granularity */
function inputTokenChart(rows, granularity) {
  if (!rows.length) { emptyChart("input-token-chart"); return; }
  const labels = rows.map(row => dateLabel(row.bucket_start, granularity));
  const fullLabels = rows.map(row => fullDateLabel(row.bucket_start, granularity));
  /** @type {InputDatasetDefinition[]} */
  const datasetDefinitions = [
    { label: "Uncached input", key: "uncached_tokens", backgroundColor: "#35d49a", stack: "input", borderWidth: 0 },
    { label: "Cached input", key: "cached_tokens", backgroundColor: "#ffc765", stack: "input", borderWidth: 0 },
  ];
  const datasets = datasetDefinitions.map(dataset => ({
    ...dataset,
    data: rows.map(row => Number(row[dataset.key] || 0)),
  }));
  const canvas = chartCanvas("input-token-chart", "CachedとUncachedのInputトークン内訳");
  const chart = createBarChart(canvas, {
    type: "bar",
    data: { labels, datasets },
    options: {
      ...baseChartOptions(),
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { stacked: true, grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 12 } },
        y: { stacked: true, beginAtZero: true, ticks: { callback: value => number.format(Number(value)) } },
      },
      plugins: {
        legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } },
        tooltip: { callbacks: { title: items => fullLabels[items[0].dataIndex], label: context => `${context.dataset.label}: ${integer.format(Number(context.parsed.y))}` } },
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

/** @param {string} id @param {string} ariaLabel @returns {DashboardCanvas} */
function chartCanvas(id, ariaLabel) {
  const node = requiredElement(`#${id}`, HTMLElement);
  charts.get(id)?.destroy();
  charts.delete(id);
  node.innerHTML = "";
  const announcement = document.createElement("p");
  const canvas = Object.assign(document.createElement("canvas"), { chartAnnouncement: announcement });
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", `${ariaLabel}。左右の矢印キーで期間を移動できます。`);
  canvas.tabIndex = 0;
  const fallback = document.createElement("p");
  fallback.textContent = ariaLabel;
  canvas.append(fallback);
  announcement.className = "sr-only";
  announcement.setAttribute("aria-live", "polite");
  node.append(canvas, announcement);
  canvas.chartAnnouncement = announcement;
  return canvas;
}

/** @param {string} id @param {BarChart} chart */
function registerChart(id, chart) { charts.set(id, chart); }

/** @param {string} id */
function emptyChart(id) {
  charts.get(id)?.destroy();
  charts.delete(id);
  requiredElement(`#${id}`, HTMLElement).innerHTML = '<div class="empty">データがありません</div>';
}

/**
 * @param {BarChart} chart
 * @param {DashboardCanvas} canvas
 * @param {string[]} labels
 * @param {(index: number) => string} describe
 */
function addKeyboardNavigation(chart, canvas, labels, describe) {
  let index = 0;
  const activate = () => {
    const active = chart.data.datasets.map((_, datasetIndex) => ({ datasetIndex, index }));
    chart.setActiveElements(active);
    chart.tooltip?.setActiveElements(active, { x: chart.scales.x.getPixelForValue(index), y: chart.chartArea.top });
    canvas.chartAnnouncement.textContent = describe(index);
    chart.update();
  };
  canvas.addEventListener("keydown", event => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End", "Escape"].includes(event.key)) return;
    event.preventDefault();
    if (event.key === "Escape") {
      chart.setActiveElements([]);
      chart.tooltip?.setActiveElements([], { x: 0, y: 0 });
      chart.update();
      return;
    }
    if (event.key === "Home") index = 0;
    else if (event.key === "End") index = labels.length - 1;
    else index = Math.max(0, Math.min(labels.length - 1, index + (event.key === "ArrowRight" ? 1 : -1)));
    activate();
  });
}

/**
 * @param {Array<ProjectCostRow | ProjectRequestRow>} rows
 * @param {"amount" | "requests"} valueKey
 * @returns {GroupedProjectRows}
 */
function groupProjectRows(rows, valueKey) {
  const timestamps = [...new Set(rows.map(row => row.bucket_start))].sort((a, b) => a - b);
  /** @type {Map<string, number>} */
  const totals = new Map();
  /** @type {Map<string, string>} */
  const names = new Map();
  rows.forEach(row => {
    const key = row.project_id || "__unclassified__";
    const value = valueKey === "amount"
      ? /** @type {ProjectCostRow} */ (row).amount
      : /** @type {ProjectRequestRow} */ (row).requests;
    totals.set(key, (totals.get(key) || 0) + value);
    names.set(key, row.project_name);
  });
  const ranked = [...totals].sort((a, b) => b[1] - a[1]);
  const visible = new Set(ranked.slice(0, 8).map(([key]) => key));
  /** @type {Map<string, number>} */
  const values = new Map();
  rows.forEach(row => {
    const projectKey = row.project_id || "__unclassified__";
    const key = visible.has(projectKey) ? projectKey : "__other__";
    const pointKey = `${key}:${row.bucket_start}`;
    const value = valueKey === "amount"
      ? /** @type {ProjectCostRow} */ (row).amount
      : /** @type {ProjectRequestRow} */ (row).requests;
    values.set(pointKey, (values.get(pointKey) || 0) + value);
  });
  const keys = ranked.slice(0, 8).map(([key]) => key);
  if (ranked.length > 8) keys.push("__other__");
  return {
    timestamps,
    keys,
    names,
    values,
    ranked,
    colors: projectColors(keys.filter(key => key !== "__other__")),
  };
}

/** @param {string[]} projectIds @returns {Map<string, string>} */
function projectColors(projectIds) {
  /** @type {Map<string, string>} */
  const colors = new Map();
  /** @type {number[]} */
  const usedHues = [];
  [...projectIds].sort().forEach(projectId => {
    let hue = projectHue(projectId);
    while (usedHues.some(used => hueDistance(hue, used) < 28)) hue = (hue + 137.508) % 360;
    usedHues.push(hue);
    colors.set(projectId, `hsl(${hue.toFixed(1)} 72% 62%)`);
  });
  return colors;
}

/** @param {string} projectId */
function projectHue(projectId) {
  let hash = 0;
  for (const character of projectId) hash = ((hash << 5) - hash + character.charCodeAt(0)) | 0;
  return Math.abs(hash) % 360;
}

/** @param {number} first @param {number} second */
function hueDistance(first, second) { const distance = Math.abs(first - second); return Math.min(distance, 360 - distance); }

/**
 * @param {string} id
 * @param {ModelBreakdownRow[]} rows
 * @param {"tokens"} key
 * @param {(value: number) => string} formatter
 */
function bars(id, rows, key, formatter) {
  const node = requiredElement(`#${id}`, HTMLElement);
  if (!rows.length) { node.innerHTML = '<div class="empty">データがありません</div>'; return; }
  const max = Math.max(...rows.map(row => Number(row[key])), 1);
  node.innerHTML = rows.map(row => `<div class="bar-row"><span class="bar-label" title="${escapeHtml(row.label)}">${escapeHtml(row.label)}</span><div class="bar-track"><div class="bar-fill" style="width:${Number(row[key]) / max * 100}%"></div></div><span class="bar-value">${formatter(row[key])}</span></div>`).join("");
}

/** @param {ProjectCostTotal[]} rows @param {string} currency @param {number} total */
function costShareBars(rows, currency, total) {
  const node = requiredElement("#project-breakdown", HTMLElement);
  if (!rows.length || !total) { node.innerHTML = '<div class="empty">データがありません</div>'; return; }
  node.innerHTML = rows.map(row => {
    const amount = row.amount;
    const share = amount / total * 100;
    const width = Math.max(0, Math.min(100, share));
    return `<div class="bar-row"><span class="bar-label" title="${escapeHtml(row.label)}">${escapeHtml(row.label)}</span><div class="bar-track"><div class="bar-fill" style="width:${width}%"></div></div><span class="bar-value share-value"><span>${escapeHtml(formatCurrency(amount, currency))}</span><small>${share.toFixed(1)}%</small></span></div>`;
  }).join("");
}

/** @param {RecentUsageRow[]} rows */
function table(rows) {
  requiredElement("#usage-table", HTMLTableSectionElement).innerHTML = rows.length ? rows.map(row => `<tr><td>${dateLabel(row.bucket_start)}</td><td title="${escapeHtml(row.project_id)}">${escapeHtml(row.project_name || "—")}</td><td>${escapeHtml(row.model || "—")}</td><td title="${escapeHtml(row.api_key_id)}">${escapeHtml(row.api_key_name || "—")}</td><td>${row.batch < 0 ? "—" : row.batch ? "Yes" : "No"}</td><td>${integer.format(row.num_model_requests)}</td><td>${integer.format(row.input_tokens)}</td><td>${integer.format(row.output_tokens)}</td><td>${integer.format(row.input_cached_tokens)}</td></tr>`).join("") : '<tr><td colspan="9" class="empty">データがありません</td></tr>';
}

/** @param {"project_id" | "model" | "api_key_id"} name @param {Array<string | FilterOption>} values */
function options(name, values) {
  const select = requiredElement(`[name="${name}"]`, HTMLSelectElement);
  const selected = select.value;
  const entries = values.map(value => typeof value === "string" ? { value, label: value } : value);
  select.innerHTML = '<option value="">すべて</option>' + entries.map(entry => `<option value="${escapeHtml(entry.value)}">${escapeHtml(entry.label)}</option>`).join("");
  select.value = entries.some(entry => entry.value === selected) ? selected : "";
}

/** @param {DashboardData} data */
function syncStatus(data) {
  const latest = data.sync_status.find(row => row.endpoint === "completions") || data.sync_status[0];
  const indicator = requiredElement("#sync-indicator", HTMLElement);
  indicator.textContent = data.sync_running ? "同期中" : latest?.status === "success" ? "同期済み" : latest?.status === "failed" ? "同期失敗" : "未同期";
  requiredElement("#sync-detail", HTMLElement).textContent = latest?.finished_at ? `最終同期: ${new Date(latest.finished_at * 1000).toLocaleString("ja-JP")}` : "APIキー未設定時は同期されません。";
}

/** @param {unknown} value */
function escapeHtml(value) { const node = document.createElement("span"); node.textContent = String(value); return node.innerHTML; }

form.addEventListener("submit", event => { event.preventDefault(); loadDashboard(); });
currencySelect.addEventListener("change", () => { selectedCurrency = currencySelect.value; if (currentData) renderCostViews(currentData); });
requiredElement("#sync-button", HTMLButtonElement).addEventListener("click", async () => {
  showMessage("");
  const response = await fetch("/api/sync", { method: "POST" });
  const body = /** @type {SyncResponse} */ (await response.json());
  if (!response.ok) showMessage(body.detail || "同期を開始できませんでした。");
  else { showMessage("同期を開始しました。"); setTimeout(loadDashboard, 1200); }
});
loadDashboard();
