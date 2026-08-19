"use client";

import { ChangeEvent, useEffect, useState } from "react";
import { apiJson, apiUpload } from "@/lib/api";

type FileItem = { id: string; name: string; mime_type: string; size: number; status: string; created_at: string };

export default function FilesPage() {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [error, setError] = useState("");
  async function load() { try { setFiles(await apiJson<FileItem[]>("/api/v1/files")); } catch (loadError) { setError(String(loadError)); } }
  useEffect(() => { void load(); }, []);
  async function upload(event: ChangeEvent<HTMLInputElement>) { const file = event.target.files?.[0]; if (!file) return; try { await apiUpload<FileItem>("/api/v1/files", file); await load(); } catch (uploadError) { setError(uploadError instanceof Error ? uploadError.message : "上传失败"); } event.target.value = ""; }
  return <main className="management-shell"><header className="management-header"><div><p className="eyebrow">INPUT FILES</p><h1>文件</h1><p className="muted">临时文件不会自动进入知识库。</p></div><label className="primary-button file-button">上传文件<input type="file" onChange={upload} hidden /></label></header>{error ? <p className="form-error" role="alert">{error}</p> : null}<section className="file-grid">{files.map((file) => <article className="capability-card" key={file.id}><span className="capability-label">{file.status}</span><h2>{file.name}</h2><p>{file.mime_type} · {(file.size / 1024).toFixed(1)} KB</p></article>)}</section></main>;
}
