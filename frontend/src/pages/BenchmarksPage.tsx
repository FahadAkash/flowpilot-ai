import React, { useEffect, useState } from "react";
import { BarChart3, Play } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import type { BenchmarkComparison } from "../types";

export const BenchmarksPage: React.FC = () => {
  const [comparison, setComparison] = useState<BenchmarkComparison | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void api
      .getLatestBenchmark()
      .then(setComparison)
      .catch(() => {});
  }, []);

  const handleRun = async () => {
    setRunning(true);
    setError(null);
    try {
      const res = await api.runBenchmark();
      setComparison(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Benchmark failed");
    } finally {
      setRunning(false);
    }
  };

  const base = comparison?.baseline_monolithic;
  const fp = comparison?.flowpilot_orchestrator;

  const sideBySideChart =
    base && fp
      ? [
          { metric: "Avg Tokens", BaselineA: Math.round(base.avg_tokens), FlowPilot: Math.round(fp.avg_tokens) },
          { metric: "p50 Latency (ms)", BaselineA: Math.round(base.p50_latency_ms), FlowPilot: Math.round(fp.p50_latency_ms) },
          { metric: "p95 Latency (ms)", BaselineA: Math.round(base.p95_latency_ms), FlowPilot: Math.round(fp.p95_latency_ms) },
        ]
      : [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-800 bg-slate-900/70 p-4">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-100">
            <BarChart3 className="h-4 w-4 text-emerald-400" />
            Benchmark Lab: Baseline A (Monolithic Frontier) vs Baseline B (FlowPilot Orchestrator)
          </h2>
          <p className="mt-0.5 text-xs text-slate-400">
            Evaluates identical multi-domain UniDoc-Bench-inspired documents across field-level F1,
            token spend, cost, p50/p95 latency, throughput, escalation rate, and confidence calibration (ECE).
          </p>
        </div>
        <button
          type="button"
          onClick={handleRun}
          disabled={running}
          className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white transition hover:bg-emerald-500 disabled:opacity-50"
        >
          <Play className="h-3.5 w-3.5" />
          {running ? "Running 16-Case Suite..." : "Run Comparative Benchmark"}
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-200">
          {error}
        </div>
      )}

      {comparison && base && fp ? (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
            <DeltaCard label="Token Spend" value={`-${comparison.token_reduction_pct.toFixed(1)}%`} accent="text-emerald-400" />
            <DeltaCard label="Cost / Request" value={`-${comparison.cost_reduction_pct.toFixed(1)}%`} accent="text-emerald-400" />
            <DeltaCard label="p95 Latency" value={`-${comparison.p95_latency_reduction_pct.toFixed(1)}%`} accent="text-sky-300" />
            <DeltaCard label="Throughput" value={`${comparison.throughput_multiplier.toFixed(2)}x`} accent="text-indigo-300" />
            <DeltaCard label="Field-Level F1" value={fp.field_f1.toFixed(4)} accent="text-amber-300" />
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
              <h3 className="mb-3 text-sm font-semibold text-slate-100">
                Tokens & Latency: Monolithic vs FlowPilot
              </h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={sideBySideChart}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="metric" stroke="#94a3b8" fontSize={12} />
                    <YAxis stroke="#94a3b8" fontSize={12} />
                    <Tooltip
                      contentStyle={{ backgroundColor: "#0f172a", borderColor: "#1e293b", fontSize: 12 }}
                    />
                    <Bar dataKey="BaselineA" name="Baseline A (Monolithic)" fill="#f43f5e" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="FlowPilot" name="Baseline B (FlowPilot)" fill="#10b981" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
              <h3 className="mb-3 text-sm font-semibold text-slate-100">
                Confidence Calibration Reliability Curve (ECE = {fp.ece_calibration_error.toFixed(4)})
              </h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={comparison.calibration_bins}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="range" stroke="#94a3b8" fontSize={12} />
                    <YAxis domain={[0, 1]} stroke="#94a3b8" fontSize={12} />
                    <Tooltip
                      contentStyle={{ backgroundColor: "#0f172a", borderColor: "#1e293b", fontSize: 12 }}
                    />
                    <Line type="monotone" dataKey="avg_confidence" name="Calibrated Confidence" stroke="#38bdf8" strokeWidth={2} />
                    <Line type="monotone" dataKey="empirical_accuracy" name="Empirical Accuracy" stroke="#10b981" strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
            <h3 className="mb-3 text-sm font-semibold text-slate-100">
              Full Evaluation Metrics Matrix ({fp.sample_count} Shared Test Cases)
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400">
                    <th className="py-2 pr-4">Metric</th>
                    <th className="py-2 pr-4 text-right">Baseline A (Monolithic)</th>
                    <th className="py-2 pr-4 text-right">Baseline B (FlowPilot)</th>
                    <th className="py-2">What It Proves</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/80">
                  {[
                    ["Avg Tokens / Request", base.avg_tokens.toFixed(1), fp.avg_tokens.toFixed(1), "Token efficiency via Tier 0-2 routing"],
                    ["Avg Cost / Request", `$${base.avg_cost_usd.toFixed(5)}`, `$${fp.avg_cost_usd.toFixed(5)}`, "Financial efficiency"],
                    ["p50 Latency", `${base.p50_latency_ms.toFixed(1)} ms`, `${fp.p50_latency_ms.toFixed(1)} ms`, "Typical response speed"],
                    ["p95 Latency", `${base.p95_latency_ms.toFixed(1)} ms`, `${fp.p95_latency_ms.toFixed(1)} ms`, "Tail latency control"],
                    ["Throughput", `${base.throughput_rps.toFixed(2)} req/s`, `${fp.throughput_rps.toFixed(2)} req/s`, "System concurrency & scalability"],
                    ["Field-Level F1", base.field_f1.toFixed(4), fp.field_f1.toFixed(4), "Extraction & discrepancy accuracy"],
                    ["Classification F1", base.classification_f1.toFixed(4), fp.classification_f1.toFixed(4), "Document classification quality"],
                    ["Escalation Rate", `${(base.escalation_rate * 100).toFixed(1)}%`, `${(fp.escalation_rate * 100).toFixed(1)}%`, "Router selectivity"],
                    ["Avg Tool Calls / Req", base.avg_tool_calls.toFixed(2), fp.avg_tool_calls.toFixed(2), "Bounded specialist tool usage"],
                    ["Failure Rate", `${(base.failure_rate * 100).toFixed(1)}%`, `${(fp.failure_rate * 100).toFixed(1)}%`, "Guardrail & system reliability"],
                  ].map(([m, a, b, note]) => (
                    <tr key={m}>
                      <td className="py-2 pr-4 font-medium text-slate-200">{m}</td>
                      <td className="py-2 pr-4 text-right font-mono text-slate-400">{a}</td>
                      <td className="py-2 pr-4 text-right font-mono font-semibold text-emerald-300">{b}</td>
                      <td className="py-2 text-slate-400">{note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : (
        <div className="rounded-xl border border-dashed border-slate-800 bg-slate-900/40 p-10 text-center text-xs text-slate-400">
          Click <strong>Run Comparative Benchmark</strong> to measure Baseline A (Monolithic
          Frontier) against Baseline B (FlowPilot Orchestrator) on identical multi-domain documents.
        </div>
      )}
    </div>
  );
};

const DeltaCard: React.FC<{ label: string; value: string; accent: string }> = ({
  label,
  value,
  accent,
}) => (
  <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
    <div className="text-xs text-slate-400">{label}</div>
    <div className={`mt-1 text-2xl font-bold ${accent}`}>{value}</div>
  </div>
);
