import React, { useState } from "react";
import {
  AlertTriangle,
  FileText,
  Layers,
  Play,
  Sparkles,
  Trash2,
  Upload,
  Zap,
} from "lucide-react";
import { api } from "../api/client";
import type { DocumentItem, WorkflowTrace } from "../types";
import { ExecutionPipeline } from "../components/ExecutionPipeline";
import { SeverityBadge, StatusBadge, TierBadge } from "../components/TierBadge";

interface StudioPageProps {
  documents: DocumentItem[];
  onDocumentsChange: () => Promise<void>;
  onWorkflowCompleted: (trace: WorkflowTrace) => void;
  latestTrace: WorkflowTrace | null;
}

const PRESET_PROMPTS = [
  {
    tier: 0,
    label: "Tier 0 · Invoice Number (0 LLM tokens)",
    query: "What is the invoice number?",
    docFilter: (d: DocumentItem) => d.doc_type === "invoice",
  },
  {
    tier: 0,
    label: "Tier 0 · Calculate Total + Verify Tax",
    query: "Calculate the invoice total and verify subtotal plus tax.",
    docFilter: (d: DocumentItem) => d.doc_type === "invoice",
  },
  {
    tier: 1,
    label: "Tier 1 · Classify Document (SLM)",
    query: "Classify whether this document is an invoice, contract, or policy.",
    docFilter: (d: DocumentItem) => d.doc_type === "invoice",
  },
  {
    tier: 2,
    label: "Tier 2 · 3-Way Invoice vs PO vs Policy",
    query:
      "Check whether this invoice follows our purchase order and company policy. Identify any discrepancies.",
    docFilter: (d: DocumentItem) =>
      ["invoice", "purchase_order", "policy"].includes(d.doc_type),
  },
  {
    tier: 3,
    label: "Tier 3 · Conflicting Contract Escalation",
    query:
      "Compare these two contracts and resolve conflicting indemnification, liability cap, and governing law terms.",
    docFilter: (d: DocumentItem) => d.doc_type === "contract",
  },
];

export const StudioPage: React.FC<StudioPageProps> = ({
  documents,
  onDocumentsChange,
  onWorkflowCompleted,
  latestTrace,
}) => {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [query, setQuery] = useState(
    "Check whether this invoice follows our purchase order and company policy. Identify any discrepancies.",
  );
  const [forceTier, setForceTier] = useState<string>("auto");
  const [bypassCache, setBypassCache] = useState<boolean>(false);
  const [running, setRunning] = useState(false);
  const [loadingPack, setLoadingPack] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleDoc = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id],
    );
  };

  const handleLoadDemoPack = async () => {
    setLoadingPack(true);
    setError(null);
    try {
      const loaded = await api.loadDemoPack();
      await onDocumentsChange();
      setSelectedIds(
        loaded
          .filter((d) => ["invoice", "purchase_order", "policy"].includes(d.doc_type))
          .map((d) => d.id),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load demo pack");
    } finally {
      setLoadingPack(false);
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    setError(null);
    try {
      const newIds: string[] = [];
      for (const file of Array.from(files)) {
        const doc = await api.uploadDocument(file);
        newIds.push(doc.id);
      }
      await onDocumentsChange();
      setSelectedIds((prev) => Array.from(new Set([...prev, ...newIds])));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      e.target.value = "";
    }
  };

  const handleDeleteDoc = async (id: string) => {
    await api.deleteDocument(id);
    setSelectedIds((prev) => prev.filter((x) => x !== id));
    await onDocumentsChange();
  };

  const handleExecute = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!query.trim()) return;
    setRunning(true);
    setError(null);
    try {
      const docIds = selectedIds.length > 0 ? selectedIds : documents.map((d) => d.id);
      const trace = await api.executeWorkflow({
        query: query.trim(),
        document_ids: docIds,
        force_tier: forceTier === "auto" ? null : Number(forceTier),
        bypass_cache: bypassCache,
      });
      onWorkflowCompleted(trace);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Workflow execution failed");
    } finally {
      setRunning(false);
    }
  };

  const applyPreset = (preset: (typeof PRESET_PROMPTS)[number]) => {
    setQuery(preset.query);
    setForceTier("auto");
    const matching = documents.filter(preset.docFilter).map((d) => d.id);
    if (matching.length > 0) {
      setSelectedIds(matching);
    }
  };

  const resp = latestTrace?.final_response_json;
  const discrepancies = resp?.discrepancies ?? [];

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
      {/* Left Sidebar: Document Library */}
      <div className="space-y-4 lg:col-span-4">
        <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
          <div className="flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-100">
              <FileText className="h-4 w-4 text-indigo-400" />
              Enterprise Document Vault
            </h2>
            <span className="text-xs text-slate-400">{documents.length} doc(s)</span>
          </div>

          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={handleLoadDemoPack}
              disabled={loadingPack}
              className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-50"
            >
              <Sparkles className="h-3.5 w-3.5" />
              {loadingPack ? "Generating PDFs..." : "Load 5-PDF Demo Pack"}
            </button>
            <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-medium text-slate-200 transition hover:bg-slate-700">
              <Upload className="h-3.5 w-3.5" />
              Upload PDF/TXT
              <input
                type="file"
                multiple
                accept=".pdf,.txt,.md,.json,.csv"
                className="hidden"
                onChange={handleUpload}
              />
            </label>
          </div>

          <div className="mt-4 max-h-[420px] space-y-2 overflow-y-auto pr-1">
            {documents.length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-800 p-6 text-center text-xs text-slate-400">
                No documents uploaded yet. Click <strong>Load 5-PDF Demo Pack</strong> to generate
                real PDFs (Invoice, Purchase Order, Company Policy, and 2 Contracts) parsed via PyMuPDF.
              </div>
            ) : (
              documents.map((doc) => {
                const checked = selectedIds.includes(doc.id);
                return (
                  <div
                    key={doc.id}
                    onClick={() => toggleDoc(doc.id)}
                    className={`group flex cursor-pointer items-start justify-between gap-2 rounded-lg border p-2.5 transition ${
                      checked
                        ? "border-indigo-500/60 bg-indigo-500/10"
                        : "border-slate-800 bg-slate-950/60 hover:border-slate-700"
                    }`}
                  >
                    <div className="flex items-start gap-2.5">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => {}}
                        className="mt-1 accent-indigo-500"
                      />
                      <div>
                        <div className="text-xs font-medium text-slate-100">{doc.filename}</div>
                        <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-400">
                          <span className="rounded bg-slate-800 px-1.5 py-0.5 uppercase tracking-wide text-slate-300">
                            {doc.doc_type.replace("_", " ")}
                          </span>
                          <span>{doc.page_count} pg</span>
                          <span>· {doc.chunk_count} chunks</span>
                        </div>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={(ev) => {
                        ev.stopPropagation();
                        void handleDeleteDoc(doc.id);
                      }}
                      className="rounded p-1 text-slate-500 opacity-0 transition hover:bg-slate-800 hover:text-rose-400 group-hover:opacity-100"
                      title="Delete document"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Tier Quick Prompts */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
          <h3 className="mb-2.5 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
            <Zap className="h-3.5 w-3.5 text-amber-400" />
            Curated Tier 0–3 Scenarios
          </h3>
          <div className="space-y-2">
            {PRESET_PROMPTS.map((p) => (
              <button
                key={p.label}
                type="button"
                onClick={() => applyPreset(p)}
                className="w-full rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 text-left transition hover:border-indigo-500/40 hover:bg-slate-800/70"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium text-slate-200">{p.label}</span>
                  <TierBadge tier={p.tier} compact />
                </div>
                <p className="mt-0.5 line-clamp-1 text-[11px] text-slate-400">{p.query}</p>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Right Main Area: Orchestrator Input & Structured Output */}
      <div className="space-y-5 lg:col-span-8">
        <form
          onSubmit={handleExecute}
          className="rounded-xl border border-slate-800 bg-slate-900/70 p-4"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <label className="text-sm font-semibold text-slate-100">
              Natural Language Workflow Request
            </label>
            <div className="flex items-center gap-3 text-xs text-slate-400">
              <label className="flex items-center gap-1.5">
                <span>Routing:</span>
                <select
                  value={forceTier}
                  onChange={(e) => setForceTier(e.target.value)}
                  className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200"
                >
                  <option value="auto">Auto (Intelligent Router)</option>
                  <option value="0">Force Tier 0</option>
                  <option value="1">Force Tier 1</option>
                  <option value="2">Force Tier 2</option>
                  <option value="3">Force Tier 3</option>
                </select>
              </label>
              <label className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={bypassCache}
                  onChange={(e) => setBypassCache(e.target.checked)}
                  className="accent-indigo-500"
                />
                Bypass Cache
              </label>
            </div>
          </div>

          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            rows={3}
            placeholder="Ask a question, extract fields, or compare invoices against purchase orders and company policy..."
            className="mt-2.5 w-full rounded-lg border border-slate-700 bg-slate-950 p-3 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
          />

          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs text-slate-400">
              {selectedIds.length > 0
                ? `${selectedIds.length} document(s) selected`
                : `All ${documents.length} vault document(s) will be considered`}
            </span>
            <button
              type="submit"
              disabled={running || documents.length === 0}
              className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white transition hover:bg-emerald-500 disabled:opacity-50"
            >
              <Play className="h-3.5 w-3.5" />
              {running ? "Orchestrating..." : "Execute Workflow"}
            </button>
          </div>
          {error && (
            <div className="mt-3 rounded-lg border border-rose-500/40 bg-rose-500/10 p-2.5 text-xs text-rose-200">
              {error}
            </div>
          )}
        </form>

        {latestTrace ? (
          <>
            {/* Routing Decision & Telemetry Strip */}
            <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <TierBadge tier={latestTrace.final_tier} />
                  <StatusBadge status={latestTrace.status} />
                  {latestTrace.cache_hit && (
                    <span className="rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-xs font-semibold text-emerald-300">
                      Cache Hit (0 tokens)
                    </span>
                  )}
                  {latestTrace.escalation_count > 0 && (
                    <span className="rounded-full bg-amber-500/15 px-2.5 py-0.5 text-xs font-semibold text-amber-300">
                      Escalated to Tier 3 ({latestTrace.escalation_count}x)
                    </span>
                  )}
                </div>

                <div className="flex flex-wrap items-center gap-4 text-xs">
                  <div>
                    <span className="text-slate-400">Tokens: </span>
                    <strong className="text-slate-100">
                      {latestTrace.total_tokens.toLocaleString()}
                    </strong>
                  </div>
                  <div>
                    <span className="text-slate-400">Cost: </span>
                    <strong className="text-slate-100">
                      ${latestTrace.total_cost_usd.toFixed(5)}
                    </strong>
                  </div>
                  <div>
                    <span className="text-slate-400">Saved vs Frontier: </span>
                    <strong className="text-emerald-400">
                      ${latestTrace.savings_usd.toFixed(5)}
                    </strong>
                  </div>
                  <div>
                    <span className="text-slate-400">Latency: </span>
                    <strong className="text-slate-100">{latestTrace.latency_ms.toFixed(1)}ms</strong>
                  </div>
                  <div>
                    <span className="text-slate-400">Calibrated Conf: </span>
                    <strong className="text-sky-300">
                      {(latestTrace.calibrated_confidence * 100).toFixed(1)}%
                    </strong>
                  </div>
                </div>
              </div>

              <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/80 p-3">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  Executive Answer
                </div>
                <p className="mt-1 text-sm leading-relaxed text-slate-100">
                  {resp?.summary ?? "Workflow finished."}
                </p>
                {latestTrace.routing_rationale && (
                  <p className="mt-2 border-t border-slate-800 pt-2 text-xs text-slate-400">
                    <strong className="text-slate-300">Why Tier {latestTrace.final_tier}:</strong>{" "}
                    {latestTrace.routing_rationale}
                  </p>
                )}
                {resp?.disclaimer && (
                  <p className="mt-2 text-[11px] italic text-slate-500">{resp.disclaimer}</p>
                )}
              </div>
            </div>

            {/* Interactive Execution Path */}
            <ExecutionPipeline trace={latestTrace} />

            {/* Discrepancies Table */}
            {discrepancies.length > 0 && (
              <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
                <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-100">
                  <AlertTriangle className="h-4 w-4 text-amber-400" />
                  Identified Discrepancies & Policy Concerns ({discrepancies.length})
                </h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400">
                        <th className="py-2 pr-3">Severity</th>
                        <th className="py-2 pr-3">Code / Field</th>
                        <th className="py-2 pr-3">Expected</th>
                        <th className="py-2 pr-3">Actual</th>
                        <th className="py-2">Potential Concern & Citation</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/80">
                      {discrepancies.map((d, i) => (
                        <tr key={`${d.code}-${i}`} className="align-top">
                          <td className="py-2.5 pr-3">
                            <SeverityBadge severity={d.severity} />
                          </td>
                          <td className="py-2.5 pr-3 font-mono text-[11px] text-slate-200">
                            <div>{d.code}</div>
                            <div className="text-slate-400">{d.field}</div>
                          </td>
                          <td className="py-2.5 pr-3 text-slate-300">{d.expected}</td>
                          <td className="py-2.5 pr-3 text-rose-300">{d.actual}</td>
                          <td className="py-2.5 text-slate-300">
                            <div>{d.potential_concern}</div>
                            <div className="mt-0.5 text-[11px] text-slate-500">
                              Citation: {d.citation}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Tier 3 Frontier Reasoning Block */}
            {resp?.frontier_reasoning && (
              <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
                <h3 className="flex items-center gap-2 text-sm font-semibold text-amber-200">
                  <Layers className="h-4 w-4 text-amber-400" />
                  Tier 3 Frontier Reasoning Synthesis
                </h3>
                <p className="mt-1 text-xs text-amber-100/90">
                  {resp.frontier_reasoning.executive_reasoning}
                </p>
                <div className="mt-3 space-y-2">
                  {(resp.frontier_reasoning.resolutions ?? []).map((r, i) => (
                    <div
                      key={`${r.code}-${i}`}
                      className="rounded-lg border border-amber-500/20 bg-slate-950/70 p-2.5 text-xs"
                    >
                      <div className="font-mono font-semibold text-amber-300">{r.code}</div>
                      <p className="mt-1 text-slate-200">{r.analysis}</p>
                      <p className="mt-1 text-emerald-300">
                        Recommended action: {r.recommended_action}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="rounded-xl border border-dashed border-slate-800 bg-slate-900/40 p-10 text-center">
            <Sparkles className="mx-auto h-8 w-8 text-indigo-400" />
            <h3 className="mt-3 text-sm font-semibold text-slate-200">
              Ready to Orchestrate Across Tiers 0–3
            </h3>
            <p className="mx-auto mt-1 max-w-md text-xs text-slate-400">
              Load the 5-PDF Enterprise Demo Pack or upload your own PDFs, choose a Tier 0–3
              scenario, and inspect how FlowPilot routes deterministically when possible and
              escalates to LangGraph specialist agents or Tier 3 only when justified.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
