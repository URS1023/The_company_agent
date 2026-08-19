"use client";

import { useEffect, useState } from "react";
import { apiJson } from "@/lib/api";

type Plugin = { id: string; name: string; description: string; visibility: string; published_version_id: string | null };

export default function PluginsPage() {
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { void apiJson<Plugin[]>("/api/v1/plugins").then(setPlugins).catch((loadError) => setError(String(loadError))); }, []);
  return <main className="management-shell"><header className="management-header"><div><p className="eyebrow">CAPABILITIES</p><h1>插件</h1><p className="muted">每个插件都固定引用 Skill、Connector 和 Resource 的版本。</p></div><a className="secondary-button" href="/chat">返回 Chat</a></header>{error ? <p className="form-error" role="alert">{error}</p> : null}<section className="file-grid">{plugins.map((plugin) => <article className="capability-card" key={plugin.id}><span className="capability-label">{plugin.published_version_id ? "Published" : "Draft"} · {plugin.visibility}</span><h2>{plugin.name}</h2><p>{plugin.description || "暂无说明"}</p><button className="secondary-button" type="button">查看版本</button></article>)}</section></main>;
}
