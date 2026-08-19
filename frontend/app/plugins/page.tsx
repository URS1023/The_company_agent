"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiJson } from "@/lib/api";

type Plugin = { id: string; name: string; description: string; visibility: string; published_version_id: string | null; draft_version_id?: string | null };
type Skill = { id: string; name: string; published_version_id: string | null };
type Connector = { id: string; name: string; provider: string };
type Tool = { id: string; name: string; connector_id: string; published_version_id: string | null };

export default function PluginsPage() {
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [tools, setTools] = useState<Tool[]>([]);
  const [form, setForm] = useState({ name: "", skill_version_id: "", tool_version_id: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const [nextPlugins, nextSkills, nextConnectors] = await Promise.all([
        apiJson<Plugin[]>("/api/v1/plugins"),
        apiJson<Skill[]>("/api/v1/skills"),
        apiJson<Connector[]>("/api/v1/connectors")
      ]);
      setPlugins(nextPlugins); setSkills(nextSkills);
      const connectorTools = await Promise.all(nextConnectors.map((connector) => apiJson<Tool[]>(`/api/v1/connectors/${connector.id}/tools`).catch(() => [])));
      setTools(connectorTools.flat());
    } catch (loadError) { setError(loadError instanceof Error ? loadError.message : "加载能力失败"); }
  }

  useEffect(() => { void load(); }, []);

  async function createAndPublish(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      const plugin = await apiJson<Plugin>("/api/v1/plugins", { method: "POST", body: JSON.stringify({ name: form.name, description: "从管理界面创建的可复用能力", visibility: "private", spec: {} }) });
      if (!plugin.draft_version_id) throw new Error("服务端没有返回 Draft Version");
      await apiJson(`/api/v1/plugin-versions/${plugin.draft_version_id}/bindings`, { method: "POST", body: JSON.stringify({ skill_version_ids: form.skill_version_id ? [form.skill_version_id] : [], tool_version_ids: form.tool_version_id ? [form.tool_version_id] : [], resources: [] }) });
      await apiJson(`/api/v1/plugin-versions/${plugin.draft_version_id}/test-runs`, { method: "POST" });
      await apiJson(`/api/v1/plugin-versions/${plugin.draft_version_id}/publish`, { method: "POST" });
      setForm({ name: "", skill_version_id: "", tool_version_id: "" }); await load();
    } catch (createError) { setError(createError instanceof Error ? createError.message : "创建插件失败"); }
    finally { setBusy(false); }
  }

  async function clone(plugin: Plugin) { try { await apiJson(`/api/v1/plugins/${plugin.id}/clone`, { method: "POST" }); await load(); } catch (cloneError) { setError(cloneError instanceof Error ? cloneError.message : "复制插件失败"); } }
  async function share(plugin: Plugin) { try { await apiJson(`/api/v1/plugins/${plugin.id}/share`, { method: "POST", body: JSON.stringify({ visibility: plugin.visibility === "workspace" ? "private" : "workspace" }) }); await load(); } catch (shareError) { setError(shareError instanceof Error ? shareError.message : "分享插件失败"); } }

  return <main className="management-shell"><header className="management-header"><div><p className="eyebrow">CAPABILITIES</p><h1>插件</h1><p className="muted">每个插件都固定引用 Skill、Connector 和 Resource 的版本。</p></div><a className="secondary-button" href="/chat">返回 Chat</a></header>{error ? <p className="form-error" role="alert">{error}</p> : null}<form className="management-card auth-form" onSubmit={createAndPublish}><h2>创建可复用能力</h2><label htmlFor="plugin-name">插件名称</label><input id="plugin-name" aria-label="插件名称" placeholder="新插件名称" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required /><label htmlFor="plugin-skill">绑定已发布 Skill（可选）</label><select id="plugin-skill" value={form.skill_version_id} onChange={(event) => setForm({ ...form, skill_version_id: event.target.value })}><option value="">不绑定 Skill</option>{skills.filter((skill) => skill.published_version_id).map((skill) => <option value={skill.published_version_id ?? ""} key={skill.id}>{skill.name}</option>)}</select><label htmlFor="plugin-tool">绑定已发布 Tool（可选）</label><select id="plugin-tool" value={form.tool_version_id} onChange={(event) => setForm({ ...form, tool_version_id: event.target.value })}><option value="">不绑定 Tool</option>{tools.filter((tool) => tool.published_version_id).map((tool) => <option value={tool.published_version_id ?? ""} key={tool.id}>{tool.name}</option>)}</select><button className="primary-button" type="submit" disabled={busy}>{busy ? "测试并发布…" : "创建并发布"}</button></form><section className="file-grid">{plugins.map((plugin) => <article className="capability-card" key={plugin.id}><span className="capability-label">{plugin.published_version_id ? "Published" : "Draft"} · {plugin.visibility}</span><h2>{plugin.name}</h2><p>{plugin.description || "暂无说明"}</p><p className="muted">{plugin.published_version_id ? "可在 Chat 中使用" : "等待测试"}</p><div className="row-actions"><button type="button" onClick={() => void clone(plugin)}>复制</button>{plugin.published_version_id ? <button type="button" onClick={() => void share(plugin)}>{plugin.visibility === "workspace" ? "取消分享" : "分享给 Workspace"}</button> : null}<a href={`/chat?plugin=${plugin.published_version_id ?? ""}`}>运行</a></div></article>)}</section></main>;
}
