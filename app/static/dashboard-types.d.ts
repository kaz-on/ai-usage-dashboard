type Granularity = "day" | "week" | "month";
type SyncRunStatus = "running" | "success" | "failed";

interface UsageSummary {
  requests: number;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  uncached_tokens: number;
  cache_rate: number;
  tokens_per_request: number;
}

interface CostSummary {
  currency: string;
  amount: string;
}

interface UsageSeriesRow {
  bucket_start: number;
  requests: number;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  uncached_tokens: number;
}

interface ProjectRequestRow {
  bucket_start: number;
  project_id: string;
  project_name: string;
  requests: number;
}

interface CostSeriesRow {
  bucket_start: number;
  currency: string;
  amount: string;
}

interface ProjectCostRow extends CostSeriesRow {
  project_id: string;
  project_name: string;
}

interface ModelBreakdownRow {
  label: string;
  requests: number;
  tokens: number;
}

interface ProjectCostTotal {
  label: string;
  project_id: string;
  currency: string;
  amount: string;
}

interface RecentUsageRow {
  bucket_start: number;
  project_id: string;
  project_name: string;
  model: string;
  api_key_id: string;
  api_key_name: string;
  batch: number;
  service_tier: string;
  num_model_requests: number;
  input_tokens: number;
  output_tokens: number;
  input_cached_tokens: number;
}

interface FilterOption {
  value: string;
  label: string;
}

interface DashboardFilters {
  projects: FilterOption[];
  models: string[];
  api_keys: FilterOption[];
}

interface SyncStatus {
  endpoint: string;
  status: SyncRunStatus;
  started_at: number;
  finished_at: number | null;
  record_count: number;
  error_message: string | null;
}

interface DashboardData {
  summary: {
    usage: UsageSummary;
    costs: CostSummary[];
  };
  usage_series: UsageSeriesRow[];
  project_request_series: ProjectRequestRow[];
  cost_series: CostSeriesRow[];
  project_cost_series: ProjectCostRow[];
  series_granularity: Granularity;
  model_breakdown: ModelBreakdownRow[];
  project_costs: ProjectCostTotal[];
  recent_usage: RecentUsageRow[];
  sync_status: SyncStatus[];
  model_cost_unavailable: boolean;
  filters: DashboardFilters;
  sync_running: boolean;
}

interface ApiErrorResponse {
  detail?: string;
}

interface SyncResponse extends ApiErrorResponse {
  status?: "started" | "already_running";
}

type DashboardCanvas = HTMLCanvasElement & {
  chartAnnouncement: HTMLParagraphElement;
};

type BarChart = import("chart.js").Chart<"bar", number[], string>;
type BarDataset = import("chart.js").ChartDataset<"bar", number[]>;

interface BarSeries {
  key: "output_tokens";
  label: string;
  color: string;
}

interface BarChartSettings {
  ariaLabel: string;
  granularity: Granularity;
  formatter: (value: number) => string;
}

interface InputDatasetDefinition {
  key: "uncached_tokens" | "cached_tokens";
  label: string;
  backgroundColor: string;
  stack: string;
  borderWidth: number;
}

interface GroupedProjectRows {
  timestamps: number[];
  keys: string[];
  names: Map<string, string>;
  values: Map<string, number>;
  ranked: Array<[string, number]>;
  colors: Map<string, string>;
}

declare const Chart: typeof import("chart.js/auto").default;
