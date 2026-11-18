import type {
  AnalyticsOverview,
  BenchmarkComparison,
  BudgetPolicy,
  BudgetSummary,
  DocumentItem,
  ModelRegistryItem,
  WorkflowSummary,
  WorkflowTrace,
} from "../types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body || res.statusText}`);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string; provider: string }>("/health"),

  listDocuments: () => request<DocumentItem[]>("/api/v1/documents"),

  loadDemoPack: () =>
    request<DocumentItem[]>("/api/v1/documents/demo-pack", { method: "POST" }),

  uploadDocument: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentItem>("/api/v1/documents/upload", {
      method: "POST",
      body: form,
    });
  },

  deleteDocument: (id: string) =>
    request<void>(`/api/v1/documents/${id}`, { method: "DELETE" }),

  executeWorkflow: (payload: {
    query: string;
    document_ids: string[];
    force_tier?: number | null;
    bypass_cache?: boolean;
  }) => {
    const qs = payload.bypass_cache ? "?bypass_cache=true" : "";
    return request<WorkflowTrace>(`/api/v1/workflows/execute${qs}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: payload.query,
        document_ids: payload.document_ids,
        force_tier: payload.force_tier ?? null,
      }),
    });
  },

  listWorkflows: () => request<WorkflowSummary[]>("/api/v1/workflows?limit=40"),

  getWorkflowTrace: (id: string) => request<WorkflowTrace>(`/api/v1/workflows/${id}`),

  getGraphMermaid: () => request<{ mermaid: string }>("/api/v1/workflows/graph/mermaid"),

  getAnalyticsOverview: () => request<AnalyticsOverview>("/api/v1/analytics/overview"),

  listModels: () => request<ModelRegistryItem[]>("/api/v1/analytics/models"),

  getBudgets: () => request<BudgetSummary>("/api/v1/budgets"),

  updateBudgetPolicy: (policyId: string, patch: Partial<BudgetPolicy>) =>
    request<BudgetPolicy>(`/api/v1/budgets/${policyId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),

  resetCircuitBreaker: (key: string) =>
    request<{ key: string; state: string }>(
      `/api/v1/budgets/circuit-breakers/${encodeURIComponent(key)}/reset`,
      { method: "POST" },
    ),

  runBenchmark: () =>
    request<BenchmarkComparison>("/api/v1/benchmarks/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: "Baseline A vs FlowPilot Orchestrator",
        dataset_name: "unidoc-bench-curated",
        include_stress_cases: true,
      }),
    }),

  getLatestBenchmark: () =>
    request<BenchmarkComparison>("/api/v1/benchmarks/latest-comparison"),
};
