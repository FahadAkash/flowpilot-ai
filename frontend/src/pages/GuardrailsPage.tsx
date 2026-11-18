import React, { useEffect, useState } from "react";
import { RefreshCw, Save, ShieldAlert } from "lucide-react";
import { api } from "../api/client";
import type { BudgetPolicy, BudgetSummary } from "../types";

export const GuardrailsPage: React.FC = () => {
  const [summary, setSummary] = useState<BudgetSummary | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = async () => {
    const data = await api.getBudgets();
    setSummary(data);
  };

  useEffect(() => {
    void load();
  }, []);

  const handleFieldChange = (policyId: string, field: keyof BudgetPolicy, value: number) => {
    setSummary((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        active_policies: prev.active_policies.map((p) =>
          p.id === policyId ? { ...p, [field]: value } : p,
        ),
      };
    });
  };

  const handleSave = async (policy: BudgetPolicy) => {
    setSavingId(policy.id);
    setMessage(null);
    try {
      await api.updateBudgetPolicy(policy.id, {
        max_steps: policy.max_steps,
        max_agent_calls: policy.max_agent_calls,
        max_tokens_per_workflow: policy.max_tokens_per_workflow,
        max_cost_per_workflow_usd: policy.max_cost_per_workflow_usd,
        daily_cost_limit_usd: policy.daily_cost_limit_usd,
        timeout_seconds: policy.timeout_seconds,
        max_retries: policy.max_retries,
        max_tool_calls_per_agent: policy.max_tool_calls_per_agent,
        max_escalations: policy.max_escalations,
        confidence_threshold: policy.confidence_threshold,
      });
      setMessage(`Updated guardrail policy '${policy.name}'.`);
      await load();
    } finally {
      setSavingId(null);
    }
  };

  const handleResetBreaker = async (key: string) => {
    await api.resetCircuitBreaker(key);
    setMessage(`Reset circuit breaker '${key}' to CLOSED.`);
    await load();
  };

  if (!summary) {
    return <div className="p-8 text-center text-xs text-slate-400">Loading guardrails...</div>;
  }

  return (
    <div className="space-y-6">
      {message && (
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-2 text-xs text-emerald-300">
          {message}
        </div>
      )}

      {/* Daily Budget Utilization */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <SpendBar
          label="Global Daily LLM Spend"
          used={summary.global_daily_spend_usd}
          limit={summary.global_daily_limit_usd}
        />
        <SpendBar
          label="Current User Daily LLM Spend"
          used={summary.user_daily_spend_usd}
          limit={summary.user_daily_limit_usd}
        />
      </div>

      {/* Editable Budget Policies */}
      <div className="space-y-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-100">
          <ShieldAlert className="h-4 w-4 text-amber-400" />
          Active Execution & Cost Guardrail Policies (`budget_policies`)
        </h2>
        {summary.active_policies.map((pol) => (
          <div key={pol.id} className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <span className="font-mono text-sm font-semibold text-slate-100">{pol.name}</span>
                <span className="ml-2 rounded bg-slate-800 px-2 py-0.5 text-[11px] uppercase text-slate-300">
                  scope: {pol.scope}
                </span>
              </div>
              <button
                type="button"
                onClick={() => void handleSave(pol)}
                disabled={savingId === pol.id}
                className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
              >
                <Save className="h-3.5 w-3.5" />
                {savingId === pol.id ? "Saving..." : "Save Policy"}
              </button>
            </div>

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              {(
                [
                  ["max_steps", "Max Steps"],
                  ["max_agent_calls", "Max Agent Calls"],
                  ["max_tokens_per_workflow", "Token Budget"],
                  ["timeout_seconds", "Timeout (s)"],
                  ["max_retries", "Max Retries"],
                  ["max_tool_calls_per_agent", "Tool Limit / Agent"],
                  ["max_escalations", "Max Escalations"],
                  ["confidence_threshold", "Confidence Gate"],
                  ["max_cost_per_workflow_usd", "Max Cost / WF ($)"],
                  ["daily_cost_limit_usd", "Daily Limit ($)"],
                ] as const
              ).map(([field, label]) => (
                <label key={field} className="block text-xs">
                  <span className="text-slate-400">{label}</span>
                  <input
                    type="number"
                    step={field.includes("cost") || field.includes("confidence") ? "0.05" : "1"}
                    value={Number(pol[field])}
                    onChange={(e) => handleFieldChange(pol.id, field, Number(e.target.value))}
                    className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-2.5 py-1.5 font-mono text-xs text-slate-100"
                  />
                </label>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Circuit Breakers */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
        <h3 className="mb-3 text-sm font-semibold text-slate-100">
          Upstream Model Circuit Breakers
        </h3>
        {summary.circuit_breakers.length === 0 ? (
          <p className="text-xs text-slate-400">
            All circuit breakers are healthy (closed). Execute workflows to initialize per-tier
            provider monitors.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {summary.circuit_breakers.map((cb) => (
              <div
                key={cb.key}
                className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-950/70 p-3 text-xs"
              >
                <div>
                  <div className="font-mono font-semibold text-slate-100">{cb.key}</div>
                  <div className="mt-0.5 text-[11px] text-slate-400">
                    State: <strong className="uppercase text-emerald-300">{cb.state}</strong> ·
                    Failures: {cb.failure_count}/{cb.failure_threshold}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => void handleResetBreaker(cb.key)}
                  className="rounded-md border border-slate-700 p-1.5 text-slate-300 hover:bg-slate-800"
                  title="Reset circuit breaker"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

const SpendBar: React.FC<{ label: string; used: number; limit: number }> = ({
  label,
  used,
  limit,
}) => {
  const pct = Math.min(100, (used / Math.max(limit, 0.0001)) * 100);
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-slate-200">{label}</span>
        <span className="font-mono text-slate-300">
          ${used.toFixed(5)} / ${limit.toFixed(2)}
        </span>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-800">
        <div
          className="h-full rounded-full bg-emerald-500 transition-all"
          style={{ width: `${Math.max(pct, used > 0 ? 2 : 0)}%` }}
        />
      </div>
    </div>
  );
};
