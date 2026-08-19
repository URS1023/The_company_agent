"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { apiJson } from "@/lib/api";

type Run = { id: string; status: string; error_code: string | null; error_summary: string | null; created_at: string; completed_at: string | null };
type Step = { id: string; sequence: number; name: string; step_type: string; status: string; error_summary: string | null; started_at: string | null; completed_at: string | null };
type ToolCall = { id: string; tool_name: string; status: string; arguments_json: Record<string, unknown>; result_json: Record<string, unknown> | null };
type Diagnosis = { category: string; owner: string; next_action: string };

export default function RunTracePage() {
  const params = useParams<{ runId: string }>();
  const runId = params.runId;
  const [run, setRun] = useState<Run | null>(null);
  const [steps, setSteps] = useState<Step[]>([]);
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [diagnosis, setDiagnosis] = useState<Diagnosis | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [nextRun, nextSteps, nextToolCalls] = await Promise.all([
        apiJson<Run>(`/api/v1/runs/${runId}`),
        apiJson<Step[]>(`/api/v1/runs/${runId}/steps`),
        apiJson<ToolCall[]>(`/api/v1/runs/${runId}/tool-calls`)
      ]);
      setRun(nextRun); setSteps(nextSteps); setToolCalls(nextToolCalls);
      if (["failed", "cancelled"].includes(nextRun.status)) {
        const report = await apiJson<{ diagnosis: Diagnosis | null }>(`/api/v1/runs/${runId}/diagnosis`);
        setDiagnosis(report.diagnosis);
      }
    } catch (loadError) { setError(loadError instanceof Error ? loadError.message : "加载 Run 失败"); }
  }, [runId]);

  useEffect(() => { void load(); }, [load]);

  async function cancel() {
    try { await apiJson(`/api/v1/runs/${runId}/cancel`, { method: "POST" }); await load(); }
    catch (actionError) { setError(actionError instanceof Error ? actionError.message : "取消失败"); }
  }

  async function retry() {
    try { await apiJson(`/api/v1/runs/${runId}/retry`, { method: "POST" }); await load(); }
    catch (actionError) { setError(actionError instanceof Error ? actionError.message : "重试失败"); }
  }

  return <main className="management-shell">
    <header className="management-header"><div><p className="eyebrow">RUN TRACE</p><h1>执行详情</h1><p className="muted">输入来源、模型调用、工具步骤和输出都绑定到同一 Run。</p></div><a className="secondary-button" href="/chat">返回 Chat</a></header>
    {error ? <p className="form-error" role="alert">{error}</p> : null}
    {run ? <section className="management-card run-summary"><span className="capability-label">{run.status}</span><p>Run ID：{run.id}</p>{run.error_summary ? <p className="form-error">{run.error_code} · {run.error_summary}</p> : null}{diagnosis ? <p>归属：{diagnosis.category} · {diagnosis.next_action}</p> : null}<div className="row-actions">{["queued", "running"].includes(run.status) ? <button type="button" onClick={() => void cancel()}>取消 Run</button> : null}{["failed", "cancelled"].includes(run.status) ? <button type="button" onClick={() => void retry()}>重试</button> : null}</div></section> : null}
    <section className="management-grid"><div className="management-card"><h2>执行步骤</h2><div className="member-list">{steps.length ? steps.map((step) => <article className="member-row" key={step.id}><div><strong>{step.sequence}. {step.name}</strong><span>{step.step_type} · {step.status}</span></div><span className="muted">{step.error_summary ?? ""}</span></article>) : <p className="muted">尚未产生步骤。</p>}</div></div><div className="management-card"><h2>Tool 调用</h2><div className="member-list">{toolCalls.length ? toolCalls.map((call) => <article className="member-row" key={call.id}><div><strong>{call.tool_name}</strong><span>{call.status}</span></div><details><summary>查看参数</summary><pre>{JSON.stringify(call.arguments_json, null, 2)}</pre></details></article>) : <p className="muted">本次 Run 没有 Tool 调用。</p>}</div></div></section>
  </main>;
}
