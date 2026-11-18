import React, { useEffect, useState } from "react";
import { Activity, Cpu, Wrench } from "lucide-react";
import { api } from "../api/client";
import type { WorkflowSummary, WorkflowTrace } from "../types";
import { ExecutionPipeline } from "../components/ExecutionPipeline";
import { StatusBadge, TierBadge } from "../components/TierBadge";

interface TracePageProps {
  workflows: WorkflowSummary[];
  selectedTrace: WorkflowTrace | null;
  onSelectWorkflow: (id: string) => Promise<void>;
}

export const TracePage: React.FC<TracePageProps> = ({
  workflows,
  selectedTrace,
  onSelectWorkflow,
}) => {
  const [mermaid, setMermaid] = useState<string>("");

  useEffect(() => {
    void api.getGraphMermaid().then((r) => setMermaid(r.mermaid)).catch(() => {});
  }, []);

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
      {/* Workflow History List */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4 lg:col-span-4">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-100">
          <Activity className="h-4 w-4 text-sky-400" />
          Execution History ({workflows.length})
        </h2>
        <div className="max-h-[640px] space-y-2 overflow-y-auto pr-1">
          {workflows.length === 0 ? (
            <p className="text-xs text-slate-400">
              No workflows executed yet. Run a query from Studio to inspect its execution trace.
            </p>
          ) : (
            workflows.map((wf) => (
              <button
                key={wf.id}
                type="button"
                onClick={() => void onSelectWorkflow(wf.id)}
                className={`w-full rounded-lg border p-3 text-left transition ${
                  selectedTrace?.id === wf.id
                    ? "border-indigo-500/60 bg-indigo-500/10"
                    : "border-slate-800 bg-slate-950/60 hover:border-slate-700"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <TierBadge tier={wf.final_tier} compact />
                  <StatusBadge status={wf.status} />
                </div>
                <p className="mt-1.5 line-clamp-2 text-xs font-medium text-slate-200">{wf.query}</p>
                <div className="mt-1.5 flex items-center justify-between text-[11px] text-slate-400">
                  <span>{wf.total_tokens} tok</span>
                  <span>${wf.total_cost_usd.toFixed(5)}</span>
                  <span>{wf.latency_ms.toFixed(1)}ms</span>
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Selected Trace Details */}
      <div className="space-y-5 lg:col-span-8">
        {selectedTrace ? (
          <>
            <ExecutionPipeline trace={selectedTrace} />

            {/* Workflow Steps Table (State Store) */}
            <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
              <h3 className="mb-3 text-sm font-semibold text-slate-100">
                Workflow Steps (`workflow_steps` — State Store)
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400">
                      <th className="py-2 pr-3">#</th>
                      <th className="py-2 pr-3">Node / Agent</th>
                      <th className="py-2 pr-3">Tier</th>
                      <th className="py-2 pr-3">Routing Reason</th>
                      <th className="py-2 pr-3 text-right">Tokens</th>
                      <th className="py-2 text-right">Latency</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/80">
                    {selectedTrace.steps.map((s) => (
                      <tr key={s.id}>
                        <td className="py-2 pr-3 font-mono text-slate-400">{s.step_index + 1}</td>
                        <td className="py-2 pr-3 font-mono text-slate-100">
                          {s.node_name}
                          <div className="text-[11px] text-slate-400">{s.agent_name}</div>
                        </td>
                        <td className="py-2 pr-3">
                          <TierBadge tier={s.tier} compact />
                        </td>
                        <td className="py-2 pr-3 text-slate-300">{s.routing_reason}</td>
                        <td className="py-2 pr-3 text-right font-mono text-slate-200">
                          {s.tokens_used}
                        </td>
                        <td className="py-2 text-right font-mono text-slate-200">
                          {s.latency_ms.toFixed(1)}ms
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Separate Model Invocations & Tool Invocations Audit Logs */}
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
                <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-100">
                  <Cpu className="h-4 w-4 text-indigo-400" />
                  Model Invocations ({selectedTrace.model_invocations.length})
                </h3>
                {selectedTrace.model_invocations.length === 0 ? (
                  <p className="rounded-lg bg-emerald-500/10 p-3 text-xs text-emerald-300">
                    0 LLM invocations! Handled entirely by Tier 0 deterministic logic/cache.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {selectedTrace.model_invocations.map((m) => (
                      <div
                        key={m.id}
                        className="rounded-lg border border-slate-800 bg-slate-950/70 p-2.5 text-xs"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-mono font-semibold text-slate-100">
                            {m.model_key}
                          </span>
                          <TierBadge tier={m.tier} compact />
                        </div>
                        <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-slate-400">
                          <span>Agent: {m.agent_name}</span>
                          <span>
                            Tokens: {m.prompt_tokens} in / {m.completion_tokens} out
                          </span>
                          <span>Cost: ${m.cost_usd.toFixed(5)}</span>
                          {m.calibrated_confidence != null && (
                            <span>
                              Cal Conf: {(m.calibrated_confidence * 100).toFixed(1)}%
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
                <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-100">
                  <Wrench className="h-4 w-4 text-emerald-400" />
                  Tool Invocations ({selectedTrace.tool_invocations.length})
                </h3>
                {selectedTrace.tool_invocations.length === 0 ? (
                  <p className="text-xs text-slate-400">No tool calls required for this workflow.</p>
                ) : (
                  <div className="space-y-2">
                    {selectedTrace.tool_invocations.map((t) => (
                      <div
                        key={t.id}
                        className="rounded-lg border border-slate-800 bg-slate-950/70 p-2.5 text-xs"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-mono font-semibold text-emerald-300">
                            {t.tool_name}
                          </span>
                          <span className="text-[11px] text-slate-400">
                            {t.latency_ms.toFixed(2)}ms
                          </span>
                        </div>
                        <div className="mt-1 text-[11px] text-slate-400">
                          Agent: {t.agent_name} · Output: {JSON.stringify(t.result_summary_json)}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </>
        ) : (
          <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-8 text-center text-xs text-slate-400">
            Select a workflow from the left list to inspect its separated workflow steps, model
            invocations, and tool invocation telemetry.
          </div>
        )}

        {mermaid && (
          <details className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
            <summary className="cursor-pointer text-xs font-semibold text-slate-300">
              Compiled LangGraph StateGraph Topology (Mermaid Definition)
            </summary>
            <pre className="mt-3 overflow-x-auto rounded-lg bg-slate-950 p-3 font-mono text-[11px] text-emerald-300">
              {mermaid}
            </pre>
          </details>
        )}
      </div>
    </div>
  );
};
