"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiJson } from "@/lib/api";

type KnowledgeBase = { id: string; name: string; description: string; visibility: string; status: string };

export default function KnowledgePage() {
  const [bases, setBases] = useState<KnowledgeBase[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  async function load() { try { setBases(await apiJson<KnowledgeBase[]>("/api/v1/knowledge-bases")); } catch (loadError) { setError(String(loadError)); } }
  useEffect(() => { void load(); }, []);
  async function create(event: FormEvent) { event.preventDefault(); try { await apiJson("/api/v1/knowledge-bases", { method: "POST", body: JSON.stringify({ name, visibility: "private" }) }); setName(""); await load(); } catch (createError) { setError(createError instanceof Error ? createError.message : "创建失败"); } }
  return <main className="management-shell"><header className="management-header"><div><p className="eyebrow">KNOWLEDGE</p><h1>知识库</h1><p className="muted">只有显式加入的文件才会被索引。</p></div><a className="secondary-button" href="/chat">返回 Chat</a></header>{error ? <p className="form-error" role="alert">{error}</p> : null}<form className="inline-create" onSubmit={create}><input aria-label="知识库名称" placeholder="新知识库名称" value={name} onChange={(event) => setName(event.target.value)} required /><button className="primary-button" type="submit">创建知识库</button></form><section className="file-grid">{bases.map((base) => <article className="capability-card" key={base.id}><span className="capability-label">{base.visibility} · {base.status}</span><h2>{base.name}</h2><p>{base.description || "等待添加文档"}</p></article>)}</section></main>;
}
