"use client";

import { ChangeEvent, useEffect, useState } from "react";
import { apiJson, apiUploadMany } from "@/lib/api";

type FileItem = {
  id: string;
  name: string;
  mime_type: string;
  size: number;
  status: string;
  created_at: string;
};
type Artifact = {
  id: string;
  name: string;
  type: string;
  mime_type: string;
  size: number;
  status: string;
  run_id: string;
  created_at: string;
};

export default function FilesPage() {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"files" | "artifacts">("files");
  const [inputArtifactId, setInputArtifactId] = useState("");

  async function load() {
    try {
      const [nextFiles, nextArtifacts] = await Promise.all([
        apiJson<FileItem[]>("/api/v1/files"),
        apiJson<Artifact[]>("/api/v1/artifacts")
      ]);
      setFiles(nextFiles);
      setArtifacts(nextArtifacts);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载文件失败");
    }
  }

  useEffect(() => { void load(); }, []);
  useEffect(() => { if (window.location.search.includes("tab=artifacts")) setTab("artifacts"); }, []);

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(event.target.files ?? []);
    if (!selected.length) return;
    try {
      await apiUploadMany<FileItem[]>("/api/v1/files/batch", selected);
      await load();
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "上传失败");
    }
    event.target.value = "";
  }

  async function continueArtifact(artifactId: string) {
    try {
      await apiJson(`/api/v1/artifacts/${artifactId}/use-as-input`, { method: "POST" });
      setInputArtifactId(artifactId);
    } catch (useError) {
      setError(useError instanceof Error ? useError.message : "Artifact 输入引用失败");
    }
  }

  return (
    <main className="management-shell">
      <header className="management-header">
        <div>
          <p className="eyebrow">INPUT FILES</p>
          <h1>文件</h1>
          <p className="muted">临时文件不会自动进入知识库；Artifact 可预览、下载并继续作为下一次输入。</p>
        </div>
        <label className="primary-button file-button">
          上传文件
          <input type="file" multiple onChange={upload} hidden />
        </label>
      </header>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      {inputArtifactId ? <p className="form-error" role="status">已选择 Artifact：{inputArtifactId}；进入 Chat 后可继续处理。</p> : null}
      <div className="context-chips">
        <button type="button" className={tab === "files" ? "active-chip" : ""} onClick={() => setTab("files")}>输入文件</button>
        <button type="button" className={tab === "artifacts" ? "active-chip" : ""} onClick={() => setTab("artifacts")}>Artifacts</button>
      </div>
      {tab === "files" ? (
        <section className="file-grid">
          {files.map((file) => <article className="capability-card" key={file.id}><span className="capability-label">{file.status}</span><h2>{file.name}</h2><p>{file.mime_type} · {(file.size / 1024).toFixed(1)} KB</p></article>)}
        </section>
      ) : (
        <section className="file-grid">
          {artifacts.map((artifact) => <article className="capability-card" key={artifact.id}><span className="capability-label">{artifact.type} · {artifact.status}</span><h2>{artifact.name}</h2><p>{artifact.mime_type} · {(artifact.size / 1024).toFixed(1)} KB</p><div className="row-actions"><a href={`/api/v1/artifacts/${artifact.id}/preview`}>预览</a><a href={`/api/v1/artifacts/${artifact.id}/download`}>下载</a><button type="button" onClick={() => void continueArtifact(artifact.id)}>继续使用</button></div></article>)}
        </section>
      )}
    </main>
  );
}
