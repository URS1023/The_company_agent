"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiJson } from "@/lib/api";

type KnowledgeBase = { id: string; name: string; description: string; visibility: string; status: string };
type FileItem = { id: string; name: string; status: string };
type Document = { id: string; file_id: string; status: string; chunk_count: number; error_summary: string | null };

export default function KnowledgePage() {
  const [bases, setBases] = useState<KnowledgeBase[]>([]);
  const [files, setFiles] = useState<FileItem[]>([]);
  const [documents, setDocuments] = useState<Record<string, Document[]>>({});
  const [name, setName] = useState("");
  const [selectedBase, setSelectedBase] = useState<string | null>(null);
  const [selectedFileId, setSelectedFileId] = useState("");
  const [error, setError] = useState("");
  async function load() {
    try {
      const [nextBases, nextFiles] = await Promise.all([apiJson<KnowledgeBase[]>("/api/v1/knowledge-bases"), apiJson<FileItem[]>("/api/v1/files")]);
      setBases(nextBases); setFiles(nextFiles);
      await Promise.all(nextBases.map(async (base) => {
        const nextDocuments = await apiJson<Document[]>(`/api/v1/knowledge-bases/${base.id}/documents`);
        setDocuments((current) => ({ ...current, [base.id]: nextDocuments }));
      }));
    } catch (loadError) { setError(loadError instanceof Error ? loadError.message : "加载知识库失败"); }
  }
  useEffect(() => { void load(); }, []);
  async function create(event: FormEvent) { event.preventDefault(); try { await apiJson("/api/v1/knowledge-bases", { method: "POST", body: JSON.stringify({ name, visibility: "private" }) }); setName(""); await load(); } catch (createError) { setError(createError instanceof Error ? createError.message : "创建失败"); } }
  async function addDocument(baseId: string) {
    if (!selectedFileId) return;
    try { await apiJson(`/api/v1/knowledge-bases/${baseId}/documents`, { method: "POST", body: JSON.stringify({ file_id: selectedFileId }) }); setSelectedFileId(""); await load(); }
    catch (addError) { setError(addError instanceof Error ? addError.message : "加入知识库失败"); }
  }
  async function reindex(baseId: string) {
    try { await apiJson(`/api/v1/knowledge-bases/${baseId}/reindex`, { method: "POST" }); await load(); }
    catch (reindexError) { setError(reindexError instanceof Error ? reindexError.message : "重建索引失败"); }
  }
  return <main className="management-shell"><header className="management-header"><div><p className="eyebrow">KNOWLEDGE</p><h1>知识库</h1><p className="muted">只有显式加入的文件才会被索引，处理状态与缺失原因会在这里显示。</p></div><a className="secondary-button" href="/chat">返回 Chat</a></header>{error ? <p className="form-error" role="alert">{error}</p> : null}<form className="inline-create" onSubmit={create}><input aria-label="知识库名称" placeholder="新知识库名称" value={name} onChange={(event) => setName(event.target.value)} required /><button className="primary-button" type="submit">创建知识库</button></form><section className="file-grid">{bases.map((base) => <article className="capability-card" key={base.id}><span className="capability-label">{base.visibility} · {base.status}</span><h2>{base.name}</h2><p>{base.description || "等待添加文档"}</p><div className="context-chips"><select aria-label={`选择 ${base.name} 的文件`} value={selectedBase === base.id ? selectedFileId : ""} onChange={(event) => { setSelectedBase(base.id); setSelectedFileId(event.target.value); }}><option value="">选择已上传文件</option>{files.filter((file) => file.status === "ready").map((file) => <option value={file.id} key={file.id}>{file.name}</option>)}</select><button type="button" onClick={() => void addDocument(base.id)} disabled={selectedBase !== base.id || !selectedFileId}>加入知识库</button><button type="button" onClick={() => void reindex(base.id)}>重建索引</button></div><div className="member-list">{(documents[base.id] ?? []).map((document) => <div className="member-row" key={document.id}><span>{document.file_id}</span><span>{document.status} · {document.chunk_count} chunks{document.error_summary ? ` · ${document.error_summary}` : ""}</span></div>)}</div></article>)}</section></main>;
}
