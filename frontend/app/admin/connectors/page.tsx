"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiJson } from "@/lib/api";

type Connector = { id: string; name: string; provider: string; visibility: string; published_version_id: string | null; draft_version_id?: string | null };

export default function ConnectorsPage() {
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [form, setForm] = useState({ name: "", provider: "http", base_url: "", path: "/", endpoint: "", method: "GET", tool_name: "health" });
  const [error, setError] = useState("");
  async function load() { try { setConnectors(await apiJson<Connector[]>("/api/v1/connectors")); } catch (loadError) { setError(loadError instanceof Error ? loadError.message : "加载 Connector 失败"); } }
  useEffect(() => { void load(); }, []);
  async function create(event: FormEvent) {
    event.preventDefault();
    try {
      const spec = form.provider === "mcp"
        ? { endpoint: form.endpoint, allow_private: true }
        : { base_url: form.base_url, path: form.path, method: form.method, allow_private: true, input_schema: { type: "object" }, tools: [{ name: form.tool_name, description: "通过 Connector 调用的操作" }] };
      await apiJson("/api/v1/connectors", { method: "POST", body: JSON.stringify({ name: form.name, provider: form.provider, visibility: "workspace", spec }) });
      setForm({ ...form, name: "" }); await load();
    } catch (createError) { setError(createError instanceof Error ? createError.message : "创建 Connector 失败"); }
  }
  async function test(connector: Connector) { if (!connector.draft_version_id) return; try { await apiJson(`/api/v1/connector-versions/${connector.draft_version_id}/test-runs`, { method: "POST" }); await load(); } catch (testError) { setError(testError instanceof Error ? testError.message : "Connector 测试失败"); } }
  async function publish(connector: Connector) { if (!connector.draft_version_id) return; try { await apiJson(`/api/v1/connector-versions/${connector.draft_version_id}/publish`, { method: "POST" }); await load(); } catch (publishError) { setError(publishError instanceof Error ? publishError.message : "Connector 发布失败"); } }
  return <main className="management-shell"><header className="management-header"><div><p className="eyebrow">ADMIN · CONNECTORS</p><h1>企业连接</h1><p className="muted">HTTP、MCP 和内置能力都先保存为 Draft，测试通过后才能发布。</p></div><a className="secondary-button" href="/admin/members">返回管理</a></header>{error ? <p className="form-error" role="alert">{error}</p> : null}<section className="management-grid"><form className="management-card auth-form" onSubmit={create}><h2>创建 Connector</h2><label htmlFor="connector-name">名称</label><input id="connector-name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required /><label htmlFor="connector-provider">Provider</label><select id="connector-provider" value={form.provider} onChange={(event) => setForm({ ...form, provider: event.target.value })}><option value="http">HTTP API</option><option value="mcp">MCP Streamable HTTP</option><option value="builtin">Builtin</option><option value="sandbox">Trusted Sandbox</option></select>{form.provider === "mcp" ? <><label htmlFor="connector-endpoint">MCP Endpoint</label><input id="connector-endpoint" value={form.endpoint} onChange={(event) => setForm({ ...form, endpoint: event.target.value })} /></> : <><label htmlFor="connector-base-url">Base URL</label><input id="connector-base-url" value={form.base_url} onChange={(event) => setForm({ ...form, base_url: event.target.value })} /><label htmlFor="connector-path">Path</label><input id="connector-path" value={form.path} onChange={(event) => setForm({ ...form, path: event.target.value })} /><label htmlFor="connector-tool">Tool 名称</label><input id="connector-tool" value={form.tool_name} onChange={(event) => setForm({ ...form, tool_name: event.target.value })} /></>}<button className="primary-button" type="submit">保存 Draft</button></form><section className="management-card"><h2>已配置连接</h2><div className="member-list">{connectors.map((connector) => <article className="member-row" key={connector.id}><div><strong>{connector.name}</strong><span>{connector.provider} · {connector.published_version_id ? "Published" : "Draft"}</span></div><div className="row-actions"><button type="button" onClick={() => void test(connector)} disabled={!connector.draft_version_id}>测试</button><button type="button" onClick={() => void publish(connector)} disabled={!connector.draft_version_id}>发布</button></div></article>)}</div></section></section></main>;
}
