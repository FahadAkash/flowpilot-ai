import React, { useCallback, useEffect, useState } from "react";
import {
  Activity,
  BarChart3,
  Cpu,
  Gauge,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { api } from "./api/client";
import type { DocumentItem, WorkflowSummary, WorkflowTrace } from "./types";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { BenchmarksPage } from "./pages/BenchmarksPage";
import { GuardrailsPage } from "./pages/GuardrailsPage";
import { StudioPage } from "./pages/StudioPage";
import { TracePage } from "./pages/TracePage";

type TabKey = "studio" | "trace" | "analytics" | "benchmarks" | "guardrails";

const NAV_TABS: Array<{ key: TabKey; label: string; icon: React.FC<{ className?: string }> }> = [
  { key: "studio", label: "Document Studio", icon: Sparkles },
  { key: "trace", label: "Execution Trace", icon: Activity },
  { key: "analytics", label: "Cost & Telemetry", icon: Gauge },
  { key: "benchmarks", label: "Benchmark Lab", icon: BarChart3 },
  { key: "guardrails", label: "Guardrails & Ops", icon: ShieldCheck },
];

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabKey>("studio");
  const [provider, setProvider] = useState<string>("mock");
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [latestTrace, setLatestTrace] = useState<WorkflowTrace | null>(null);

  const refreshDocuments = useCallback(async () => {
    const docs = await api.listDocuments();
    setDocuments(docs);
  }, []);

  const refreshWorkflows = useCallback(async () => {
    const wfs = await api.listWorkflows();
    setWorkflows(wfs);
  }, []);

  useEffect(() => {
    void api.health().then((h) => setProvider(h.provider)).catch(() => {});
    void refreshDocuments();
    void refreshWorkflows();
  }, [refreshDocuments, refreshWorkflows]);

  const handleWorkflowCompleted = (trace: WorkflowTrace) => {
    setLatestTrace(trace);
    void refreshWorkflows();
  };

  const handleSelectWorkflow = async (id: string) => {
    const trace = await api.getWorkflowTrace(id);
    setLatestTrace(trace);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* Top Navigation */}
      <header className="sticky top-0 z-20 border-b border-slate-800 bg-slate-950/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-emerald-500 shadow-lg shadow-indigo-500/20">
              <Cpu className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="text-base font-bold tracking-tight text-white">FlowPilot AI</h1>
              <p className="text-[11px] text-slate-400">
                Tiered Multi-Agent Document Processing &amp; Workflow Orchestrator
              </p>
            </div>
          </div>

          <nav className="flex flex-wrap items-center gap-1">
            {NAV_TABS.map(({ key, label, icon: Icon }) => {
              const active = activeTab === key;
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => setActiveTab(key)}
                  className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                    active
                      ? "bg-indigo-600 text-white shadow"
                      : "text-slate-400 hover:bg-slate-800 hover:text-slate-100"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {label}
                </button>
              );
            })}
          </nav>

          <div className="hidden items-center gap-2 rounded-full border border-slate-800 bg-slate-900 px-3 py-1 text-[11px] text-slate-300 md:flex">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            Provider: <strong className="uppercase text-emerald-300">{provider}</strong>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        {activeTab === "studio" && (
          <StudioPage
            documents={documents}
            onDocumentsChange={refreshDocuments}
            onWorkflowCompleted={handleWorkflowCompleted}
            latestTrace={latestTrace}
          />
        )}
        {activeTab === "trace" && (
          <TracePage
            workflows={workflows}
            selectedTrace={latestTrace}
            onSelectWorkflow={handleSelectWorkflow}
          />
        )}
        {activeTab === "analytics" && <AnalyticsPage />}
        {activeTab === "benchmarks" && <BenchmarksPage />}
        {activeTab === "guardrails" && <GuardrailsPage />}
      </main>
    </div>
  );
};

export default App;
