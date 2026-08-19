"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiJson } from "@/lib/api";

type DataSource = { id: string; name: string; provider: string; status: string; secret_id: string | null; connection_config: Record<string, string> };
type Secret = { id: string; name: string; provider: string; status: string };

export default function DataSourcesPage() {
  const [sources, setSources] = useState<DataSource[]>([]);
  const [secrets, setSecrets] = useState<Secret[]>([]);
  const [form, setForm] = useState({ name: "", provider: "mysql", host: "127.0.0.1", port: "3306", database: "", username: "", secret_id: "" });
  const [error, setError] = useState("");
  async function load() { try { const [nextSources, nextSecrets] = await Promise.all([apiJson<DataSource[]>("/api/v1/data-sources"), apiJson<Secret[]>("/api/v1/secrets")]); setSources(nextSources); setSecrets(nextSecrets); } catch (loadError) { setError(loadError instanceof Error ? loadError.message : "加载数据源失败"); } }
  useEffect(() => { void load(); }, []);
  async function create(event: FormEvent) {
    event.preventDefault();
    try { await apiJson("/api/v1/data-sources", { method: "POST", body: JSON.stringify({ name: form.name, provider: form.provider, secret_id: form.secret_id || null, connection_config: { host: form.host, port: form.port, database: form.database, username: form.username } }) }); setForm({ ...form, name: "", database: "" }); await load(); }
    catch (createError) { setError(createError instanceof Error ? createError.message : "创建数据源失败"); }
  }
  async function test(source: DataSource) { try { await apiJson(`/api/v1/data-sources/${source.id}/test-connection`, { method: "POST" }); await load(); } catch (testError) { setError(testError instanceof Error ? testError.message : "连接测试失败"); } }
  async function remove(source: DataSource) { try { await apiJson(`/api/v1/data-sources/${source.id}`, { method: "DELETE" }); await load(); } catch (removeError) { setError(removeError instanceof Error ? removeError.message : "删除数据源失败"); } }
  return <main className="management-shell"><header className="management-header"><div><p className="eyebrow">DATA SOURCES</p><h1>数据源</h1><p className="muted">连接配置不保存密码；凭据只通过 Secret 引用，数据库工具默认只读。</p></div><a className="secondary-button" href="/chat">返回 Chat</a></header>{error ? <p className="form-error" role="alert">{error}</p> : null}<section className="management-grid"><form className="management-card auth-form" onSubmit={create}><h2>添加只读数据库</h2><label htmlFor="source-name">名称</label><input id="source-name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required /><label htmlFor="source-provider">Provider</label><select id="source-provider" value={form.provider} onChange={(event) => setForm({ ...form, provider: event.target.value })}><option value="mysql">MySQL</option><option value="postgresql">PostgreSQL</option></select><label htmlFor="source-host">Host</label><input id="source-host" value={form.host} onChange={(event) => setForm({ ...form, host: event.target.value })} required /><label htmlFor="source-port">Port</label><input id="source-port" value={form.port} onChange={(event) => setForm({ ...form, port: event.target.value })} required /><label htmlFor="source-database">Database</label><input id="source-database" value={form.database} onChange={(event) => setForm({ ...form, database: event.target.value })} required /><label htmlFor="source-username">Username</label><input id="source-username" value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} required /><label htmlFor="source-secret">Secret</label><select id="source-secret" value={form.secret_id} onChange={(event) => setForm({ ...form, secret_id: event.target.value })}><option value="">选择 Secret</option>{secrets.filter((secret) => secret.provider === "database").map((secret) => <option value={secret.id} key={secret.id}>{secret.name}</option>)}</select><button className="primary-button" type="submit">保存数据源</button></form><section className="management-card"><h2>已配置数据源</h2><div className="member-list">{sources.map((source) => <article className="member-row" key={source.id}><div><strong>{source.name}</strong><span>{source.provider} · {source.status}</span></div><div className="row-actions"><button type="button" onClick={() => void test(source)}>测试连接</button><button type="button" onClick={() => void remove(source)}>归档</button></div></article>)}</div></section></section></main>;
}
