"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiJson } from "@/lib/api";

type Plugin = {
  id: string;
  name: string;
  description: string;
  visibility: string;
  published_version_id: string | null;
  draft_version_id?: string | null;
};

export default function PluginsPage() {
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setPlugins(await apiJson<Plugin[]>("/api/v1/plugins"));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载插件失败");
    }
  }

  useEffect(() => { void load(); }, []);

  async function createAndPublish(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const plugin = await apiJson<Plugin>("/api/v1/plugins", {
        method: "POST",
        body: JSON.stringify({
          name,
          description: "从管理界面创建的可复用能力",
          visibility: "private",
          spec: {}
        })
      });
      if (!plugin.draft_version_id) throw new Error("服务端没有返回 Draft Version");
      await apiJson(`/api/v1/plugin-versions/${plugin.draft_version_id}/test-runs`, { method: "POST" });
      await apiJson(`/api/v1/plugin-versions/${plugin.draft_version_id}/publish`, { method: "POST" });
      setName("");
      await load();
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "创建插件失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="management-shell">
      <header className="management-header">
        <div><p className="eyebrow">CAPABILITIES</p><h1>插件</h1><p className="muted">每个插件都固定引用 Skill、Connector 和 Resource 的版本。</p></div>
        <a className="secondary-button" href="/chat">返回 Chat</a>
      </header>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      <form className="inline-create" onSubmit={createAndPublish}>
        <input aria-label="插件名称" placeholder="新插件名称" value={name} onChange={(event) => setName(event.target.value)} required />
        <button className="primary-button" type="submit" disabled={busy}>{busy ? "测试并发布…" : "创建并发布"}</button>
      </form>
      <section className="file-grid">
        {plugins.map((plugin) => <article className="capability-card" key={plugin.id}>
          <span className="capability-label">{plugin.published_version_id ? "Published" : "Draft"} · {plugin.visibility}</span>
          <h2>{plugin.name}</h2>
          <p>{plugin.description || "暂无说明"}</p>
          <p className="muted">{plugin.published_version_id ? "可在 Chat 中使用" : "等待测试"}</p>
        </article>)}
      </section>
    </main>
  );
}
