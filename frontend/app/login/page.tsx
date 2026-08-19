"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ username, password })
      });
      if (!response.ok) throw new Error("账号或密码不正确");
      router.push("/chat");
    } catch (submissionError) {
      setError(submissionError instanceof Error ? submissionError.message : "登录失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card" aria-labelledby="login-title">
        <div className="brand-lockup"><span className="brand-mark">CA</span><span>企业 AI 工作台</span></div>
        <h1 id="login-title">登录工作区</h1>
        <p className="muted">账号由 Workspace 管理员创建。</p>
        <form onSubmit={submit} className="auth-form">
          <label htmlFor="username">登录名</label>
          <input id="username" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required />
          <label htmlFor="password">密码</label>
          <input id="password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          <button className="primary-button wide" type="submit" disabled={busy}>{busy ? "正在登录…" : "登录"}</button>
        </form>
      </section>
    </main>
  );
}
