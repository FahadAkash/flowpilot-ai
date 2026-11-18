import React from "react";
import { ArrowRight, CheckCircle2, SkipForward } from "lucide-react";
import type { WorkflowTrace } from "../types";

const CANONICAL_AGENTS = [
  { key: "intent_router", label: "Intent Router" },
  { key: "planner", label: "Planner" },
  { key: "retrieval", label: "Retrieval" },
  { key: "extraction", label: "Extraction" },
  { key: "comparison", label: "Comparison" },
  { key: "validation", label: "Validation" },
  { key: "reasoning", label: "Tier 3 Reasoning" },
  { key: "response", label: "Response" },
];

export const ExecutionPipeline: React.FC<{ trace: WorkflowTrace }> = ({ trace }) => {
  const stepByAgent = new Map(trace.steps.map((s) => [s.agent_name, s]));

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-slate-100">
            LangGraph Specialist Execution Path
          </h3>
          <p className="text-xs text-slate-400">
            Highlighted agents executed; dimmed agents were intentionally bypassed to save tokens and latency.
          </p>
        </div>
        <span className="rounded-md bg-slate-800 px-2.5 py-1 text-xs text-slate-300">
          {trace.steps.length} active step(s) · {trace.skipped_agents.length} skipped
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {CANONICAL_AGENTS.map((agent, idx) => {
          const step = stepByAgent.get(agent.key);
          const active = Boolean(step);
          const isTier3 = agent.key === "reasoning" && active;
          return (
            <React.Fragment key={agent.key}>
              <div
                className={`min-w-[120px] rounded-lg border px-3 py-2 transition ${
                  active
                    ? isTier3
                      ? "border-amber-500/50 bg-amber-500/10 text-amber-100"
                      : "border-indigo-500/50 bg-indigo-500/10 text-slate-100"
                    : "border-slate-800 bg-slate-950/60 text-slate-500 opacity-60"
                }`}
              >
                <div className="flex items-center justify-between gap-1.5">
                  <span className="text-xs font-semibold">{agent.label}</span>
                  {active ? (
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                  ) : (
                    <SkipForward className="h-3.5 w-3.5 text-slate-600" />
                  )}
                </div>
                <div className="mt-1 text-[11px] text-slate-400">
                  {step ? (
                    <>
                      {step.latency_ms.toFixed(1)}ms · {step.tokens_used} tok
                    </>
                  ) : (
                    "Skipped"
                  )}
                </div>
              </div>
              {idx < CANONICAL_AGENTS.length - 1 && (
                <ArrowRight className="h-3.5 w-3.5 shrink-0 text-slate-600" />
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};
