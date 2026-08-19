"use client";

import { useEffect, useState } from "react";
import { apiJson } from "@/lib/api";

type DataSource = { id: string; name: string; provider: string; status: string; secret_id: string | null };

export default function DataSourcesPage() {
  const [sources, setSources] = useState<DataSource[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { void apiJson<DataSource[]>("/api/v1/data-sources").then(setSources).catch((loadError) => setError(String(loadError))); }, []);
  return <main className="management-shell"><header className="management-header"><div><p className="eyebrow">DATA SOURCES</p><h1>数据源</h1><p className="muted">连接配置不保存密码；凭据只通过 Secret 引用。</p></div><a className="secondary-button" href="/chat">返回 Chat</a></header>{error ? <p className="form-error" role="alert">{error}</p> : null}<section className="file-grid">{sources.map((source) => <article className="capability-card" key={source.id}><span className="capability-label">{source.provider} · {source.status}</span><h2>{source.name}</h2><p>{source.secret_id ? "已绑定 Secret" : "缺少 Secret"}</p></article>)}</section></main>;
}
