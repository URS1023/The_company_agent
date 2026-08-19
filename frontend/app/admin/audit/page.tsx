"use client";

import { useEffect, useState } from "react";
import { apiJson } from "@/lib/api";

type Audit = { id: string; action: string; resource_type: string; resource_id: string | null; actor_user_id: string | null; created_at: string; metadata_json: Record<string, unknown> };

export default function AuditPage() {
  const [rows, setRows] = useState<Audit[]>([]); const [error, setError] = useState("");
  useEffect(() => { void apiJson<Audit[]>("/api/v1/admin/audit-logs").then(setRows).catch((loadError) => setError(loadError instanceof Error ? loadError.message : "加载审计失败")); }, []);
  return <main className="management-shell"><header className="management-header"><div><p className="eyebrow">ADMIN · AUDIT</p><h1>审计日志</h1><p className="muted">只记录资源动作和非敏感元数据，不记录密码、Token 或 Secret 值。</p></div><a className="secondary-button" href="/admin/members">返回管理</a></header>{error ? <p className="form-error" role="alert">{error}</p> : null}<section className="management-card"><div className="member-list">{rows.map((row) => <article className="member-row" key={row.id}><div><strong>{row.action} · {row.resource_type}</strong><span>{row.resource_id ?? ""} · {new Date(row.created_at).toLocaleString()}</span></div><details><summary>元数据</summary><pre>{JSON.stringify(row.metadata_json, null, 2)}</pre></details></article>)}</div></section></main>;
}
