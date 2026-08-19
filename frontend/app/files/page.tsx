"use client";

import { ChangeEvent, useEffect, useState } from "react";
import { apiJson, apiUploadMany } from "@/lib/api";

type FileItem = { id: string; name: string; mime_type: string; size: number; status: string; created_at: string };
type Artifact = { id: string; name: string; type: string; mime_type: string; size: number; status: string; run_id: string; created_at: string };

export default function FilesPage() {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [error, setError] = useState("");
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [tab, setTab] = useState<"files" | "artifacts">("files");
  async function load() { try { const [nextFiles, nextArtifacts] = await Promise.all([apiJson<FileItem[]>("/api/v1/files"), apiJson<Artifact[]>("/api/v1/artifacts")]); setFiles(nextFiles); setArtifacts(nextArtifacts); } catch (loadError) { setError(String(loadError)); } }
  useEffect(() => { void load(); }, []);
  async function upload(event: ChangeEvent<HTMLInputElement>) { const selected = Array.from(event.target.files ?? []); if (!selected.length) return; try { await apiUploadMany<FileItem[]>("/api/v1/files/batch", selected); await load(); } catch (uploadError) { setError(uploadError instanceof Error ? uploadError.message : "上传失败"); } event.target.value = ""; }
  return <main className="management-shell"><header className="management-header"><div><p className="eyebrow">INPUT FILES</p><h1>文件</h1><p className="muted">临时文件不会自动进入知识库；Artifact 可预览、下载并继续作为下一次输入。</p></div><label className="primary-button file-button">上传文件<input type="file" multiple onChange={upload} hidden /></label></header>{error ? <p className="form-error" role="alert">{error}</p> : null}<div className="context-chips"><button type="button" className={tab === "files" ? "active-chip" : ""} onClick={() => setTab("files")}>输入文件</button><button type="button" className={tab === "artifacts" ? "active-chip" : ""} onClick={() => setTab("artifacts")}>Artifacts</button></div>{tab === "files" ? <section className="file-grid">{files.map((file) => <article className="capability-card" key={file.id}><span className="capability-label">{file.status}</span><h2>{file.name}</h2><p>{file.mime_type} · {(file.size / 1024).toFixed(1)} KB</p></article>)}</section> : <section className="file-grid">{artifacts.map((artifact) => <article className="capability-card" key={artifact.id}><span className="capability-label">{artifact.type} · {artifact.status}</span><h2>{artifact.name}</h2><p>{artifact.mime_type} · {(artifact.size / 1024).toFixed(1)} KB</p><div className="row-actions"><a href={`/api/v1/artifacts/${artifact.id}/preview`}>预览</a><a href={`/api/v1/artifacts/${artifact.id}/download`}>下载</a></div></article>)}</section>}</main>;
}
