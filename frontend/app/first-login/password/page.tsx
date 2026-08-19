"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { apiJson } from "@/lib/api";

export default function FirstLoginPasswordPage() {
  const router = useRouter();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (newPassword.length < 12) {
      setError("新密码至少需要 12 个字符");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await apiJson("/api/v1/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword })
      });
      router.push("/chat");
    } catch (submissionError) {
      setError(submissionError instanceof Error ? submissionError.message : "修改密码失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card" aria-labelledby="password-title">
        <div className="brand-lockup"><span className="brand-mark">CA</span><span>企业 AI 工作台</span></div>
        <h1 id="password-title">设置你的工作区密码</h1>
        <p className="muted">这是管理员提供的临时密码。修改后才能进入工作区。</p>
        <form className="auth-form" onSubmit={submit}>
          <label htmlFor="current-password">当前密码</label>
          <input id="current-password" type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required />
          <label htmlFor="new-password">新密码（至少 12 个字符）</label>
          <input id="new-password" type="password" autoComplete="new-password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required />
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          <button className="primary-button wide" type="submit" disabled={busy}>{busy ? "正在保存…" : "保存并进入工作区"}</button>
        </form>
      </section>
    </main>
  );
}
