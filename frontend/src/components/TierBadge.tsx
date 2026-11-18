import React from "react";

const TIER_META: Record<number, { label: string; classes: string; desc: string }> = {
  0: {
    label: "Tier 0 · Deterministic",
    classes: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
    desc: "Zero-LLM fast path",
  },
  1: {
    label: "Tier 1 · Lightweight AI",
    classes: "bg-sky-500/15 text-sky-300 border-sky-500/30",
    desc: "Small instruction model",
  },
  2: {
    label: "Tier 2 · Multi-Agent",
    classes: "bg-indigo-500/15 text-indigo-300 border-indigo-500/30",
    desc: "LangGraph specialist workflow",
  },
  3: {
    label: "Tier 3 · Frontier Escalation",
    classes: "bg-amber-500/15 text-amber-300 border-amber-500/30",
    desc: "Advanced frontier reasoning",
  },
};

export const TierBadge: React.FC<{ tier: number; compact?: boolean }> = ({ tier, compact }) => {
  const meta = TIER_META[tier] ?? TIER_META[1];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${meta.classes}`}
      title={meta.desc}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {compact ? `T${tier}` : meta.label}
    </span>
  );
};

export const SeverityBadge: React.FC<{ severity: string }> = ({ severity }) => {
  const map: Record<string, string> = {
    critical: "bg-rose-500/20 text-rose-300 border-rose-500/40",
    high: "bg-orange-500/20 text-orange-300 border-orange-500/40",
    medium: "bg-amber-500/20 text-amber-300 border-amber-500/40",
    low: "bg-slate-500/20 text-slate-300 border-slate-500/40",
  };
  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${map[severity] ?? map.low}`}
    >
      {severity}
    </span>
  );
};

export const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const map: Record<string, string> = {
    completed: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
    running: "bg-sky-500/15 text-sky-300 border-sky-500/30",
    budget_exceeded: "bg-amber-500/15 text-amber-300 border-amber-500/30",
    cancelled: "bg-slate-500/15 text-slate-300 border-slate-500/30",
    failed: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  };
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium capitalize ${map[status] ?? map.cancelled}`}
    >
      {status.replace("_", " ")}
    </span>
  );
};
