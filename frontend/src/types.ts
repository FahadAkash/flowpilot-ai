export interface DocumentItem {
  id: string;
  filename: string;
  content_type: string;
  sha256: string;
  doc_type: string;
  page_count: number;
  size_bytes: number;
  status: string;
  chunk_count: number;
  created_at: string;
  metadata_json: Record<string, unknown>;
}

export interface DiscrepancyItem {
  code: string;
  category: string;
  severity: "low" | "medium" | "high" | "critical";
  field: string;
  expected: string;
  actual: string;
  potential_concern: string;
  citation: string;
  requires_frontier_reasoning: boolean;
}

export interface WorkflowStep {
  id: string;
  step_index: number;
  node_name: string;
  agent_name: string;
  tier: number;
  status: string;
  routing_reason: string;
  input_summary_json: Record<string, unknown>;
  output_summary_json: Record<string, unknown>;
  confidence: number | null;
  latency_ms: number;
  tokens_used: number;
  cost_usd: number;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface ModelInvocation {
  id: string;
  workflow_step_id: string | null;
  agent_name: string;
  model_key: string;
  provider: string;
  tier: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  latency_ms: number;
  raw_confidence: number | null;
  calibrated_confidence: number | null;
  cache_hit: boolean;
  status: string;
  error_code: string | null;
  created_at: string;
}

export interface ToolInvocation {
  id: string;
  workflow_step_id: string | null;
  agent_name: string;
  tool_name: string;
  arguments_json: Record<string, unknown>;
  result_summary_json: Record<string, unknown>;
  latency_ms: number;
  status: string;
  error_message: string | null;
  created_at: string;
}

export interface WorkflowResponseBody {
  summary?: string;
  intent?: string;
  selected_tier?: number;
  final_tier?: number;
  routing_rationale?: string;
  extracted_fields?: Record<string, unknown>;
  extracted_records?: Record<string, unknown>[];
  discrepancies?: DiscrepancyItem[];
  frontier_reasoning?: {
    executive_reasoning?: string;
    resolutions?: Array<{
      code: string;
      analysis: string;
      recommended_action: string;
    }>;
  } | null;
  validation?: {
    passed?: boolean;
    rules_evaluated?: number;
    passed_rules?: string[];
    failed_rules?: string[];
    warnings?: string[];
  };
  citations?: string[];
  executed_agents?: string[];
  skipped_agents?: string[];
  disclaimer?: string | null;
  error?: Record<string, unknown>;
}

export interface WorkflowSummary {
  id: string;
  user_id: string;
  idempotency_key: string | null;
  query: string;
  document_ids: string[];
  intent: string;
  selected_tier: number;
  final_tier: number;
  routing_rationale: string;
  status: string;
  final_response_json: WorkflowResponseBody;
  raw_confidence: number;
  calibrated_confidence: number;
  escalation_count: number;
  retry_count: number;
  step_count: number;
  agent_call_count: number;
  tool_call_count: number;
  total_tokens: number;
  total_cost_usd: number;
  latency_ms: number;
  cache_hit: boolean;
  error_json: Record<string, unknown> | null;
  created_at: string;
  completed_at: string | null;
}

export interface WorkflowTrace extends WorkflowSummary {
  steps: WorkflowStep[];
  model_invocations: ModelInvocation[];
  tool_invocations: ToolInvocation[];
  estimated_baseline_cost_usd: number;
  estimated_baseline_tokens: number;
  savings_usd: number;
  skipped_agents: string[];
}

export interface BudgetPolicy {
  id: string;
  name: string;
  scope: string;
  user_id: string | null;
  task_type: string | null;
  max_steps: number;
  max_agent_calls: number;
  max_tokens_per_workflow: number;
  max_cost_per_workflow_usd: number;
  daily_cost_limit_usd: number;
  timeout_seconds: number;
  max_retries: number;
  max_tool_calls_per_agent: number;
  max_escalations: number;
  confidence_threshold: number;
  is_active: boolean;
  updated_at: string;
}

export interface CircuitBreakerStatus {
  key: string;
  state: string;
  failure_count: number;
  failure_threshold: number;
  recovery_seconds: number;
  opened_at: number | null;
}

export interface BudgetSummary {
  global_daily_spend_usd: number;
  global_daily_limit_usd: number;
  user_daily_spend_usd: number;
  user_daily_limit_usd: number;
  active_policies: BudgetPolicy[];
  circuit_breakers: CircuitBreakerStatus[];
}

export interface AnalyticsOverview {
  total_workflows: number;
  total_tokens: number;
  estimated_baseline_tokens: number;
  token_savings_pct: number;
  total_cost_usd: number;
  estimated_baseline_cost_usd: number;
  savings_usd: number;
  cost_savings_pct: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  escalation_rate_pct: number;
  cache_hit_rate_pct: number;
  tier_distribution: Record<string, number>;
  latency_by_tier: Array<{ tier: string; count: number; p50_ms: number; p95_ms: number }>;
  agent_cost_breakdown: Array<{ agent: string; calls: number; tokens: number; cost_usd: number }>;
}

export interface ModelRegistryItem {
  id: string;
  model_key: string;
  provider: string;
  tier: number;
  input_cost_per_1k: number;
  output_cost_per_1k: number;
  max_context_tokens: number;
  avg_latency_ms: number;
  calibration_slope: number;
  calibration_intercept: number;
  is_active: boolean;
}

export interface EvaluationRun {
  id: string;
  name: string;
  dataset_name: string;
  mode: string;
  sample_count: number;
  avg_tokens: number;
  avg_cost_usd: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  throughput_rps: number;
  field_precision: number;
  field_recall: number;
  field_f1: number;
  classification_f1: number;
  escalation_rate: number;
  avg_tool_calls: number;
  failure_rate: number;
  ece_calibration_error: number;
  tier_distribution_json: Record<string, number>;
  created_at: string;
}

export interface BenchmarkComparison {
  baseline_monolithic: EvaluationRun;
  flowpilot_orchestrator: EvaluationRun;
  token_reduction_pct: number;
  cost_reduction_pct: number;
  p95_latency_reduction_pct: number;
  throughput_multiplier: number;
  f1_delta: number;
  calibration_bins: Array<{
    range: string;
    count: number;
    avg_confidence: number;
    empirical_accuracy: number;
    calibration_gap: number;
  }>;
  report_markdown: string;
}
