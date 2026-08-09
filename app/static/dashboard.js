const form = document.querySelector("#filters");
const message = document.querySelector("#message");
const number = new Intl.NumberFormat("ja-JP", { notation: "compact", maximumFractionDigits: 1 });
const integer = new Intl.NumberFormat("ja-JP");

function params() { return new URLSearchParams(new FormData(form)); }
function showMessage(text) { message.textContent = text; message.hidden = !text; }
function dateLabel(timestamp) { return new Date(timestamp * 1000).toLocaleDateString("ja-JP", { month: "numeric", day: "numeric", timeZone: "UTC" }); }

async function loadDashboard() {
  showMessage("");
  try {
    const response = await fetch(`/api/dashboard?${params()}`);
    if (!response.ok) throw new Error((await response.json()).detail || "データを取得できませんでした。");
    const data = await response.json();
    render(data);
  } catch (error) { showMessage(error.message); }
}

function render(data) {
  const usage = data.summary.usage;
  document.querySelector("#requests-total").textContent = integer.format(usage.requests);
  document.querySelector("#input-total").textContent = number.format(usage.input_tokens);
  document.querySelector("#output-total").textContent = number.format(usage.output_tokens);
  document.querySelector("#cache-rate").textContent = `${(usage.cache_rate * 100).toFixed(1)}%`;
  document.querySelector("#cost-total").textContent = data.summary.costs.length
    ? data.summary.costs.map(c => `${c.currency.toUpperCase()} ${Number(c.amount).toFixed(2)}`).join(" / ") : "—";

  const currency = data.cost_series[0]?.currency || "";
  const costRows = data.cost_series.filter(row => row.currency === currency);
  document.querySelector("#cost-currency").textContent = currency.toUpperCase();
  lineChart("cost-chart", costRows, [{ key: "amount", className: "line" }]);
  lineChart("request-chart", data.usage_series, [{ key: "requests", className: "line blue" }]);
  lineChart("token-chart", data.usage_series, [
    { key: "input_tokens", className: "line" },
    { key: "output_tokens", className: "line blue" },
    { key: "cached_tokens", className: "line amber" },
  ]);
  bars("model-breakdown", data.model_breakdown, "tokens", value => number.format(value));
  bars("project-breakdown", data.project_costs.filter(x => x.currency === currency), "amount", value => `${currency.toUpperCase()} ${Number(value).toFixed(2)}`);
  table(data.recent_usage);
  options("project_id", data.filters.projects);
  options("model", data.filters.models);
  options("api_key_id", data.filters.api_keys);
  syncStatus(data);
  document.querySelector("#usage-csv").href = `/api/export/completions.csv?${params()}`;
  document.querySelector("#cost-csv").href = `/api/export/costs.csv?${params()}`;
  if (data.model_cost_unavailable) showMessage("モデル指定はUsageだけに適用されます。Costs APIはモデルで絞り込めません。");
}

function lineChart(id, rows, series) {
  const node = document.getElementById(id);
  if (!rows.length) { node.innerHTML = '<div class="empty">データがありません</div>'; return; }
  const width = 800, height = 220, left = 48, right = 12, top = 14, bottom = 28;
  const values = rows.flatMap(row => series.map(item => Number(row[item.key] || 0)));
  const max = Math.max(...values, 1);
  const x = index => left + index * (width - left - right) / Math.max(rows.length - 1, 1);
  const y = value => top + (height - top - bottom) * (1 - Number(value) / max);
  const lines = [0, .5, 1].map(ratio => `<line class="grid" x1="${left}" y1="${y(max * ratio)}" x2="${width-right}" y2="${y(max * ratio)}"/><text x="0" y="${y(max * ratio)+4}">${number.format(max * ratio)}</text>`).join("");
  const paths = series.map(item => `<polyline class="${item.className}" points="${rows.map((row, i) => `${x(i)},${y(row[item.key])}`).join(" ")}"/>`).join("");
  const labels = rows.filter((_, i) => i === 0 || i === rows.length - 1 || i === Math.floor(rows.length / 2)).map(row => { const i = rows.indexOf(row); return `<text x="${x(i)}" y="${height-5}" text-anchor="middle">${dateLabel(row.bucket_start)}</text>`; }).join("");
  node.innerHTML = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">${lines}${paths}${labels}</svg>`;
}

function bars(id, rows, key, formatter) {
  const node = document.getElementById(id);
  if (!rows.length) { node.innerHTML = '<div class="empty">データがありません</div>'; return; }
  const max = Math.max(...rows.map(row => Number(row[key])), 1);
  node.innerHTML = rows.map(row => `<div class="bar-row"><span class="bar-label" title="${escapeHtml(row.label)}">${escapeHtml(row.label)}</span><div class="bar-track"><div class="bar-fill" style="width:${Number(row[key]) / max * 100}%"></div></div><span class="bar-value">${formatter(row[key])}</span></div>`).join("");
}

function table(rows) {
  document.querySelector("#usage-table").innerHTML = rows.length ? rows.map(row => `<tr><td>${dateLabel(row.bucket_start)}</td><td>${escapeHtml(row.project_id || "—")}</td><td>${escapeHtml(row.model || "—")}</td><td>${escapeHtml(row.api_key_id || "—")}</td><td>${row.batch < 0 ? "—" : row.batch ? "Yes" : "No"}</td><td>${integer.format(row.num_model_requests)}</td><td>${integer.format(row.input_tokens)}</td><td>${integer.format(row.output_tokens)}</td><td>${integer.format(row.input_cached_tokens)}</td></tr>`).join("") : '<tr><td colspan="9" class="empty">データがありません</td></tr>';
}

function options(name, values) {
  const select = form.elements[name], selected = select.value;
  select.innerHTML = '<option value="">すべて</option>' + values.map(value => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("");
  select.value = values.includes(selected) ? selected : "";
}

function syncStatus(data) {
  const latest = data.sync_status.find(row => row.endpoint === "completions") || data.sync_status[0];
  const indicator = document.querySelector("#sync-indicator");
  indicator.textContent = data.sync_running ? "同期中" : latest?.status === "success" ? "同期済み" : latest?.status === "failed" ? "同期失敗" : "未同期";
  document.querySelector("#sync-detail").textContent = latest?.finished_at ? `最終同期: ${new Date(latest.finished_at * 1000).toLocaleString("ja-JP")}` : "APIキー未設定時は同期されません。";
}

function escapeHtml(value) { const node = document.createElement("span"); node.textContent = String(value); return node.innerHTML; }

form.addEventListener("submit", event => { event.preventDefault(); loadDashboard(); });
document.querySelector("#sync-button").addEventListener("click", async () => {
  showMessage("");
  const response = await fetch("/api/sync", { method: "POST" });
  const body = await response.json();
  if (!response.ok) showMessage(body.detail || "同期を開始できませんでした。");
  else { showMessage("同期を開始しました。"); setTimeout(loadDashboard, 1200); }
});
loadDashboard();

