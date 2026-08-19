"use client";

import { FormEvent, useState } from "react";
import { apiJson } from "@/lib/api";

export default function ProfilePage() {
  const [currentPassword, setCurrentPassword] = useState(""); const [newPassword, setNewPassword] = useState(""); const [message, setMessage] = useState("");
  async function change(event: FormEvent) { event.preventDefault(); try { await apiJson("/api/v1/auth/change-password", { method: "POST", body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) }); setCurrentPassword(""); setNewPassword(""); setMessage("密码已更新，旧会话已失效。"); } catch (error) { setMessage(error instanceof Error ? error.message : "修改密码失败"); } }
  async function logout() { await apiJson("/api/v1/auth/logout", { method: "POST" }); window.location.href = "/login"; }
  return <main className="management-shell"><header className="management-header"><div><p className="eyebrow">PROFILE</p><h1>个人设置</h1><p className="muted">修改密码会轮换当前 Session，并撤销旧的认证凭据。</p></div><a className="secondary-button" href="/chat">返回 Chat</a></header>{message ? <p className="form-error" role="status">{message}</p> : null}<section className="management-card auth-form"><h2>修改密码</h2><form onSubmit={change}><label htmlFor="profile-current">当前密码</label><input id="profile-current" type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required /><label htmlFor="profile-new">新密码（至少 12 个字符）</label><input id="profile-new" type="password" minLength={12} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required /><button className="primary-button" type="submit">保存密码</button></form><button type="button" onClick={() => void logout()}>退出登录</button></section></main>;
}
