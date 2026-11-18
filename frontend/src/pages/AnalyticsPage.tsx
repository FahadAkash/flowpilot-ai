import React, { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import type { AnalyticsOverview, ModelRegistryItem } from "../types";
import { TierBadge } from "../components/TierBadge";

const TIER_COLORS = ["#10b981", "#38bdf8", "#818cf8", "#f59e0b"];

export const AnalyticsPage: React.FC = () => {
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [models, setModels] = useState<ModelRegistryItem[]>([]);

  useEffect(() => {
    void Promise.all([api.getAnalyticsOverview(), api.listModels()]).then(([ov, ms]) => {
      setOverview(ov);
      setModels(ms);
    });
  }, []);

  if (!overview) {
    return <div className="p-8 text-center text-xs text-slate-400">Loading telemetry...</div>;
  }

  const tierPie = [
    { name: "Tier 0 (Deterministic)", value: overview.tier_distribution.tier_0 ?? 0 },
    { name: "Tier 1 (Lightweight AI)", value: overview.tier_distribution.tier_1 ?? 0 },
    { name: "Tier 2 (Multi-Agent)", value: overview.tier_distribution.tier_2 ?? 0 },
    { name: "Tier 3 (Frontier)", value: overview.tier_distribution.tier_3 ?? 0 },
  ];

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <KpiCard label="Total Workflows" value={String(overview.total_workflows)} sub="Persisted runs" />
        <KpiCard
          label="Token Savings"
          value={`${overview.token_savings_pct.toFixed(1)}%`}
          sub={`${overview.total_tokens.toLocaleString()} vs ${overview.estimated_baseline_tokens.toLocaleString()} base`}
          accent="text-emerald-400"
        />
        <KpiCard
          label="Cost Savings"
          value={`${overview.cost_savings_pct.toFixed(1)}%`}
          sub={`Saved $${overview.savings_usd.toFixed(4)}`}
          accent="text-emerald-400"
        />
        <KpiCard
          label="p50 / p95 Latency"
          value={`${overview.p50_latency_ms.toFixed(0)} / ${overview.p95_latency_ms.toFixed(0)}ms`}
          sub="End-to-end orchestration"
          accent="text-sky-300"
        />
        <KpiCard
          label="Escalation / Cache"
          value={`${overview.escalation_rate_pct.toFixed(1)}% / ${overview.cache_hit_rate_pct.toFixed(1)}%`}
          sub="Tier 3 rate · Tier 0 cache"
          accent="text-amber-300"
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
          <h3 className="mb-3 text-sm font-semibold text-slate-100">Tier Routing Distribution</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={tierPie}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={90}
                  paddingAngle={3}
                >
                  {tierPie.map((entry, index) => (
                    <Cell key={entry.name} fill={TIER_COLORS[index % TIER_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ backgroundColor: "#0f172a", borderColor: "#1e293b", fontSize: 12 }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 flex flex-wrap justify-center gap-4 text-xs text-slate-300">
            {tierPie.map((t, i) => (
              <span key={t.name} className="flex items-center gap-1.5">
                <span
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: TIER_COLORS[i] }}
                />
                {t.name}: <strong>{t.value}</strong>
              </span>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
          <h3 className="mb-3 text-sm font-semibold text-slate-100">
            Latency by Execution Tier (p50 vs p95 ms)
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={overview.latency_by_tier}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="tier" stroke="#94a3b8" fontSize={12} />
                <YAxis stroke="#94a3b8" fontSize={12} />
                <Tooltip
                  contentStyle={{ backgroundColor: "#0f172a", borderColor: "#1e293b", fontSize: 12 }}
                />
                <Bar dataKey="p50_ms" name="p50 (ms)" fill="#38bdf8" radius={[4, 4, 0, 0]} />
                <Bar dataKey="p95_ms" name="p95 (ms)" fill="#818cf8" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Model Registry Table */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
        <h3 className="mb-3 text-sm font-semibold text-slate-100">
          Model Registry (`model_registry` — Pricing & Confidence Calibration)
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400">
                <th className="py-2 pr-3">Model</th>
                <th className="py-2 pr-3">Provider</th>
                <th className="py-2 pr-3">Tier</th>
                <th className="py-2 pr-3 text-right">Input / 1K</th>
                <th className="py-2 pr-3 text-right">Output / 1K</th>
                <th className="py-2 pr-3 text-right">Context</th>
                <th className="py-2 text-right">Calibration (slope / int)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80">
              {models.map((m) => (
                <tr key={m.id}>
                  <td className="py-2 pr-3 font-mono font-medium text-slate-100">{m.model_key}</td>
                  <td className="py-2 pr-3 capitalize text-slate-300">{m.provider}</td>
                  <td className="py-2 pr-3">
                    <TierBadge tier={m.tier} compact />
                  </td>
                  <td className="py-2 pr-3 text-right font-mono text-slate-300">
                    ${m.input_cost_per_1k.toFixed(5)}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono text-slate-300">
                    ${m.output_cost_per_1k.toFixed(5)}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono text-slate-400">
                    {m.max_context_tokens.toLocaleString()}
                  </td>
                  <td className="py-2 text-right font-mono text-sky-300">
                    {m.calibration_slope.toFixed(2)} / {m.calibration_intercept.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

const KpiCard: React.FC<{ label: string; value: string; sub: string; accent?: string }> = ({
  label,
  value,
  sub,
  accent = "text-slate-100",
}) => (
  <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
    <div className="text-xs text-slate-400">{label}</div>
    <div className={`mt-1 text-xl font-bold ${accent}`}>{value}</div>
    <div className="mt-1 text-[11px] text-slate-500">{sub}</div>
  </div>
);
