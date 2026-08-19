"use client";

import { useEffect, useState } from "react";
import { apiJson } from "@/lib/api";

type Profile = { profile: string; provider: string; model: string; configured: boolean; enabled: boolean; dimensions?: number };
export default function ModelsPage() {
  const [profiles, setProfiles] = useState<Profile[]>([]); const [message, setMessage] = useState("");
  useEffect(() => { void apiJson<Profile[]>("/api/v1/admin/model-profiles").then(setProfiles).catch((error) => setMessage(error instanceof Error ? error.message : "加载模型配置失败")); }, []);
  async function probe(profile: string) { try { const result = await apiJson<{ status: string }>(`/api/v1/admin/model-profiles/${profile}/probe`, { method: "POST" }); setMessage(`${profile}：${result.status}`); } catch (error) { setMessage(error instanceof Error ? error.message : "Probe 失败"); } }
  return <main className="management-shell"><header className="management-header"><div><p className="eyebrow">ADMIN · MODEL PROFILES</p><h1>模型配置</h1><p className="muted">Chat、Vision 和 Embedding 分离配置；Key 只通过本地环境或 Secret 注入。</p></div><a className="secondary-button" href="/admin/members">返回管理</a></header>{message ? <p className="form-error" role="status">{message}</p> : null}<section className="file-grid">{profiles.map((profile) => <article className="capability-card" key={profile.profile}><span className="capability-label">{profile.profile}</span><h2>{profile.model}</h2><p>{profile.provider} · {profile.configured ? "已配置 Key" : "未配置 Key"} · {profile.enabled ? "已启用" : "未启用"}{profile.dimensions ? ` · ${profile.dimensions} 维` : ""}</p><button type="button" onClick={() => void probe(profile.profile)}>安全 Probe</button></article>)}</section></main>;
}
