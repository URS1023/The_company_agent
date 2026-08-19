"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiJson } from "@/lib/api";

type Member = { id: string; username: string; display_name: string; status: string; must_change_password: boolean };
type Created = { user: Member; temporary_password: string };

export default function MembersPage() {
  const [members, setMembers] = useState<Member[]>([]);
  const [form, setForm] = useState({ username: "", display_name: "", role: "member" });
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState("");

  async function load() {
    try { setMembers(await apiJson<Member[]>("/api/v1/admin/users")); } catch (loadError) { setError(String(loadError)); }
  }
  useEffect(() => { void load(); }, []);

  async function create(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const result = await apiJson<Created>("/api/v1/admin/users", { method: "POST", body: JSON.stringify(form) });
      setNewPassword(`登录名：${result.user.username}\n临时密码：${result.temporary_password}`);
      setForm({ username: "", display_name: "", role: "member" });
      await load();
    } catch (createError) { setError(createError instanceof Error ? createError.message : "创建失败"); }
  }

  async function disable(member: Member) {
    try { await apiJson(`/api/v1/admin/users/${member.id}`, { method: "PATCH", body: JSON.stringify({ status: "disabled" }) }); await load(); }
    catch (disableError) { setError(disableError instanceof Error ? disableError.message : "停用失败"); }
  }

  async function reset(member: Member) {
    try {
      const result = await apiJson<Created>(`/api/v1/admin/users/${member.id}/reset-password`, { method: "POST" });
      setNewPassword(`登录名：${result.user.username}\n临时密码：${result.temporary_password}`);
      await load();
    } catch (resetError) { setError(resetError instanceof Error ? resetError.message : "重置失败"); }
  }

  return (
    <main className="management-shell">
      <header className="management-header"><div><p className="eyebrow">WORKSPACE ADMIN</p><h1>成员与权限</h1><p className="muted">账号由管理员创建；密码只在创建或重置时显示一次。</p></div><div className="row-actions"><a className="secondary-button" href="/admin/secrets">Secret</a><a className="secondary-button" href="/admin/models">模型</a><a className="secondary-button" href="/admin/audit">审计</a><a className="secondary-button" href="/chat">返回 Chat</a></div></header>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      {newPassword ? <pre className="one-time-secret" role="status">{newPassword}</pre> : null}
      <section className="management-grid">
        <form className="management-card auth-form" onSubmit={create}>
          <h2>创建成员</h2>
          <label htmlFor="member-username">登录名</label><input id="member-username" value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} required />
          <label htmlFor="member-name">显示名称</label><input id="member-name" value={form.display_name} onChange={(event) => setForm({ ...form, display_name: event.target.value })} required />
          <label htmlFor="member-role">角色</label><select id="member-role" value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })}><option value="member">Member</option><option value="admin">Admin</option></select>
          <button className="primary-button" type="submit">创建账号</button>
        </form>
        <section className="management-card"><h2>当前成员</h2><div className="member-list">{members.map((member) => <article className="member-row" key={member.id}><div><strong>{member.display_name}</strong><span>{member.username} · {member.status}</span></div><div className="row-actions"><button type="button" onClick={() => void reset(member)}>重置密码</button><button type="button" onClick={() => void disable(member)} disabled={member.status === "disabled"}>停用</button></div></article>)}</div></section>
      </section>
    </main>
  );
}
